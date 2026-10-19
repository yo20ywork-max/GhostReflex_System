import json
import random
import time

OUTPUT_FILE = "speech_repair_production_60k.jsonl"
TOTAL_SAMPLES = 60000

HOMOPHONE_MAP = {
    "截圖": ["階圖", "接圖", "界圖"],
    "程式碼": ["成式碼", "程試碼", "程是碼"],
    "註解": ["助解", "住解", "祝解"],
    "變數": ["便數", "辨數", "遍數"],
    "倉庫": ["唱庫", "蒼庫", "倉酷"],
    "分支": ["分之", "芬芝", "分枝"],
    "畫布": ["花布", "話布", "化布"],
    "向量": ["向量", "相量", "像量"],
    "網址": ["往址", "網指", "往紙"],
    "快取": ["快去", "塊取", "會取"],
    "函數": ["涵數", "寒數", "含數"]
}

TECH_CONFUSION = {
    "git": ["記特", "機特", "寄特", "git"],
    "svg": ["s v g", "愛死為記", "svg"],
    "png": ["p n g", "批恩記", "png"],
    "pr": ["批阿爾", "p r", "pr"]
}

FILLERS = ["那個…", "呃…", "就是…", "然後…", "幫我…", "快點…", "隨便…", "等等…"]
REDUNDANT_POSTFIX = ["一下", "好不好", "搞定它", "用一下", "處理掉", "拜託"]

POSITIVE_POOL = [
    {
        "app": "VSCode", "clip": "Clip_code",
        "tasks": [
            ("格式化當前檔案的程式碼", "FORMAT_CODE", ["整理", "格式化"], ["程式碼", "這個檔"]),
            ("為選取的函數加入註解文件", "ADD_DOCSTRING", ["寫註解", "補註解"], ["這個函式", "這段函數"])
        ]
    },
    {
        "app": "Terminal", "clip": "None",
        "tasks": [
            ("拉取遠端倉庫最新程式碼並重啟", "GIT_PULL_RELOAD", ["更新", "拉最新"], ["專案", "倉庫"])
        ]
    },
    {
        "app": "Chrome", "clip": "None",
        "tasks": [
            ("重新整理當前分頁並強制清除快取", "HARD_RELOAD", ["強制重整", "清快取"], ["分頁", "這個網頁"])
        ]
    },
    {
        "app": "System", "clip": "None",
        "tasks": [
            ("擷取全螢幕畫面並自動儲存至桌面", "CAPTURE_SCREEN", ["截圖", "全螢幕截圖"], ["螢幕", "現在畫面"]),
            ("鎖定螢幕並進入省電待機狀態", "LOCK_DEVICE", ["鎖定", "關掉螢幕"], ["主機", "電腦"])
        ]
    }
]

NEGATIVE_PHRASES = [
    "今天中午到底要吃什麼便當", "好飽喔想喝飲料", "喂你有聽到我的聲音嗎",
    "[環境音:鍵盤敲擊聲]", "[環境音:背景雜音]", "奇怪怎麼會這樣", "先放著明天再看"
]

def noise(t):
    for k, v in HOMOPHONE_MAP.items():
        if k in t and random.random() < 0.35:
            t = t.replace(k, random.choice(v))
    for k, v in TECH_CONFUSION.items():
        if k in t.lower() and random.random() < 0.4:
            t = t.lower().replace(k, random.choice(v))
    return t

print(f"正在產出 {TOTAL_SAMPLES} 筆訓練集...")
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for _ in range(TOTAL_SAMPLES):
        if random.random() < 0.25:
            frag = random.choice(NEGATIVE_PHRASES) + " " + random.choice(["[SILENCE:SHORT]", "[SILENCE:LONG]"])
            line = {"sequence": f"[CTX:FOCUS:Desktop|CLIP:None] [FRAG:{frag}] [SEP] [TARGET:保持靜默，無操作指令。[ACT:IDLE]]"}
        else:
            group = random.choice(POSITIVE_POOL)
            clean, act, verbs, objs = random.choice(group["tasks"])
            frag = f"{random.choice(FILLERS)}{random.choice(verbs)}…{random.choice(objs)}…{random.choice(REDUNDANT_POSTFIX)}"
            frag = noise(frag) + " " + random.choice(["[SILENCE:SHORT]", "[SILENCE:LONG]"])
            line = {"sequence": f"[CTX:FOCUS:{group['app']}|CLIP:{group['clip']}] [FRAG:{frag}] [SEP] [TARGET:{clean}。[ACT:{act}]]"}
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
print(f"-> 資料集已寫入：{OUTPUT_FILE}")
