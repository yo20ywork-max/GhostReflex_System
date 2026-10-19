import os
import re
import sys
import json
import time
import queue
import threading
import subprocess
import ctypes
import webbrowser
import urllib.request
import urllib.parse
from datetime import datetime
from collections import deque
import tkinter as tk
import numpy as np
import sounddevice as sd
import pyperclip
import ollama
import opencc
import torch
from pynput import keyboard
from PIL import ImageGrab
from funasr import AutoModel
from core_model import MicroGLRNet
from tokenizer import UnicodeTokenizer

# ==========================================
# 0. 繁簡轉換器 (台灣正體校正)
# ==========================================
cc = opencc.OpenCC('s2twp')

# ==========================================
# 1. 系統動作調度器 (快軌系統執行)
# ==========================================
kb_ctrl = keyboard.Controller()

def type_text(content: str):
    time.sleep(0.05)
    original_clip = pyperclip.paste()
    try:
        pyperclip.copy(content)
        with kb_ctrl.pressed(keyboard.Key.ctrl):
            kb_ctrl.tap('v')
        print(f"\n⚡ [文字鍵入] 已於游標處鍵入內容")
    finally:
        time.sleep(0.1)
        pyperclip.copy(original_clip)

def action_format_code():
    time.sleep(0.05)
    with kb_ctrl.pressed(keyboard.Key.shift, keyboard.Key.alt):
        kb_ctrl.tap('f')
    print("\n⚡ [執行快軌] 已發送程式碼排版快捷鍵 (Shift + Alt + F)")

def action_add_docstring():
    time.sleep(0.05)
    doc_template = '"""\n[函數功能說明]\n\nArgs:\n    無\n\nReturns:\n    None\n"""'
    pyperclip.copy(doc_template)
    with kb_ctrl.pressed(keyboard.Key.ctrl):
        kb_ctrl.tap('v')
    print("\n⚡ [執行快軌] 已貼上標準 Docstring 函數註解模板")

def action_git_pull():
    print("\n⚡ [執行快軌] 正在背景執行 Git Pull 遠端更新...")
    try:
        res = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=12)
        out = res.stdout.strip() or res.stderr.strip()
        print(f"Git 執行回傳:\n{out}")
    except Exception as e:
        print(f"Git 執行異常: {e}")

def action_hard_reload():
    time.sleep(0.05)
    with kb_ctrl.pressed(keyboard.Key.ctrl):
        kb_ctrl.tap(keyboard.Key.f5)
    print("\n⚡ [執行快軌] 已發送瀏覽器強制更新快捷鍵 (Ctrl + F5)")

def action_capture_screen():
    desktop_dir = os.path.expanduser("~/Desktop")
    file_name = f"GhostReflex_Shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    target_path = os.path.join(desktop_dir, file_name)
    shot = ImageGrab.grab()
    shot.save(target_path, "PNG")
    print(f"\n⚡ [執行快軌] 全螢幕截圖已儲存至桌面: {target_path}")

def action_lock_device():
    print("\n⚡ [執行快軌] 立即鎖定 Windows 工作站螢幕")
    ctypes.windll.user32.LockWorkStation()

