"""Add terminal-status accounting without changing the frozen fixture oracle."""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(report):
    records = report['records']
    if len({row['id'] for row in records}) != len(records):
        raise ValueError('Duplicate case IDs')
    for row in records:
        if type(row.get('passed')) is not bool or 'agent_status' not in row:
            raise ValueError('Expected full-loop records with oracle and terminal status')
        if row['agent_status'] is None:
            if row['passed'] or not row.get('error'):
                raise ValueError('A plan rejected before execution must record failure and its error')
        elif not isinstance(row['agent_status'], str) or not row['agent_status']:
            raise ValueError('Invalid terminal status')
    oracle = sum(row['passed'] for row in records)
    completed = sum(row['agent_status'] == 'completed' for row in records)
    false_completion = sum(not row['passed'] and row['agent_status'] == 'completed' for row in records)
    if (report['total'], report['passed'], report['agent_completed'], report['false_completions']) != (len(records), oracle, completed, false_completion):
        raise ValueError('Stored totals disagree with records')
    return {
        'total': len(records),
        'original_oracle_passed': oracle,
        'agent_completed': completed,
        'joint_oracle_and_completed': sum(row['passed'] and row['agent_status'] == 'completed' for row in records),
        'completed_but_original_oracle_failed': false_completion,
        'oracle_passed_but_agent_not_completed': [row['id'] for row in records if row['passed'] and row['agent_status'] != 'completed'],
        'rejected_before_agent_run': [row['id'] for row in records if row['agent_status'] is None],
        'records': [{'id': row['id'], 'original_oracle_passed': row['passed'], 'agent_status': row['agent_status'], 'joint_passed': row['passed'] and row['agent_status'] == 'completed'} for row in records],
        'interpretation': 'The original oracle checks both outcome and trace shape. Its failures are not all harmful actions. Joint count additionally requires completed terminal status; it is not a release approval or native desktop test.',
        'original_oracle_unchanged': True,
        'release_approved': False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    result = summarize(json.loads(raw))
    result.update(source=str(args.input.resolve()), source_sha256=hashlib.sha256(raw).hexdigest())
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
