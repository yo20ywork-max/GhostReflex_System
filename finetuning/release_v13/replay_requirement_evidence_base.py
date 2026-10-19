"""Independent requirement/evidence contract on the same six captured cases."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from evaluate_development import request
from model_context import unpack

R = Path(__file__).resolve().parent
SOURCE = R / 'COMPLETION_FILE_FACTS_REPLAY.jsonl'
CANDIDATE = R / 'runtime-candidate/requirement_evidence_check.py'
spec = importlib.util.spec_from_file_location('requirement_evidence_check', CANDIDATE)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = R / 'REQUIREMENT_EVIDENCE_BASE_REPLAY.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    source_summary = json.loads(SOURCE.with_suffix('.summary.json').read_text(encoding='utf8'))
    assert source_summary['results_sha256'] == sha(SOURCE) and source_summary['rows'] == 12
    rows = [json.loads(line) for line in SOURCE.read_text(encoding='utf8').splitlines() if json.loads(line)['mode'] == 'baseline']
    assert len(rows) == 6
    model_name = 'qwen2.5-coder:7b'
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364'
    sources = {str(p): sha(p) for p in [Path(__file__), SOURCE, CANDIDATE, R.parents[1] / 'run_daemon.py', R.parents[1] / 'model_context.py']}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
           'context_and_options_unchanged': True, 'changes': ['checker system', 'requirement/evidence schema', 'validated aggregate verdict'],
           'actions_executed': False, 'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            context = json.loads(row['request']['messages'][1]['content'])
            if 'shared_context_text' in context:
                context = unpack(context)
            payload = candidate.request_payload(row['request'], context)
            payload['model'] = model_name
            began = time.monotonic()
            result = {'case': row['case'], 'expected_complete': row['expected_complete'], 'request': payload}
            try:
                response = request('/api/chat', payload)
                value = json.loads(response['message']['content'])
                assessment = candidate.validate(value, context)
                valid = response.get('done') is True and response.get('done_reason') == 'stop'
                result.update(response=response, generation_complete=valid, assessment=assessment,
                              correct=valid and assessment['complete'] is row['expected_complete'], checks=value['checks'])
            except Exception as exc:
                result.update(generation_complete=False, correct=False, error=str(exc))
            result['seconds'] = time.monotonic() - began
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response', 'checks')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    summary = {'rows': len(results), 'correct': sum(r['correct'] for r in results),
               'false_positives': sum(r.get('assessment', {}).get('complete') is True and not r['expected_complete'] for r in results),
               'sources_and_model_unchanged': stable, 'results_sha256': sha(target), 'semantic_review_required': True,
               'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    assert stable
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
