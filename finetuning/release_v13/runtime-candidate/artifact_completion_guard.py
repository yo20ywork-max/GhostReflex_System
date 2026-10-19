"""Negative-only guard: a model cannot overrule contrary exact-file evidence.

This never promotes a task to complete. Artifact interpretation and remaining
semantic/operation/delivery checks are separate; there is no all-tasks guarantee.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('artifact_evidence_guard_input', Path(__file__).with_name('artifact_evidence.py'))
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def assess(value, prompt, history, verdict):
    if (not isinstance(verdict, dict) or type(verdict.get('complete')) is not bool
            or not isinstance(verdict.get('reason'), str)):
        raise ValueError('A complete valid checker response is required; no fallback success.')
    facts = evidence.build(value, prompt, history)
    blockers = []
    for artifact in facts['artifacts']:
        if artifact['kind'] == 'semantic_generation':
            continue  # Text equality cannot establish summary/code/creative quality.
        relation = artifact['content_relation']
        name = artifact['destination_name']
        if relation['status'] == 'text_different':
            diff = relation['comparison']['first_difference']
            blockers.append({'destination': name, 'kind': 'exact_text_mismatch',
                             'first_difference': diff,
                             'reason': f'「{name}」的完整讀回內容與要求的來源順序不符；首個差異在字元索引 {diff["character_index"]}。'})
        elif relation['status'] == 'unknown':
            blockers.append({'destination': name, 'kind': 'insufficient_exact_file_evidence',
                             'reason': f'「{name}」缺少可核對的完整來源／目的內容或對應的位元組複製證據。'})
        elif artifact.get('later_file_actions') or artifact.get('later_unclassified_actions'):
            blockers.append({'destination': name, 'kind': 'later_observation_requires_reconciliation',
                             'reason': f'「{name}」的比對證據之後還有相關檔案或未分類操作，須先核對後續狀態。'})
    return {'complete': False if blockers else verdict['complete'],
            'reason': ' '.join(b['reason'] for b in blockers) if blockers else verdict['reason'],
            'host_blockers': blockers, 'model_verdict': dict(verdict),
            'positive_completion_inferred_by_host': False}
