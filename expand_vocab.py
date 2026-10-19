"""Back up and migrate a character vocabulary/checkpoint to UTF-8 fallback."""

import argparse
import json
import os
from pathlib import Path
import shutil
from datetime import datetime

import torch

from core_model import MicroGLRNet
from tokenizer import extend_vocab


def expand(directory: Path):
    vocab_path = directory / "vocab.json"
    checkpoint_path = directory / "micro_glr_checkpoint.pt"
    vocab = json.loads(vocab_path.read_text(encoding="utf-8-sig"))
    expanded = extend_vocab(vocab)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    state = checkpoint["model_state_dict"]
    weights = state["embedding.weight"]
    if weights.shape[0] != len(vocab):
        raise ValueError("Checkpoint and vocabulary sizes differ; refusing migration")
    if not torch.equal(weights, state["lm_head.weight"]):
        raise ValueError("Expected tied embedding/output weights")
    if "vocab" in checkpoint and checkpoint["vocab"] != vocab:
        raise ValueError("Checkpoint vocabulary IDs do not match vocab.json")
    if expanded == vocab:
        print(f"Already expanded: {len(vocab)} tokens")
        return

    # Copy UNK's embedding for untrained bytes. Old rows remain bit-for-bit
    # identical, and new rows cannot exceed UNK's old logit in exact arithmetic.
    new_weights = weights[1:2].repeat(len(expanded), 1)
    new_weights[:len(vocab)] = weights
    state = dict(state)
    state["embedding.weight"] = new_weights
    state["lm_head.weight"] = new_weights
    model = MicroGLRNet(vocab_size=len(expanded))
    model.load_state_dict(state, strict=True)
    migrated = {**checkpoint, "model_state_dict": state, "vocab": expanded,
                "tokenizer_format": "legacy-char-utf8-v1",
                "vocab_migration": {"original_size": len(vocab),
                                    "added_tokens_trained": False}}

    backup = directory / "backups" / ("vocab_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    backup.mkdir(parents=True)
    for path in (vocab_path, checkpoint_path):
        shutil.copy2(path, backup / path.name)
    for name in ("tokenizer.py", "expand_vocab.py", "train.py", "auto_evolver.py",
                 "run_daemon.py", "run_daemon_backup.py"):
        path = directory / name
        if path.exists():
            shutil.copy2(path, backup / path.name)
    vocab_tmp = vocab_path.with_suffix(".json.migrating")
    ckpt_tmp = checkpoint_path.with_suffix(".pt.migrating")
    try:
        vocab_tmp.write_text(json.dumps(expanded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        torch.save(migrated, ckpt_tmp)
        # Readers validate metadata and dimensions, so a concurrent reader
        # between these replaces fails closed instead of using mismatched IDs.
        os.replace(ckpt_tmp, checkpoint_path)
        os.replace(vocab_tmp, vocab_path)
    except Exception:
        shutil.copy2(backup / vocab_path.name, vocab_path)
        shutil.copy2(backup / checkpoint_path.name, checkpoint_path)
        raise
    finally:
        vocab_tmp.unlink(missing_ok=True)
        ckpt_tmp.unlink(missing_ok=True)
    print(f"Vocabulary: {len(vocab)} -> {len(expanded)}; backup: {backup}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    expand(parser.parse_args().directory.resolve())
