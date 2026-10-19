"""Bounded, resumable per-user installer and owned Windows process lifecycle."""
import ctypes
from ctypes import wintypes
import hashlib
import html.parser
import http.cookiejar
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile


class Cancelled(Exception): pass


def check(cancel):
    if cancel.is_set(): raise Cancelled('已停止。再次安裝時會續傳已下載的檔案。')


def digest(path, cancel=None):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            if cancel: check(cancel)
            h.update(block)
    return h.hexdigest()


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise RuntimeError('下載重新導向未使用 HTTPS。')
        if urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            new.remove_header('Authorization')
        return new


def resolve_drive(file_id, cancel):
    """Follow Google's public download confirmation form without forwarding credentials."""
    class Form(html.parser.HTMLParser):
        def __init__(self):super().__init__();self.action='';self.fields={};self.active=False
        def handle_starttag(self,tag,attributes):
            a=dict(attributes)
            if tag=='form' and a.get('id')=='download-form':self.action=a.get('action','');self.active=True
            if tag=='input' and self.active and a.get('name'):self.fields[a['name']]=a.get('value','')
        def handle_endtag(self,tag):
            if tag=='form':self.active=False
    opener=urllib.request.build_opener(SafeRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    url='https://drive.google.com/uc?'+urllib.parse.urlencode({'export':'download','id':file_id})
    for _ in range(3):
        check(cancel)
        with opener.open(url,timeout=20) as response:
            if 'text/html' not in response.headers.get('Content-Type',''):return response.url,opener
            body_text=response.read(512_000).decode('utf8','replace')
        form=Form();form.feed(body_text)
        if urllib.parse.urlparse(form.action).hostname not in ('drive.google.com','drive.usercontent.google.com'):
            raise RuntimeError('Google Drive 檔案無法直接下載，請確認資料夾權限或稍後重試。')
        url=form.action+'?'+urllib.parse.urlencode(form.fields)
    raise RuntimeError('Google Drive 下載確認未完成。')


def download(item, path, cancel, progress, token=None, opener=None):
    """A final file is reused only after SHA verification; incomplete bytes are resumable."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    size, expected = item['bytes'], item['sha256']
    if path.is_file() and path.stat().st_size == size and digest(path, cancel) == expected:
        progress(size, size); return
    part = path.with_name(path.name + '.part')
    if part.exists() and part.stat().st_size > size: part.unlink()
    if part.exists() and part.stat().st_size == size:
        if digest(part, cancel) == expected: os.replace(part, path); return
        part.unlink()
    opener = opener or urllib.request.build_opener(SafeRedirect())
    for attempt in range(5):
        check(cancel)
        start = part.stat().st_size if part.exists() else 0
        headers = {'User-Agent': 'GhostReflex-Setup/0.1', 'Accept-Encoding': 'identity'}
        if token and urllib.parse.urlparse(item['url']).hostname == 'huggingface.co':
            headers['Authorization'] = 'Bearer ' + token()
        if start: headers['Range'] = f'bytes={start}-'
        try:
            with opener.open(urllib.request.Request(item['url'], headers=headers), timeout=20) as response:
                if response.status == 206:
                    content_range = response.headers.get('Content-Range', '')
                    if not content_range.startswith(f'bytes {start}-') or not content_range.endswith('/'+str(size)):
                        raise RuntimeError('續傳範圍不一致，未寫入檔案。')
                elif response.status == 200: start = 0
                else: raise RuntimeError('下載伺服器回應異常。')
                with part.open('ab' if start else 'wb') as output:
                    count = start
                    while True:
                        check(cancel)
                        block = response.read(1024*1024)
                        if not block: break
                        count += len(block)
                        if count > size: raise RuntimeError('下載大小超過預期。')
                        output.write(block); progress(count, size)
            if part.stat().st_size != size: raise OSError('下載中斷')
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403): raise RuntimeError('公開下載暫時無法存取，請檢查網路後重試。') from None
            if exc.code == 416 and part.exists(): part.unlink()
            if attempt == 4: raise RuntimeError(f'下載失敗（HTTP {exc.code}），可按安裝重試。') from None
            if cancel.wait(min(2**attempt, 10)): check(cancel)
        except (OSError, TimeoutError, urllib.error.URLError):
            if attempt == 4: raise RuntimeError('網路中斷，已保留續傳檔案，請按安裝重試。') from None
            if cancel.wait(min(2**attempt, 10)): check(cancel)
    check(cancel)
    if digest(part, cancel) != expected:
        part.unlink()
        raise RuntimeError('下載檔案校驗失敗，請重新安裝以再次下載。')
    os.replace(part, path)


def extract(archive, destination, cancel, prefix='', limit=8_000_000_000):
    destination = Path(destination).resolve(); destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        items = source.infolist()
        if sum(i.file_size for i in items) > limit: raise ValueError('解壓縮大小超過限制。')
        seen = set()
        for item in items:
            name = item.filename
            if prefix:
                if not name.startswith(prefix): raise ValueError('壓縮包根目錄不符。')
                name = name[len(prefix):]
            if not name: continue
            parts = PurePosixPath(name).parts
            if '\\' in name or ':' in name or name.startswith('/') or any(p in ('..', '.') for p in parts):
                raise ValueError('壓縮包含不安全路徑。')
            if (item.external_attr >> 16) & 0o170000 == 0o120000: raise ValueError('壓縮包含符號連結。')
            target = destination.joinpath(*parts)
            if not target.resolve().is_relative_to(destination): raise ValueError('解壓縮超出安裝目錄。')
            key = str(target).casefold()
            if key in seen: raise ValueError('壓縮包含重複路徑。')
            seen.add(key)
        for item in items:
            check(cancel)
            name = item.filename[len(prefix):] if prefix else item.filename
            if not name: continue
            target = destination.joinpath(*PurePosixPath(name).parts)
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as src, target.open('wb') as dst:
                while True:
                    check(cancel); block = src.read(1024*1024)
                    if not block: break
                    dst.write(block)


class Job:
    """Only children assigned to this job, and their descendants, are terminated."""
    def __init__(self):
        from ctypes import c_ulonglong, c_size_t, c_longlong
        class Basic(ctypes.Structure):
            _fields_ = [('ProcessTime', c_longlong), ('JobTime', c_longlong), ('Flags', wintypes.DWORD),
                        ('MinWorkingSet', c_size_t), ('MaxWorkingSet', c_size_t), ('ActiveLimit', wintypes.DWORD),
                        ('Affinity', c_size_t), ('Priority', wintypes.DWORD), ('Scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name,c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('Basic',Basic),('IO',IO),('ProcessMemory',c_size_t),('JobMemory',c_size_t),('PeakProcess',c_size_t),('PeakJob',c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE,wintypes.UINT]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
        info = Extended(); info.Basic.Flags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.lock = threading.Lock(); self.children = []; self.closed = False

    def start(self, command, **kwargs):
        with self.lock:
            if self.closed: raise Cancelled('背景工作已停止。')
            process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW, **kwargs)
            if not self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))):
                process.terminate(); process.wait()
                raise ctypes.WinError(ctypes.get_last_error())
            self.children.append(process)
            return process

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed = True
            self.kernel.TerminateJobObject(self.handle, 1)
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        for process in self.children:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass


class Installer:
    def __init__(self, root, config, notify, cancel, job, token=None, runtime_override=None):
        self.root = Path(root).resolve(); self.config = config; self.notify = notify
        self.cancel = cancel; self.job = job; self.token = token; self.runtime_override = runtime_override
        self.app = self.root / 'app'; self.cache = self.root / 'downloads'
        self.runtime = self.root / 'runtime'; self.store = self.root / 'model-store'
        self.env = {k:v for k,v in os.environ.items() if k not in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN','PYTHONHOME','PYTHONPATH')}
        self.service = None; self.app_process = None
        self.cache.mkdir(parents=True, exist_ok=True)

    def step(self, text):check(self.cancel); self.notify('status', text)

    def fetch(self, item, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        self.step('下載／校驗 ' + item.get('label',path.name))
        if path.is_file() and path.stat().st_size==item['bytes'] and digest(path,self.cancel)==item['sha256']:
            self.notify('progress',(item['bytes'],item['bytes']));return
        if item.get('parts'):
            parts=[]
            for index,part in enumerate(item['parts']):
                local=self.cache/f'{item["sha256"][:16]}-part-{index:02d}.bin';self.fetch(part,local);parts.append(local)
            self.step('合併與校驗程式資料')
            combined=path.with_name(path.name+'.part')
            with combined.open('wb') as output:
                for part in parts:
                    with part.open('rb') as source:
                        while True:
                            check(self.cancel);block=source.read(1024*1024)
                            if not block:break
                            output.write(block)
            if combined.stat().st_size!=item['bytes'] or digest(combined,self.cancel)!=item['sha256']:
                combined.unlink();raise RuntimeError('程式分檔合併校驗失敗。')
            os.replace(combined,path)
            for part in parts:part.unlink()
            return
        opener=None
        if item.get('drive_id'):
            item=dict(item);item['url'],opener=resolve_drive(item['drive_id'],self.cancel)
        download(item, path, self.cancel, lambda n,total:self.notify('progress', (n,total)), self.token,opener)

    def run(self, command, timeout=900, cwd=None):
        check(self.cancel)
        # Account secrets never enter subprocess environments or command lines.
        environment = {k:v for k,v in self.env.items() if k not in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN')}
        process = self.job.start(command, cwd=cwd or self.root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tail = bytearray()
        def consume():
            while True:
                block = process.stdout.read(4096)
                if not block:break
                tail.extend(block)
                if len(tail)>8000:del tail[:-8000]
        reader = threading.Thread(target=consume,daemon=True);reader.start()
        began=time.monotonic()
        while process.poll() is None:
            check(self.cancel)
            if time.monotonic()-began > timeout:
                process.terminate();raise RuntimeError('此步驟逾時，請重試。')
            self.cancel.wait(0.1)
        reader.join(3);process.stdout.close();check(self.cancel)
        if process.returncode:
            message=tail.decode('utf8','replace')[-1600:]
            raise RuntimeError('步驟未完成：' + message)

    def start_service(self):
        check(self.cancel)
        if self.service and self.service.poll() is None:return
        exe = Path(self.runtime_override) if self.runtime_override else self.runtime/'ollama.exe'
        if not exe.is_file(): raise RuntimeError('模型執行元件尚未安裝，請先按自動安裝。')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port=sock.getsockname()[1]
        self.host=f'http://127.0.0.1:{port}'
        self.env.update(OLLAMA_HOST=self.host, OLLAMA_MODELS=str(self.store), OLLAMA_NO_CLOUD='1',
                        OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_CONTEXT_LENGTH='12288',
                        OLLAMA_FLASH_ATTENTION='1', OLLAMA_KV_CACHE_TYPE='q8_0', OLLAMA_KEEP_ALIVE='15m')
        log=(self.root/'model-service.log').open('ab')
        try:self.service=self.job.start([str(exe),'serve'],env=self.env,stdout=log,stderr=log)
        finally:log.close()
        for _ in range(120):
            check(self.cancel)
            if self.service.poll() is not None:raise RuntimeError('模型服務啟動失敗，請查看 model-service.log。')
            try:
                with urllib.request.urlopen(self.host+'/api/version',timeout=1) as response:
                    json.load(response);return
            except (OSError,ValueError):self.cancel.wait(0.5)
        raise RuntimeError('等候模型服務啟動逾時。')

    def archive(self, key, destination, sentinel, limit):
        item=self.config[key]; marker=self.root/(key+'-installed.json')
        try: installed=json.loads(marker.read_text(encoding='utf8'))
        except (OSError, ValueError): installed={}
        if installed.get('sha256')==item['sha256'] and sentinel.is_file():return
        local=self.cache/(key+'.zip');self.fetch(item,local)
        self.step('解壓縮 '+item['label'])
        extract(local,destination,self.cancel,limit=limit)
        if not sentinel.is_file():raise RuntimeError('安裝內容不完整：'+key)
        marker.write_text(json.dumps({'sha256':item['sha256']}),encoding='utf8')
        local.unlink()

    def configure(self):
        workspace=self.root/'workspace';workspace.mkdir(exist_ok=True)
        windows=Path(os.environ.get('WINDIR','C:/Windows'))
        # Resolve bundled components and Windows tools without a host Python/Ollama installation.
        self.env['PATH']=os.pathsep.join(str(path) for path in [self.runtime,self.runtime/'lib/ollama',
            windows/'System32',windows,windows/'System32/Wbem',windows/'System32/WindowsPowerShell/v1.0'])
        self.env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
            GHOST_WORKSPACE=str(workspace), GHOST_LOG_DIR=str(self.root/'logs'),
            GHOST_BROWSER_PROFILE=str(self.root/'browser-profile'),
            GHOST_CONTEXT_CLIPBOARD='0', GHOST_ENABLE_VOICE='1', GHOST_VOICE_AUTO_EXECUTE='0', GHOST_ENABLE_PLAYWRIGHT='1',
            GHOST_ASR_MODEL=str(self.app/'models/paraformer-zh'), GHOST_ASR_HUB='ms',
            HF_HUB_OFFLINE='1', MODELSCOPE_OFFLINE='1',
            GHOST_PLANNER_MODELS=','.join(self.config.get('planner_models',['qwen2.5-coder:7b','ghost-brain'])), GHOST_VISION_MODELS='',
            GHOST_ALLOW_SHELL='0', GHOST_ALLOW_OUTSIDE_WORKSPACE='0', GHOST_AUTO_APPROVE_HIGH_RISK='0',
            PLAYWRIGHT_BROWSERS_PATH=str(self.root/'browsers'))

    def install(self, skip_space_check=False):
        self.step('檢查安裝空間')
        if not skip_space_check and shutil.disk_usage(self.root).free < 25_000_000_000:
            raise RuntimeError('請在安裝磁碟保留至少25GB可用空間。')
        self.configure()
        self.archive('app',self.app,self.app/'GhostReflex-Agent.exe',4_000_000_000)
        self.archive('speech',self.app/'models/paraformer-zh',self.app/'models/paraformer-zh/model.pt',1_200_000_000)
        if not self.runtime_override:self.archive('ollama',self.runtime,self.runtime/'ollama.exe',8_000_000_000)
        model=self.config['base'];blob=self.store/'blobs'/('sha256-'+model['sha256'])
        self.fetch(model,blob)
        self.archive('manifests',self.store,self.store/'manifests/registry.ollama.ai/library/ghost-brain/latest',1_000_000)
        self.step('啟動獨立模型服務');self.start_service()
        self.step('安裝瀏覽器元件')
        self.run([str(self.app/'_internal/playwright/driver/node.exe'),str(self.app/'_internal/playwright/driver/package/cli.js'),'install','chromium'],timeout=1800)
        self.step('檢查程式與模型')
        self.run([str(self.app/'GhostReflex-Agent.exe'),'--self-check'],timeout=180)
        with urllib.request.urlopen(self.host+'/api/tags',timeout=10) as response:tags=json.load(response)['models']
        if not {'ghost-brain:latest','qwen2.5-coder:7b'}.issubset({t['name'] for t in tags}):
            raise RuntimeError('模型安裝後核對失敗。')
        (self.root/'installed.json').write_text(json.dumps({'version':self.config['version'],'completed':True}),encoding='utf8')
        self.step('安裝完成')

    def launch(self):
        if not (self.root/'installed.json').exists():raise RuntimeError('請先完成自動安裝。')
        self.configure();self.start_service();check(self.cancel)
        if self.app_process and self.app_process.poll() is None:return
        log=(self.root/'agent.log').open('ab')
        try:self.app_process=self.job.start([str(self.app/'GhostReflex-Agent.exe')],cwd=self.app,env=self.env,stdout=log,stderr=log)
        finally:log.close()

    def close_all(self):
        self.cancel.set()
        if self.app_process and self.app_process.poll() is None:
            pid=self.app_process.pid
            callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            def close_window(hwnd, _):
                window_pid=wintypes.DWORD();ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(window_pid))
                if window_pid.value==pid:ctypes.windll.user32.PostMessageW(hwnd,0x0010,0,0)
                return True
            ctypes.windll.user32.EnumWindows(callback(close_window),0)
            try:self.app_process.wait(timeout=4)
            except subprocess.TimeoutExpired:pass
        self.job.close()
