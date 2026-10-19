"""Stable legacy character IDs with lossless UTF-8 byte fallback.

Unicode scalar values are supported; isolated UTF-16 surrogates are rejected.
The vocabulary must be extended together with its checkpoint (expand_vocab.py).
"""

import json
from pathlib import Path


def byte_token(value: int) -> str:
    return f"<0x{value:02X}>"


def validate_vocab(vocab: dict) -> None:
    if vocab.get("<PAD>") != 0 or vocab.get("<UNK>") != 1:
        raise ValueError("Expected <PAD>=0 and <UNK>=1")
    ids = list(vocab.values())
    if any(type(i) is not int for i in ids) or sorted(ids) != list(range(len(ids))):
        raise ValueError("Vocabulary IDs must be unique and contiguous")
    allowed = {"<PAD>", "<UNK>"} | {byte_token(b) for b in range(256)}
    if any(not isinstance(t, str) or (len(t) != 1 and t not in allowed) for t in vocab):
        raise ValueError("Unsupported vocabulary token")


def extend_vocab(vocab: dict) -> dict:
    validate_vocab(vocab)
    expanded = dict(vocab)
    for value in range(256):
        expanded.setdefault(byte_token(value), len(expanded))
    return expanded


class UnicodeTokenizer:
    def __init__(self, vocab: dict):
        validate_vocab(vocab)
        self.vocab = dict(vocab)
        self.id_to_token = {i: token for token, i in vocab.items()}
        self.byte_ids = [vocab.get(byte_token(b)) for b in range(256)]
        if any(i is None for i in self.byte_ids):
            raise ValueError("Missing UTF-8 fallback tokens; run expand_vocab.py first")
        self.id_to_byte = {i: b for b, i in enumerate(self.byte_ids)}

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def encode(self, text: str) -> list[int]:
        result = []
        for char in text:
            if 0xD800 <= ord(char) <= 0xDFFF:
                raise ValueError("Isolated UTF-16 surrogate is not a Unicode scalar value")
            token_id = self.vocab.get(char)
            if token_id is not None:
                result.append(token_id)
            else:
                result.extend(self.byte_ids[b] for b in char.encode("utf-8"))
        return result

    def decode(self, ids, *, errors="strict") -> str:
        parts = []
        pending = bytearray()

        def flush():
            if pending:
                parts.append(pending.decode("utf-8", errors=errors))
                pending.clear()

        for token_id in ids:
            token_id = int(token_id)
            if token_id in self.id_to_byte:
                pending.append(self.id_to_byte[token_id])
            else:
                flush()
                token = self.id_to_token[token_id]
                if token != "<PAD>":
                    parts.append(token)
        flush()
        return "".join(parts)

    def encode_prefix(self, text: str, max_tokens: int) -> list[int]:
        """Truncate at a character boundary, never inside a UTF-8 sequence."""
        result = []
        for char in text:
            encoded = self.encode(char)
            if len(result) + len(encoded) > max_tokens:
                break
            result.extend(encoded)
        return result
