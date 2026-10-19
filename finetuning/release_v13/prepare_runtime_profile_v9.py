"""Freeze integrity preflight and preserve prior questions/oracles/schemas."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old = R / 'evaluation-runtime-v8'
    manifest = json.loads((old / 'manifest.json').read_text(encoding='utf8'))
    before = R / 'runtime-v8-sources/run_daemon.py'
    assert sha(before) == manifest['source_hashes']['run_daemon.py']
    for name, digest in manifest['source_hashes'].items():
        if name != 'run_daemon.py':
            assert sha(ROOT / name) == digest, name
    previous = ast.parse(before.read_text(encoding='utf-8-sig'))
    current = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
    # All code outside the gateway and the explicit per-task reset is identical.
    for tree in [previous, current]:
        tree.body = [n for n in tree.body if getattr(n, 'name', '') != 'OllamaGateway']
    agent = next(n for n in current.body if getattr(n, 'name', '') == 'UniversalAgent')
    run = next(n for n in agent.body if getattr(n, 'name', '') == 'run')
    run.body = [n for n in run.body if not (
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'begin_task' for t in n.targets)
        or isinstance(n, ast.If) and isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Name)
        and n.test.func.id == 'callable' and any(isinstance(a, ast.Name) and a.id == 'begin_task' for a in n.test.args))]
    assert ast.dump(previous) == ast.dump(current)
    record = {'installed_utc': datetime.now(timezone.utc).isoformat(), 'before_sha256': sha(before),
              'after_sha256': sha(ROOT / 'run_daemon.py'),
              'new_modules': {n: sha(ROOT / n) for n in ['model_blob_integrity.py', 'ollama_model_integrity.py']},
              'tests_run': 52, 'observed_test_exit_codes': [0, 0],
              'test_groups': {'integrity_and_gateway': 22, 'planner_sources_generation_ui_compatibility': 30},
              'test_sources': {n: sha(ROOT / 'tests' / n) for n in ['test_model_blob_integrity.py', 'test_gateway_model_integrity.py', 'test_gateway_completion.py']},
              'scope': 'Local disk bytes before first model use per task; no loaded-memory or answer correctness claim. Remote backends cannot be locally attested.',
              'release_approved': False}
    with (R / 'MODEL_INTEGRITY_INSTALL.json').open('x', encoding='utf8') as f:
        json.dump(record, f, indent=2)
    destination, snapshot = R / 'evaluation-runtime-v9', R / 'runtime-v9-sources'
    destination.mkdir(exist_ok=False); snapshot.mkdir(exist_ok=False)
    for name in ['run_daemon.py', 'model_blob_integrity.py', 'ollama_model_integrity.py']:
        (snapshot / name).write_bytes((ROOT / name).read_bytes())
    runners = []
    for source in sorted(R.glob('*_runtime_v8.py')):
        target = source.with_name(source.name.replace('_runtime_v8', '_runtime_v9'))
        code = source.read_text(encoding='utf8').replace('evaluation-runtime-v8', 'evaluation-runtime-v9').replace('_runtime_v8', '_runtime_v9')
        # New /api/tags reads must not be counted as generations or overwrite a
        # captured chat response. This preserves the existing inference budget.
        code = code.replace("def sent(req):calls.append({'request':json.loads(req.content)})",
                            "def sent(req):\n        if req.url.path == '/api/chat': calls.append({'request':json.loads(req.content)})")
        code = code.replace("def sent(req):\n        calls.append", "def sent(req):\n        if req.url.path != '/api/chat': return\n        calls.append")
        code = code.replace('def received(resp):\n', "def received(resp):\n        if resp.request.url.path != '/api/chat': return\n")
        code = code.replace("lambda req:sent.append(json.loads(req.content))", "lambda req:sent.append(json.loads(req.content)) if req.url.path == '/api/chat' else None")
        code = code.replace('def response_hook(response):\n', "def response_hook(response):\n        if response.request.url.path != '/api/chat': return\n")
        if source.name == 'evaluate_file_tasks_text_runtime_v8.py':
            code = code.replace("rows=cases();assert len(rows)==8", "integrity_before = gateway.integrity.ensure(args.model)\n    rows=cases();assert len(rows)==8")
            code = code.replace("manifest={'model':model,", "manifest={'model_integrity_before':integrity_before,'model':model,")
            code = code.replace('class BoundedGateway:\n', 'class BoundedGateway:\n                    def begin_task(self): gateway.begin_task()\n')
            code = code.replace("summary={'total':8,", "from model_blob_integrity import verify_manifest\n    integrity_after = verify_manifest(integrity_before['manifest'], gateway.integrity.root / 'blobs', model['digest'])\n    summary={'model_integrity_after':integrity_after,'total':8,")
        compile(code, str(target), 'exec')
        with target.open('x', encoding='utf8', newline='\n') as f:
            f.write(code)
        runners.append({'old': source.name, 'old_sha256': sha(source), 'new': target.name, 'new_sha256': sha(target)})
    for name, digest in manifest['outputs'].items():
        assert sha(old / name) == digest
        (destination / name).write_bytes((old / name).read_bytes())
    for path in [ROOT / 'run_daemon.py', ROOT / 'model_blob_integrity.py', ROOT / 'ollama_model_integrity.py', Path(__file__), R / 'MODEL_INTEGRITY_INSTALL.json']:
        manifest['source_hashes'][str(path.relative_to(ROOT))] = sha(path)
    manifest.update(profile_name='evaluation-runtime-v9', predecessor_manifest_sha256=sha(old / 'manifest.json'),
                    runtime_change='Verify actual local model files before model use, cache within task only. No tool, prompt, schema or oracle changes.')
    with (destination / 'manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with (destination / 'PROFILE_PREPARATION.json').open('x', encoding='utf8') as f:
        json.dump({'runners': runners, 'questions_answers_oracles_schemas_byte_identical': True,
                   'runner_changes': 'Output paths/imports; filter chat-only capture; file8 task reset and actual-blob pre/post receipts.',
                   'release_approved': False}, f, indent=2)
    print(json.dumps(record))


if __name__ == '__main__':
    main()