def action_auto_fill():
    search_paths = [
        os.path.join(os.path.dirname(__file__), "config", "profile.json"),
        os.path.join(os.path.dirname(__file__), "profile.json"),
        "profile.json"
    ]
    target_path = next((p for p in search_paths if os.path.exists(p)), None)
    if target_path:
        with open(target_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
        formatted_str = "\n".join([f"{k}: {v}" for k, v in profile_data.items()])
        pyperclip.copy(formatted_str)
        print(f"\n⚡ [執行快軌] 個人資料已載入剪貼簿:\n{formatted_str}")
    else:
        print("\n⚠️ [填表提示] 找不到 profile.json 設定檔")

def action_open_youtube():
    print("\n⚡ [執行快軌] 開啟 YouTube 首頁")
    webbrowser.open("https://www.youtube.com")

def action_open_chatgpt():
    print("\n⚡ [執行快軌] 開啟 ChatGPT 網頁")
    webbrowser.open("https://chatgpt.com")

ACTIONS = {
    "FORMAT_CODE": action_format_code,
    "ADD_DOCSTRING": action_add_docstring,
    "GIT_PULL_RELOAD": action_git_pull,
    "HARD_RELOAD": action_hard_reload,
    "CAPTURE_SCREEN": action_capture_screen,
    "LOCK_DEVICE": action_lock_device,
    "AUTO_FILL": action_auto_fill,
    "OPEN_YOUTUBE": action_open_youtube,
    "OPEN_CHATGPT": action_open_chatgpt
}

# ==========================================
# 2. 泛化 100% 動態反射與工具調度引擎
# ==========================================
# 紀錄當前播放的影片 ID，供後續秒數微調使用
CURRENT_VIDEO_ID = None

def action_yt(payload: str):
    """自動搜尋 YouTube 影片，若 payload 內含時間則直接帶入網址"""
    global CURRENT_VIDEO_ID
    
    # 檢查 payload 裡面有沒有藏秒數（例如「周杰倫 晴天 180秒」）
    sec_match = re.search(r'(\d+)\s*秒', payload)
    target_sec = int(sec_match.group(1)) if sec_match else None
    
    # 清洗實際要搜尋的歌名（把秒數文字濾掉，避免搜尋不到）
    clean_query = re.sub(r'\d+\s*秒', '', payload).strip()
    if not clean_query:
        clean_query = "精選音樂"
        
    print(f"\n🎵 [動態工具] 執行 YouTube 播放: {clean_query} (指定秒數: {target_sec})")
    try:
        encoded_query = urllib.parse.quote(clean_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            html = resp.read().decode('utf-8')
        video_ids = re.findall(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\"", html)
        if video_ids:
            CURRENT_VIDEO_ID = video_ids[0]
            # 💡 關鍵：如果一開始就有指定秒數，直接把 &t=秒數 帶進第一支開的網頁，完美省掉開第二個分頁！
            target_url = f"https://www.youtube.com/watch?v={CURRENT_VIDEO_ID}"
            if target_sec:
                target_url += f"&t={target_sec}s"
                
            webbrowser.open(target_url)
            time.sleep(2.0)
            return f"已自動開播: {clean_query}" + (f" (自 {target_sec} 秒起)" if target_sec else "")
    except Exception:
        pass
        
    webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_query)}")
    return f"已開啟 YouTube 搜尋: {clean_query}"

action_youtube = action_yt
action_play = action_yt

