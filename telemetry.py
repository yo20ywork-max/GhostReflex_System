import json
import time

TELEMETRY_PATH = "user_telemetry.jsonl"

def log_interaction(context, fragment, clean_text, action_id, accepted: bool):
    """將日常交互自動沉澱為帶標籤的訓練樣本"""
    if accepted:
        # 使用者採納：將模型當前預測固化為正向標籤
        target = f"{clean_text}。[ACT:{action_id}]]"
    else:
        # 使用者忽略（超時淡出）：判定為誤觸，自動重定向為靜默標籤
        target = "保持靜默，無操作指令。[ACT:IDLE]]"

    record = {
        "sequence": f"{context} [FRAG:{fragment}] [SEP] [TARGET:{target}",
        "timestamp": time.time(),
        "accepted": accepted
    }
    with open(TELEMETRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# 在 GhostPillHUD 內部埋點：
# 1. trigger() 觸發時調用：log_interaction(..., accepted=True)
# 2. hide() 因 Timer 超時觸發時調用：log_interaction(..., accepted=False)