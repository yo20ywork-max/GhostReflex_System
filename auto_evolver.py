import os
import time
import json
import ctypes
import torch
import torch.nn as nn
from core_model import MicroGLRNet
from lora_layer import inject_lora_to_model
from tokenizer import UnicodeTokenizer

TELEMETRY_PATH = "user_telemetry.jsonl"
CHECKPOINT_PATH = "micro_glr_checkpoint.pt"

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_system_idle_seconds():
    """獲取 Windows 系統當前未操作時長（秒）"""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis / 1000.0

def run_lora_evolution():
    if not os.path.exists(TELEMETRY_PATH):
        return

    with open(TELEMETRY_PATH, "r", encoding="utf-8") as f:
        samples = [json.loads(line.strip())["sequence"] for line in f if line.strip()]

    if len(samples) < 20:
        return  # 累積樣本過少，暫不執行

    print(f"\n⚡ [系統閒置中] 觸發自進化程序，正在訓練 {len(samples)} 筆個人回饋資料...")

    with open("vocab.json", "r", encoding="utf-8") as f:
        c2i = json.load(f)
    tokenizer = UnicodeTokenizer(c2i)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = MicroGLRNet(vocab_size=len(c2i)).to(device)
    base_ckpt = torch.load(CHECKPOINT_PATH, map_location=device, weights_only=True)
    if base_ckpt.get("vocab", c2i) != c2i:
        raise ValueError("Checkpoint vocabulary does not match vocab.json")
    model.load_state_dict(base_ckpt["model_state_dict"])

    # 掛載 LoRA
    model = inject_lora_to_model(model, r=4).to(device)
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-3)
    criterion = nn.CrossEntropyLoss(ignore_index=-100)

    # 批次微調 5 個 Epoch
    model.train()
    for _ in range(5):
        for seq in samples:
            p, t = seq.split(" [SEP] ", 1)
            p_ids = tokenizer.encode(p + " [SEP] ")
            if len(p_ids) >= 140:
                raise ValueError("Prompt exceeds 140 tokens; increase the budget before fine-tuning")
            t_ids = tokenizer.encode_prefix(t, 140 - len(p_ids))
            if t and not t_ids:
                raise ValueError("No complete target character fits 140 tokens")
            ids = p_ids + t_ids
            targets = ids[1:] + [0]
            for idx in range(min(len(p_ids) - 1, len(targets))):
                targets[idx] = -100

            x = torch.tensor([ids], device=device)
            y = torch.tensor([targets], device=device)

            optimizer.zero_grad()
            loss = criterion(model(x).view(-1, len(c2i)), y.view(-1))
            loss.backward()
            optimizer.step()

    # 將 LoRA 增量直接融合（Merge）回主模型矩陣
    with torch.no_grad():
        for block in model.layers:
            for name in ("q_proj", "v_proj", "out_proj"):
                proj = getattr(block.cell, name)
                delta_w = (proj.lora_B @ proj.lora_A) * proj.scaling
                proj.original.weight.add_(delta_w)
                setattr(block.cell, name, proj.original)

    # 儲存融合後的全新檢查點
    torch.save({**base_ckpt, "model_state_dict": model.state_dict(), "vocab": c2i,
                "tokenizer_format": "legacy-char-utf8-v1"}, CHECKPOINT_PATH)
    
    # 備份並清空日誌檔
    os.rename(TELEMETRY_PATH, f"user_telemetry_archive_{int(time.time())}.jsonl")
    print("✅ [自進化完成] 權重已更新，模型已完全同化您最新的語音與交互習慣。")

if __name__ == "__main__":
    print("[自進化守護已啟動] 當您離開電腦超過 10 分鐘時將自動執行增量微調...")
    while True:
        time.sleep(30)
        if get_system_idle_seconds() > 600:  # 閒置 > 600 秒
            run_lora_evolution()