def action_seek(payload: str):
    """利用 YouTube 網址時間參數（&t=秒數）進行絕對精準跳轉"""
    global CURRENT_VIDEO_ID
    m = re.search(r'\d+', payload)
    target_secs = int(m.group()) if m else 30
    
    print(f"🎯 [絕對時間跳轉] 強制導向至: {target_secs} 秒處")
    
    if CURRENT_VIDEO_ID:
        # 如果知道當前影片 ID，直接重導向網址帶入 &t=秒數，絕對不會拉到底！
        target_url = f"https://www.youtube.com/watch?v={CURRENT_VIDEO_ID}&t={target_secs}s"
        webbrowser.open(target_url)
        return f"已絕對跳轉至: {target_secs} 秒"
    else:
        # 備用防呆：如果剛才不是透過程式開的影片，才退回模擬右方向鍵
        steps = max(1, target_secs // 5)
        for _ in range(steps):
            kb_ctrl.tap('l')
            time.sleep(0.01)
        return f"已透過方向鍵快進: {target_secs} 秒"

action_forward = action_seek
action_jump = action_seek

def action_pause(payload: str):
    """暫停或播放切換"""
    time.sleep(0.05)
    kb_ctrl.tap('k')
    return "已執行: 播放/暫停切換"

def action_replay(payload: str):
    """從頭重播"""
    time.sleep(0.05)
    kb_ctrl.tap('0')
    time.sleep(0.05)
    kb_ctrl.tap('k')
    return "已執行: 從頭重播"

def action_close_tab(payload: str):
    """關閉當前分頁"""
    time.sleep(0.05)
    with kb_ctrl.pressed(keyboard.Key.ctrl):
        kb_ctrl.tap('w')
    return "已執行: 分頁已關閉"

def action_search(payload: str):
    """Google 搜尋"""
    webbrowser.open(f"https://www.google.com/search?q={payload}")
    return f"已執行搜尋: {payload}"

def action_article(payload: str):
    """生成長文並複製"""
    pyperclip.copy(payload)
    return f"已生成文章並複製（共 {len(payload)} 字）"

def action_translate(payload: str):
    """翻譯並複製"""
    pyperclip.copy(payload)
    return f"翻譯完成已複製: {payload}"


def get_dynamic_registry():
    """🤖 動態反射註冊表：自動掃描當前檔案中所有以 action_ 開頭的函數"""
    registry = {}
    current_module = sys.modules[__name__]
    for name in dir(current_module):
        if name.startswith("action_"):
            action_key = name.replace("action_", "").upper()
            registry[action_key] = getattr(current_module, name)
    return registry


def ask_slow_track(user_prompt: str) -> str:
    print(f"\n🧠 [泛化大腦啟動] 使用者輸入: {user_prompt}")
    models_to_try = ["ghost-brain", "qwen2.5-coder:7b"]
    response = None
    
    for m in models_to_try:
        try:
            response = ollama.chat(
                model=m,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一個具備 100% 泛化能力的自主 AI Agent。\n"
                            "【絕對核心規則】\n"
                            "1. 請依據使用者意圖，自由發揮並輸出任何合適的操作標籤。\n"
                            "2. 標籤格式統一為：[CMD:動作名稱] 參數內容。\n"
                            "3. 若使用者要求「播放某某影片並跳到幾分幾秒」，請將秒數直接寫在 YT 參數內（例如 [CMD:YT] 周杰倫晴天 180秒），或者拆開輸出。\n"
                            "4. 支援的常見動作代稱包含 YT, YOUTUBE, PLAY, SEEK, FORWARD, PAUSE, REPLAY, SEARCH, ARTICLE, TRANSLATE 等。\n"
                            "5. 若無特定動作，直接以繁體中文回答。"
                        )
                    },
                    {"role": "user", "content": user_prompt}
                ]
            )
            break
        except Exception:
            continue

    if not response:
        return "調用 Ollama 失敗，請確認 Ollama 服務已在背景啟動。"

    reply = response["message"]["content"].strip()
    print(f"🤖 [Qwen 原始回應]:\n{reply}")

    tag_matches = list(re.finditer(r'\[(?:ACT|CMD):([A-Z_]+)\]', reply))
    
    if tag_matches:
        registry = get_dynamic_registry()
        execution_results = []
        
        # 💡 智慧防呆：檢查是否同時含有 YT/PLAY 與 SEEK/FORWARD
        cmd_names_found = [m.group(1).upper() for m in tag_matches]
        has_yt_and_seek = any(c in cmd_names_found for c in ["YT", "YOUTUBE", "PLAY"]) and any(c in cmd_names_found for c in ["SEEK", "FORWARD", "JUMP"])
        
        seek_payload_captured = None
        if has_yt_and_seek:
            # 如果同時存在，先把 SEEK 的參數抓出來備用
            for i, match in enumerate(tag_matches):
                if match.group(1).upper() in ["SEEK", "FORWARD", "JUMP"]:
                    start_pos = match.end()
                    end_pos = tag_matches[i+1].start() if i + 1 < len(tag_matches) else len(reply)
                    seek_payload_captured = reply[start_pos:end_pos].strip()

        for i, match in enumerate(tag_matches):
            cmd_name = match.group(1).upper()
            start_pos = match.end()
            end_pos = tag_matches[i+1].start() if i + 1 < len(tag_matches) else len(reply)
            payload = reply[start_pos:end_pos].strip()
            
            print(f"⚙️ [動態反射調度] 偵測到動作: {cmd_name}, 參數: {payload}")

            # 如果同時有 YT 和 SEEK，且目前正在跑 SEEK 標籤，直接跳過不重複執行（因為已經在 YT 裡一次帶入了）
            if has_yt_and_seek and cmd_name in ["SEEK", "FORWARD", "JUMP"]:
                print(f"🛡️ [智慧防呆] 偵測到複合播放與跳轉，已將秒數合併至首個開播指令，略過重複跳轉。")
                continue

            # 🛠️ 如果是 YT 播放標籤，且我們剛好抓到了獨立的 SEEK 參數，把它們融合成一個完整 payload 傳進去！
            if cmd_name in ["YT", "YOUTUBE", "PLAY"] and seek_payload_captured and seek_payload_captured not in payload:
                payload = f"{payload} {seek_payload_captured}"

            if cmd_name in registry:
                try:
                    res_msg = registry[cmd_name](payload)
                    execution_results.append(res_msg)
                except Exception as e:
                    execution_results.append(f"執行 [{cmd_name}] 發生異常: {e}")
            else:
                if payload:
                    pyperclip.copy(payload)
                    execution_results.append(f"已自動處理未知動作 [{cmd_name}] 並複製內容")
                else:
                    execution_results.append(f"收到未知指令 [{cmd_name}]")
                    
        return " | ".join(execution_results)

    return reply

