import os
import json
import time
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from core_model import MicroGLRNet
from tokenizer import UnicodeTokenizer, extend_vocab

DATA_PATH = "speech_repair_production_60k.jsonl"
CHECKPOINT_PATH = "micro_glr_checkpoint.pt"
VOCAB_PATH = "vocab.json"

if not os.path.exists(DATA_PATH):
    print(f"錯誤：找不到 {DATA_PATH}，請先執行 python generate_dataset.py")
    exit(1)

with open(DATA_PATH, "r", encoding="utf-8") as f:
    all_lines = [json.loads(line)["sequence"] for line in f]

if os.path.exists(VOCAB_PATH):
    # Never rebuild IDs from this training corpus or shrink the vocabulary.
    tokenizer = UnicodeTokenizer.load(VOCAB_PATH)
    char_to_id = tokenizer.vocab
else:
    if os.path.exists(CHECKPOINT_PATH):
        raise RuntimeError("Checkpoint exists but vocab.json is missing; restore the matching vocabulary")
    chars = sorted(set("".join(all_lines)))
    char_to_id = {"<PAD>": 0, "<UNK>": 1}
    for ch in chars:
        char_to_id[ch] = len(char_to_id)
    char_to_id = extend_vocab(char_to_id)
    tokenizer = UnicodeTokenizer(char_to_id)
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(char_to_id, f, ensure_ascii=False, indent=2)

class TrainDataset(Dataset):
    def __init__(self, lines, c2i, max_len=140):
        self.data = []
        encoder = UnicodeTokenizer(c2i)
        for seq in lines:
            p, t = seq.split(" [SEP] ", 1)
            p_ids = encoder.encode(p + " [SEP] ")
            if len(p_ids) >= max_len:
                raise ValueError("Prompt exceeds max_len; increase the token budget instead of dropping the target")
            t_ids = encoder.encode_prefix(t, max_len - len(p_ids))
            if t and not t_ids:
                raise ValueError("No complete target character fits max_len")
            ids = p_ids + t_ids
            targets = ids[1:] + [0]
            for idx in range(min(len(p_ids) - 1, len(targets))):
                targets[idx] = -100
            self.data.append((torch.tensor(ids), torch.tensor(targets)))
            
    def __len__(self): return len(self.data)
    def __getitem__(self, i): return self.data[i]

def collate_fn(batch):
    inp, tar = zip(*batch)
    return (
        nn.utils.rnn.pad_sequence(inp, batch_first=True, padding_value=0),
        nn.utils.rnn.pad_sequence(tar, batch_first=True, padding_value=-100)
    )

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
dataset = TrainDataset(all_lines, char_to_id)
loader = DataLoader(dataset, batch_size=64, shuffle=True, collate_fn=collate_fn)

model = MicroGLRNet(vocab_size=len(char_to_id)).to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3)
criterion = nn.CrossEntropyLoss(ignore_index=-100)

print(f"開始訓練 (裝置: {device})...")
model.train()
for epoch in range(1, 4):
    total_loss = 0
    for step, (x, y) in enumerate(loader):
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x)
        loss = criterion(logits.view(-1, len(char_to_id)), y.view(-1))
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        if (step + 1) % 200 == 0:
            print(f"Epoch {epoch} | Step {step+1}/{len(loader)} | Loss: {loss.item():.4f}")
    print(f">> Epoch {epoch} 平均 Loss: {total_loss/len(loader):.4f}")

torch.save({"model_state_dict": model.state_dict(), "vocab": char_to_id,
            "tokenizer_format": "legacy-char-utf8-v1"}, CHECKPOINT_PATH)
print(f"-> 訓練完成！權重已儲存至：{CHECKPOINT_PATH}")
