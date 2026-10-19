"""Check whether observed locator failures are directly taught by training labels."""
from collections import Counter
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent


def main():
    source = R / 'train.jsonl'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    assert lock['sha256']['train.jsonl'] == digest
    rows = list(map(json.loads, source.read_text(encoding='utf8').splitlines()))
    waits, preview_presses = [], []
    for row in rows:
        try:
            request, answer = json.loads(row['prompt']), json.loads(row['answer'])
        except (ValueError, KeyError):
            continue
        if not isinstance(answer, dict) or 'steps' not in answer:
            continue
        for step in answer['steps']:
            if step['tool'] == 'BROWSER_WAIT_FOR':
                args = step['args']
                waits.append({'id': row['id'], 'request': request['user_request'], 'args': args,
                              'target_verbatim_in_request': args['target'] in request['user_request'],
                              'answer_sha256': hashlib.sha256(row['answer'].encode()).hexdigest()})
            if step['tool'] == 'BROWSER_PRESS' and '預覽' in request['user_request']:
                preview_presses.append({'id': row['id'], 'request': request['user_request'], 'args': step['args']})
    assert len(waits) == 56
    assert all(row['target_verbatim_in_request'] for row in waits)
    assert not preview_presses
    report = {'train_sha256': digest, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'train_rows': len(rows), 'wait_action_count': len(waits),
              'locator_types': dict(Counter(row['args']['by'] for row in waits)),
              'all_wait_targets_verbatim_in_request': True, 'preview_press_labels': preview_presses,
              'records': waits,
              'manual_scope': 'All56 wait request/locator pairs inspected. Text targets use text; supplied CSS IDs use css. No invented CSS-ID wait label found. This does not audit all semantics or prove generalization.',
              'inference': 'The observed invented CSS IDs are not directly copied from these wait labels; weak transfer from examples remains possible. Native-backend comparison is still pending.',
              'training_modified': False, 'release_approved': False}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    with (R / 'TRAINING_LOCATOR_AUDIT.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
