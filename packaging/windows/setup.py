"""Public, per-user Windows installer and owned-process control panel."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from engine import Installer, Job, Cancelled

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def shortcuts(root, installer, shortcut_dir=None):
    target = root / 'GhostReflex-Setup.exe'
    if not getattr(sys, 'frozen', False):
        return
    if Path(sys.executable).resolve() != target.resolve():
        shutil.copy2(sys.executable, target)
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    if shortcut_dir is not None:
        shortcut_dir.mkdir(parents=True, exist_ok=True)
    places = ('@(' + quote(shortcut_dir.resolve()) + ')') if shortcut_dir is not None else "@($shell.SpecialFolders.Item('Desktop'), $shell.SpecialFolders.Item('Programs'))"
    script = ("$ErrorActionPreference = 'Stop'\n$shell = New-Object -ComObject WScript.Shell\n"
        "$places = " + places + "\n"
        "foreach ($place in $places) {\n"
        "  $link = $shell.CreateShortcut((Join-Path $place 'GhostReflex.lnk'))\n"
        "  $link.TargetPath = " + quote(target) + "\n"
        "  $link.Arguments = '--root '+[char]34+" + quote(root) + "+[char]34\n"
        "  $link.WorkingDirectory = " + quote(root) + "\n"
        "  $link.Save()\n}\n")
    installer.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], timeout=30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path)
    parser.add_argument('--no-auto', action='store_true', help='Show controls without starting')
    parser.add_argument('--install-only', action='store_true', help='Install, check and stop owned processes')
    parser.add_argument('--no-shortcuts', action='store_true', help='Use for isolated verification installs')
    parser.add_argument('--shortcut-dir', type=Path, help='Write verification shortcuts inside this directory')
    args = parser.parse_args()
    config = json.loads((ASSETS / 'release.json').read_text(encoding='utf8'))
    target = (args.root or Path(os.environ['LOCALAPPDATA']) / 'GhostReflex_System').resolve()
    target.mkdir(parents=True, exist_ok=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\GhostReflexSetup-' + hashlib.sha256(str(target).casefold().encode()).hexdigest())
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        messagebox.showinfo('GhostReflex', '此安裝位置的控制面板已開啟。請使用原本的視窗。')
        kernel.CloseHandle(mutex)
        return 1
    cancel = threading.Event()
    job = Job()
    events = queue.Queue()
    worker = Installer(target, config, lambda kind, value: events.put((kind, value)), cancel, job)
    if args.install_only:
        try:
            worker.install()
            if not args.no_shortcuts: shortcuts(target, worker, args.shortcut_dir)
            return 0
        except Exception as exc:
            (target / 'setup-error.txt').write_text(str(exc), encoding='utf8')
            return 1
        finally:
            worker.close_all()
            kernel.CloseHandle(mutex)

    root = tk.Tk()
    root.title('GhostReflex — 安裝與啟動')
    root.geometry('700x530')
    root.minsize(640, 500)
    root.configure(bg='#f4f6fa')
    style = ttk.Style()
    style.theme_use('vista')
    style.configure('.', font=('Microsoft JhengHei UI', 10))
    main = ttk.Frame(root, padding=26)
    main.pack(fill='both', expand=True)
    ttk.Label(main, text='GhostReflex', font=('Segoe UI', 25, 'bold')).pack(anchor='w')
    ttk.Label(main, text='Windows 桌面代理 · Ollama · 中文語音', font=('Microsoft JhengHei UI', 12)).pack(anchor='w', pady=(3, 16))
    status = tk.StringVar(value='準備啟動')
    ttk.Label(main, textvariable=status, wraplength=630).pack(anchor='w', pady=(0, 8))
    bar = ttk.Progressbar(main, maximum=100)
    bar.pack(fill='x')
    progress = tk.StringVar(value='')
    ttk.Label(main, textvariable=progress).pack(anchor='w', pady=(5, 10))
    ttk.Label(main, text='首次需連網下載約 7–9 GB，請保留 25 GB 可用空間。\n之後點桌面 GhostReflex 即會啟動模型與語音。\n語音校準時保持安靜 5 秒；看到右上角辨識文字後，10 秒內按右 Ctrl 執行。', wraplength=630, justify='left').pack(anchor='w', pady=(0, 13))
    ttk.Label(main, text='安裝位置：' + str(target), wraplength=630, foreground='#666').pack(anchor='w')
    logbox = tk.Text(main, height=5, font=('Microsoft JhengHei UI', 9), wrap='word', state='disabled')
    logbox.pack(fill='both', expand=True, pady=12)
    buttons = ttk.Frame(main)
    buttons.pack(fill='x')
    busy = False
    closing = False
    log_offset = 0

    def append(text):
        logbox.configure(state='normal')
        logbox.insert('end', text + '\n')
        if int(logbox.index('end-1c').split('.')[0]) > 80:
            logbox.delete('1.0', '40.0')
        logbox.see('end')
        logbox.configure(state='disabled')

    def start():
        nonlocal busy, log_offset
        if busy or closing or (worker.app_process and worker.app_process.poll() is None):
            return
        busy = True
        start_button.configure(state='disabled')
        def work():
            try:
                installed = target / 'installed.json'
                try: current = json.loads(installed.read_text(encoding='utf8'))
                except (OSError, ValueError): current = {}
                if current.get('version') != config['version']:
                    worker.install()
                    if not args.no_shortcuts: shortcuts(target, worker, args.shortcut_dir)
                log = target / 'agent.log'
                log_offset = log.stat().st_size if log.exists() else 0
                worker.step('啟動中文語音，正在載入及校準麥克風…')
                worker.launch()
                events.put(('launched', None))
            except Cancelled:
                events.put(('error', '已停止。下次開啟可續傳。'))
            except Exception as exc:
                (target / 'setup-error.txt').write_text(str(exc), encoding='utf8')
                events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def close():
        nonlocal closing
        if closing: return
        closing = True
        status.set('正在關閉麥克風、GhostReflex 與本次啟動的 Ollama…')
        start_button.configure(state='disabled')
        cancel.set()
        def stop():
            worker.close_all()
            events.put(('closed', None))
        threading.Thread(target=stop, daemon=True).start()

    start_button = ttk.Button(buttons, text='安裝／啟動中文語音', command=start)
    start_button.pack(side='left')
    ttk.Button(buttons, text='開啟工作資料夾', command=lambda: os.startfile(str(target / 'workspace' if (target / 'workspace').exists() else target))).pack(side='left', padx=8)
    ttk.Button(buttons, text='關閉系統', command=close).pack(side='right')
    root.protocol('WM_DELETE_WINDOW', close)

    def tick():
        nonlocal busy, log_offset
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'closed':
                    root.destroy(); return
                if kind == 'status':
                    status.set(value); append(value)
                elif kind == 'progress':
                    done, total = value
                    bar['value'] = done * 100 / max(total, 1)
                    progress.set(f'{done / 1e9:.2f} / {total / 1e9:.2f} GB')
                elif kind == 'error':
                    busy = False; status.set('啟動未完成：' + value); append(value)
                    start_button.configure(state='normal')
                elif kind == 'launched':
                    busy = False; progress.set('模型服務已啟動，等待語音就緒')
        except queue.Empty:
            pass
        if worker.app_process and not closing:
            log = target / 'agent.log'
            if log.exists():
                with log.open('rb') as stream:
                    stream.seek(log_offset); data = stream.read(16384); log_offset = stream.tell()
                text = data.decode('utf8', 'replace')
                for line in text.splitlines():
                    if 'ASR' in line or '校準' in line or '語音待命' in line:
                        append(line)
                    if '語音待命' in line:
                        status.set('中文語音已待命 · 說話後按右 Ctrl 執行')
                        progress.set('Ollama 與麥克風運作中')
                    elif any(token in line for token in ('模型載入失敗', '麥克風啟動失敗', '校準失敗')):
                        status.set('語音啟動失敗，請查看下方記錄及麥克風設定')
                if worker.app_process.poll() is not None:
                    status.set('GhostReflex 已結束；可按啟動重試，詳細內容見 agent.log')
                    start_button.configure(state='normal')
        root.after(200, tick)
    root.after(100, tick)
    if not args.no_auto:
        root.after(400, start)
    try:
        root.mainloop()
    finally:
        worker.close_all()
        kernel.CloseHandle(mutex)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        messagebox.showerror('GhostReflex', str(error))
        raise