def make_slow_track_runner(prompt_text: str):
    def _runner():
        reply = ask_slow_track(prompt_text)
        print(f"\n🤖 [回覆結果]:\n{reply}\n")
        pyperclip.copy(reply)
        print("📋 [系統] 內容已更新至剪貼簿。")
    return _runner

# ==========================================
# 3. 懸浮藥丸 UI (含文字輸入與語音雙模組)
# ==========================================
class GhostPillHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.0)
        screen_w = self.root.winfo_screenwidth()
        self.root.geometry(f"420x50+{screen_w - 450}+45")
        
        self.frame = tk.Frame(self.root, bg="#18181E", highlightthickness=1, highlightbackground="#363645")
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        self.label = tk.Label(self.frame, text="GhostReflex 待命...", fg="#ECECF1", bg="#18181E", font=("Segoe UI", 10, "bold"))
        self.label.pack(side=tk.LEFT, padx=14)
        
        self.entry = tk.Entry(self.frame, fg="#ECECF1", bg="#262838", insertbackground="white", font=("Segoe UI", 10), relief=tk.FLAT)
        self.entry.bind("<Return>", self.on_submit_text)
        
        self.hint = tk.Label(self.frame, text="切換打字", fg="#5B9DFF", bg="#262838", font=("Segoe UI", 8, "bold"), padx=8, pady=3)
        self.hint.pack(side=tk.RIGHT, padx=12)
        self.hint.bind("<Button-1>", lambda e: self.toggle_input_mode())
        
        self.is_active = False
        self.is_input_mode = False
        self.handler = None
        self.timer = None
        self.priority = 0
        self.root.wm_attributes("-alpha", 0.85)

    def toggle_input_mode(self):
        if not self.is_input_mode:
            self.is_input_mode = True
            self.label.pack_forget()
            self.entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=8)
            self.entry.focus_set()
            self.hint.config(text="送出", fg="#22C55E")
            self.root.wm_attributes("-alpha", 0.98)
            if self.timer:
                self.timer.cancel()
        else:
            self.submit_text_action()

    def on_submit_text(self, event):
        self.submit_text_action()

    def submit_text_action(self):
        text = self.entry.get().strip()
        if text:
            print(f"\n⌨️ [手動輸入指令]: {text}")
            self.entry.delete(0, tk.END)
            self.exit_input_mode()
            threading.Thread(target=make_slow_track_runner(text), daemon=True).start()
        else:
            self.exit_input_mode()

    def exit_input_mode(self):
        self.is_input_mode = False
        self.entry.pack_forget()
        self.label.pack(side=tk.LEFT, padx=14)
        self.hint.config(text="切換打字", fg="#5B9DFF")

    def show(self, text, func, priority=0):
        if self.is_input_mode:
            return
        def _render():
            self.priority = priority
            self.handler = func
            display_str = text[:18] + "..." if len(text) > 18 else text
            self.label.config(text=display_str)
            self.root.wm_attributes("-alpha", 0.94)
            self.is_active = True
            if self.timer: 
                self.timer.cancel()
            self.timer = threading.Timer(5.0, self.hide)
            self.timer.start()
        self.root.after(0, _render)

    def hide(self):
        if self.is_input_mode:
            return
        def _fade():
            self.root.wm_attributes("-alpha", 0.85)
            self.is_active = False
            self.handler = None
            self.priority = 0
            self.label.config(text="GhostReflex 待命...")
        self.root.after(0, _fade)

    def trigger(self):
        if self.is_input_mode:
            self.submit_text_action()
        elif self.is_active and self.handler:
            f = self.handler
            self.hide()
            threading.Thread(target=f, daemon=True).start()

hud = GhostPillHUD()

