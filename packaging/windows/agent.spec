# Build with Python 3.12 and the versions recorded in BUILD_VERSIONS.json.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

root = Path(os.environ['GHOST_BUILD_SOURCE'])
datas = [(str(root / 'vocab.json'), '.'), (str(root / 'micro_glr_checkpoint.pt'), '.')]
binaries = []
hidden = ['pynput.keyboard._win32', 'pynput.mouse._win32', 'playwright.sync_api', 'scipy.signal', 'soundfile']
for package in ['funasr', 'sounddevice', 'opencc', 'pynput', 'kaldiio']:
    d, b, h = collect_all(package)
    datas += d; binaries += b; hidden += h
datas += collect_data_files('librosa')
for package in ['funasr', 'torch', 'torchaudio', 'numpy', 'omegaconf', 'hydra-core', 'librosa', 'soundfile']:
    datas += copy_metadata(package)
a = Analysis([str(root / 'packaging/windows/agent_entry.py')], pathex=[str(root)], datas=datas,
             binaries=binaries, hiddenimports=hidden,
             excludes=['tensorflow', 'tensorboard', 'jax', 'jaxlib', 'matplotlib', 'IPython', 'pytest',
                       'PySide6', 'PyQt5', 'PyQt6', 'pandas', 'sklearn', 'torchvision', 'triton', 'transformers',
                       'datasets', 'peft', 'onnxruntime', 'wandb', 'modelscope', 'bitsandbytes',
                       'diffusers', 'accelerate', 'lightning', 'pytorch_lightning', 'vllm', 'timm',
                       'sentence_transformers', 'boto3', 'oss2', 'aliyunsdkcore'], noarchive=False)
# Do not pick up ICU DLLs from the host's unrelated Codex runtime.
a.binaries = [entry for entry in a.binaries if not (Path(entry[0]).name.lower().startswith('icu') and 'codex-runtimes' in entry[1])]
a.datas = [entry for entry in a.datas if Path(entry[0]).name != 'direct_url.json']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='GhostReflex-Agent', console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='GhostReflex-Agent', upx=False)
