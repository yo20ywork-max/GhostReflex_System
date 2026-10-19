"""Necessary release checks against frozen binaries, not development Python imports."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.request
from engine import Installer, Job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--wav', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    reports = args.reports.resolve(); reports.mkdir(exist_ok=True)
    root = args.root.resolve()
    job = Job()
    worker = Installer(root, json.loads(args.manifest.read_text(encoding='utf8')), lambda *_: None, threading.Event(), job)
    results = {'frozen': True, 'cases': [], 'live_human_voice_test_this_build': False}
    try:
        worker.configure();worker.start_service()
        exe = str(worker.app / 'GhostReflex-Agent.exe')
        def run(name, command, timeout=240):
            log = reports / (name + '.log')
            with log.open('wb') as output:
                process = job.start(command, cwd=worker.app, env=worker.env, stdout=output, stderr=output)
                process.wait(timeout=timeout)
            text = log.read_text(encoding='utf8', errors='replace')
            results['cases'].append({'name':name,'exit_code':process.returncode,'log':log.name})
            if process.returncode:raise RuntimeError(name + ' failed: ' + text[-2000:])
            return text
        run('frozen-self-check', [exe, '--self-check'])
        run('frozen-chinese-asr', [exe, '--asr-check', str(args.wav.resolve()), '--result', str(reports/'asr-result.json')])
        asr = json.loads((reports/'asr-result.json').read_text(encoding='utf8'))
        expected = '請回答二加三等於多少'
        if re.sub(r'[^\w]', '', asr['normalized']) != expected:raise RuntimeError('Known Chinese speech did not match')
        results['known_chinese_synthetic_speech'] = asr
        text = run('frozen-math-dialogue', [exe, '--no-voice', '--text', '請回答二加三等於多少，只回答數字。'])
        if not re.search(r'(?m)^5\s*$',text):raise RuntimeError('Math response was not 5: '+text[-800:])
        results['math_response'] = '5'
        run('frozen-greeting-dialogue', [exe, '--no-voice', '--text', '你好'])
        completions=[]
        for file in (root/'logs').glob('ghostreflex_*.jsonl'):
            for line in file.read_text(encoding='utf8').splitlines():
                event=json.loads(line)
                if event.get('event')=='request_complete':completions.append(event)
        if len(completions)<2 or any(event.get('status')!='completed' for event in completions[-2:]):
            raise RuntimeError('Dialogue completion receipts did not pass')
        if completions[-1].get('plan_model') != 'deterministic:greeting':
            raise RuntimeError('Pure greeting must not dispatch a desktop plan')
        results['dialogue_completion_receipts']=completions[-2:]
        # Actual normal GUI/VoiceEngine path opens the default microphone and calibrates.
        log = root / 'agent.log'
        offset = log.stat().st_size if log.exists() else 0
        worker.launch()
        ready = False
        began = time.monotonic()
        while time.monotonic()-began < 180:
            if worker.app_process.poll() is not None:raise RuntimeError('Voice GUI exited early')
            if log.exists():
                with log.open('rb') as stream:
                    stream.seek(offset);tail=stream.read().decode('utf8','replace')
                if '語音待命' in tail:
                    ready = True;break
                if any(value in tail for value in ('模型載入失敗','麥克風啟動失敗','校準失敗')):
                    raise RuntimeError(tail[-2000:])
            time.sleep(.5)
        if not ready:raise RuntimeError('Microphone readiness timeout')
        results['microphone_calibrated_and_ready'] = True
        results['owned_voice_pid'] = worker.app_process.pid
        results['owned_ollama_pid'] = worker.service.pid
        with urllib.request.urlopen(worker.host+'/api/ps',timeout=10) as response: results['loaded_models']=json.load(response)
        results['status']='passed'
    except Exception as exc:
        results['status']='failed';results['error']=str(exc)
        raise
    finally:
        worker.close_all()
        results['owned_processes_stopped']=all(process.poll() is not None for process in job.children)
        (reports/'FROZEN_VERIFICATION.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')


if __name__ == '__main__':main()