def on_press(key):
    if key == keyboard.Key.ctrl_r and hud.is_active:
        hud.trigger()

listener = keyboard.Listener(on_press=on_press)
listener.daemon = True
listener.start()

# ==========================================
# 4. 載入 μ-GLR 神經網路推論引擎
# ==========================================
with open("vocab.json", "r", encoding="utf-8") as f:
    c2i = json.load(f)
i2c = {int(v): k for k, v in c2i.items()}
tokenizer = UnicodeTokenizer(c2i)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = MicroGLRNet(vocab_size=len(c2i)).to(device)
if os.path.exists("micro_glr_checkpoint.pt"):
    model.load_state_dict(torch.load("micro_glr_checkpoint.pt", map_location=device)["model_state_dict"])
model.eval()

def infer(ctx, frag):
    prompt = f"{ctx} [FRAG:{frag}] [SEP] [TARGET:"
    tokens = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long, device=device)
    out = []
    with torch.no_grad():
        for _ in range(40):
            logits = model(tokens)
            nid = torch.argmax(logits[:, -1, :], dim=-1).item()
            if nid == 0: break
            out.append(nid)
            if tokenizer.decode(out, errors="replace").endswith("]]"): break
            tokens = torch.cat([tokens, torch.tensor([[nid]], device=device)], dim=1)
    text = tokenizer.decode(out, errors="replace")
    m = re.search(r"\[ACT:([A-Z_]+)\]", text)
    act = m.group(1) if m else "IDLE"
    clean = text.split("[ACT:")[0].replace("]", "").strip("。 ")
    return clean, act

# ==========================================
# 5. 初始化 Paraformer 引擎與自適應環境校準收音
# ==========================================
print("\n[ASR] 正在加載 Paraformer 中文聲學模型...")
asr_device = "cuda:0" if torch.cuda.is_available() else "cpu"

asr_model = AutoModel(
    model="paraformer-zh",
    hub="hf",
    device=asr_device
)
print(f"[ASR] 模型已就緒 (運算裝置: {asr_device})")

HOTWORDS = "YouTube you two HU two 優土伯 油土伯 ChatGPT 截圖 螢幕截圖 鎖定 填表 自動填表 播放音樂 晴天 稻香 周杰倫 蔡依林 五月天 翻譯 生成 文章"
audio_q = queue.Queue()

def audio_cb(indata, frames, time_info, status):
    audio_q.put(indata.copy())

