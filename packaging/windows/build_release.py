"""Bounded release asset builder. Does not train or modify model weights."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import threading
import urllib.request
import zipfile
from engine import digest, download

REPO = 'yo20ywork-max/GhostReflex_System'
VERSION = 'v0.1.0-windows-20261019'
BASE = '60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463'


def zip_tree(folder, output, selected=None):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for file in (selected or sorted(folder.rglob('*'))):
            if file.is_file() and file.name != 'direct_url.json':
                archive.write(file, file.relative_to(folder).as_posix())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'models', 'app', 'manifest'])
    parser.add_argument('--local', type=Path, required=True)
    parser.add_argument('--delivery', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    local = args.local.resolve()
    delivery = args.delivery.resolve()
    release = delivery / 'release'; work = delivery / 'work'; reports = delivery / 'reports'
    for path in [release, work, reports]: path.mkdir(parents=True, exist_ok=True)
    if args.phase == 'prepare':
        snapshot = work / 'source'; snapshot.mkdir(exist_ok=True)
        for file in source.glob('*.py'):
            shutil.copy2(file, snapshot / file.name)
        for name in ['vocab.json', 'micro_glr_checkpoint.pt']:
            shutil.copy2(source / name, snapshot / name)
        shutil.copytree(source / 'packaging', snapshot / 'packaging', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        versions = {name: metadata.version(name) for name in ['pyinstaller', 'torch', 'torchaudio', 'funasr', 'numpy', 'sounddevice', 'ollama', 'playwright', 'opencc-python-reimplemented']}
        (reports / 'BUILD_VERSIONS.json').write_text(json.dumps(versions, indent=2), encoding='utf8')
        inventory = {p.relative_to(snapshot).as_posix(): digest(p) for p in snapshot.rglob('*') if p.is_file()}
        (reports / 'BUILD_SOURCE_SHA256.json').write_text(json.dumps(inventory, indent=2), encoding='utf8')
    elif args.phase == 'models':
        store = local / 'dist/GhostReflex_Portable/ollama_models'
        base = store / 'blobs' / ('sha256-' + BASE)
        if digest(base) != BASE: raise RuntimeError('Base model digest mismatch')
        with base.open('rb') as stream:
            for index in range(1, 4):
                target = release / f'GhostReflex-Model.part{index:02d}'
                with target.open('wb') as output:
                    remaining = 1_600_000_000
                    while remaining:
                        block = stream.read(min(4*1024*1024, remaining))
                        if not block: break
                        output.write(block); remaining -= len(block)
        selected = set()
        for name in ['ghost-brain/latest', 'qwen2.5-coder/7b']:
            manifest = store / 'manifests/registry.ollama.ai/library' / name
            selected.add(manifest)
            value = json.loads(manifest.read_text())
            for blob in [value['config'], *value['layers']]:
                sha = blob['digest'].split(':')[1]
                file = store / 'blobs' / ('sha256-' + sha)
                if file.stat().st_size != blob['size'] or digest(file) != sha:
                    raise RuntimeError('Model blob mismatch: ' + sha)
                if sha != BASE: selected.add(file)
        zip_tree(store, release / 'GhostReflex-Model-Manifests.zip', sorted(selected))
        speech = local / 'dist/GhostReflex_Portable/models/paraformer-zh'
        names = ['model.pt','config.yaml','configuration.json','am.mvn','seg_dict','tokens.json','README.md']
        zip_tree(speech, release / 'GhostReflex-Chinese-ASR.zip', [speech / name for name in names])
        runtime = {'url': 'https://github.com/ollama/ollama/releases/download/v0.32.9/ollama-windows-amd64.zip',
                   'bytes': 1459368267, 'sha256': '7b4f6ce09c1f2c3b21561b323779beaf3ca3c7012f8e4522605a13cbbb19f0b8'}
        download(runtime, work / 'ollama-windows-amd64.zip', threading.Event(), lambda *_: None)
        (reports / 'OLLAMA_OFFICIAL_ASSET.json').write_text(json.dumps(runtime, indent=2), encoding='utf8')
    elif args.phase == 'app':
        app = work / 'dist/GhostReflex-Agent'
        # These files are looked up relative to the executable by the current source.
        for name in ['vocab.json','micro_glr_checkpoint.pt']:
            shutil.copy2(source / name, app / name)
        notices = app / 'THIRD_PARTY_NOTICES'; notices.mkdir(exist_ok=True)
        shutil.copy2(source / 'LICENSE', app / 'LICENSE.txt')
        shutil.copy2(Path(__import__('sys').base_prefix) / 'LICENSE.txt', notices / 'PYTHON-LICENSE.txt')
        for name in ['THIRD_PARTY_NOTICES.md', 'OLLAMA-LICENSE.txt', 'APACHE-2.0.txt']:
            shutil.copy2(source / 'packaging/windows/notices' / name, notices / name)
        for distribution in metadata.distributions():
            for file in distribution.files or []:
                name = str(file).replace('\\', '/')
                if '.dist-info/' not in name or not any(piece.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')) for piece in file.parts):
                    continue
                package = distribution.metadata.get('Name','unknown')
                destination = notices / package / file.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                try: shutil.copy2(distribution.locate_file(file), destination)
                except OSError: pass
        zip_tree(app, release / 'GhostReflex-App.zip')
    elif args.phase == 'manifest':
        url = f'https://github.com/{REPO}/releases/download/{VERSION}/'
        def asset(name, label):
            file = release / name
            return {'label': label, 'url': url + name, 'bytes': file.stat().st_size, 'sha256': digest(file)}
        config = {'version': VERSION, 'repository': REPO, 'planner_models': ['qwen2.5-coder:7b','ghost-brain'],
                  'app': asset('GhostReflex-App.zip','GhostReflex 主程式'),
                  'speech': asset('GhostReflex-Chinese-ASR.zip','Paraformer 中文語音模型'),
                  'manifests': asset('GhostReflex-Model-Manifests.zip','模型清單與必要授權'),
                  'base': {'label':'GhostReflex 對話模型','bytes':4683074048,'sha256':BASE,
                           'parts':[asset(f'GhostReflex-Model.part{i:02d}', f'對話模型分檔 {i}/3') for i in range(1,4)]},
                  'ollama': json.loads((reports / 'OLLAMA_OFFICIAL_ASSET.json').read_text())}
        config['ollama']['label'] = 'Ollama 0.32.9 Windows 執行環境'
        (release / 'release.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf8')
    print(args.phase + ' complete', flush=True)


if __name__ == '__main__': main()