def mic_worker():
    with sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1600, callback=audio_cb):
        print("\n" + "="*50)
        print("🛑 [環境聲學校準] 請保持常態安靜 5 秒，正在採集環境噪音基底...")
        print("="*50)

        calib_chunks = []
        for remaining in range(5, 0, -1):
            sys.stdout.write(f"\r⏳ 採樣倒數: {remaining} 秒... (請勿發話或劇烈敲擊)")
            sys.stdout.flush()
            for _ in range(10):
                calib_chunks.append(audio_q.get())

        rms_list = [np.sqrt(np.mean(c**2)) for c in calib_chunks]
        avg_noise = np.mean(rms_list)
        max_noise = np.max(rms_list)

        VOICE_THRESHOLD = max(max_noise * 1.35, avg_noise * 2.6, 0.022)

        print(f"\n\n✅ [校準完成]")
        print(f"   ├─ 平均底噪能量: {avg_noise:.4f}")
        print(f"   ├─ 最大雜訊峰值: {max_noise:.4f}")
        print(f"   └─ 最終判定門檻: {VOICE_THRESHOLD:.4f}")
        print("="*50)
        print("🎙️ [守護行程就緒] 麥克風已啟動，請隨口說出指令...\n")

        pre_buffer = deque(maxlen=4)
        buf = []
        silence_cnt = 0
        speech_streak = 0
        has_voice = False
        
        FILLER_WORDS = {"嗯", "有沒有", "那個", "啊", "喔", "好的", "測試", "喂", "在嗎"}
        SLOW_KEYWORDS = ["幫我", "請問", "查", "搜尋", "找", "播放", "聽", "寫", "如何", "怎麼", "什麼", "翻譯", "生成", "文章", "心得", "報告", "打字", "鍵入", "輸入"]

        while True:
            chunk = audio_q.get()
            rms = np.sqrt(np.mean(chunk**2))
            
            zcr = np.mean(np.abs(np.diff(np.sign(chunk.flatten())))) / 2
            is_speech_chunk = (rms > VOICE_THRESHOLD) and (zcr < 0.40)

            if is_speech_chunk:
                speech_streak += 1
                if speech_streak >= 3 and not has_voice:
                    has_voice = True
                    buf.extend(list(pre_buffer))
                if has_voice:
                    buf.append(chunk)
                silence_cnt = 0
            else:
                speech_streak = 0
                if has_voice: 
                    buf.append(chunk)
                    silence_cnt += 1
                else:
                    pre_buffer.append(chunk)

            if has_voice and silence_cnt > 7:
                full_audio = np.concatenate(buf, axis=0).flatten()
                buf = []
                has_voice = False
                silence_cnt = 0
                speech_streak = 0
                pre_buffer.clear()

                if len(full_audio) < 12800:
                    continue

                res = asr_model.generate(input=full_audio, hotword=HOTWORDS)
                if not res or not res[0]["text"]:
                    continue

                raw_text = res[0]["text"]
                raw_text = raw_text.replace("you two", "YouTube").replace("HU two", "YouTube").replace("優土伯", "YouTube").replace("油土伯", "YouTube")
                
                text = cc.convert(raw_text).strip()
                if not text:
                    continue

                print(f"\nASR 識別: {text}")
                clean, act = infer("[CTX:FOCUS:VSCode|CLIP:None]", text)
                print(f"μ-GLR 解析: {clean} | 動作: [{act}]")

                matched_action = None

                m_type = re.match(r"^(打字|輸入|鍵入)\s*(.+)", text)
                if m_type:
                    target_str = m_type.group(2).strip()
                    matched_action = (f"輸入: {target_str}", lambda s=target_str: type_text(s))
                elif act in ACTIONS:
                    matched_action = (clean, ACTIONS[act])
                elif "截圖" in text or "螢幕截圖" in text:
                    matched_action = ("擷取全螢幕", ACTIONS["CAPTURE_SCREEN"])
                elif "鎖定" in text or "離開電腦" in text:
                    matched_action = ("鎖定螢幕", ACTIONS["LOCK_DEVICE"])
                elif "排版" in text or "整理代碼" in text:
                    matched_action = ("排版整理", ACTIONS["FORMAT_CODE"])
                elif "註解" in text or "文檔" in text:
                    matched_action = ("插入註解", ACTIONS["ADD_DOCSTRING"])
                elif "刷新" in text or "重新載入" in text:
                    matched_action = ("強制重新載入", ACTIONS["HARD_RELOAD"])
                elif "git" in text.lower() or "更新程式" in text:
                    matched_action = ("Git Pull 更新", ACTIONS["GIT_PULL_RELOAD"])
                elif "填表" in text or "自動填表" in text:
                    matched_action = ("自動填表", ACTIONS["AUTO_FILL"])
                elif text.strip().lower() in ["開啟youtube", "開啟yt", "打開youtube", "打開yt", "youtube", "yt"]:
                    matched_action = ("開啟 YouTube", ACTIONS["OPEN_YOUTUBE"])
                elif text.strip().lower() in ["開啟chatgpt", "打開chatgpt", "chatgpt", "gpt"]:
                    matched_action = ("開啟 ChatGPT", ACTIONS["OPEN_CHATGPT"])

                if matched_action:
                    print(f"💡 [快軌待命] 捕獲「{matched_action[0]}」，請按 右側 Ctrl 執行")
                    hud.show(matched_action[0], matched_action[1], priority=1)
                else:
                    clean_text = re.sub(r"[^\w\s]", "", text).strip()
                    has_intent = any(kw in clean_text for kw in SLOW_KEYWORDS) or any(k in clean_text.lower() for k in ["youtube", "yt"])
                    if (has_intent or len(clean_text) >= 5) and clean_text not in FILLER_WORDS:
                        print(f"💡 [慢軌待命] 收到「{clean_text}」，按 右側 Ctrl 才會送往 Qwen 處理")
                        hud.show(f"處理: {clean_text}", make_slow_track_runner(clean_text), priority=0)
                    else:
                        hud.hide()

threading.Thread(target=mic_worker, daemon=True).start()
hud.root.mainloop()
