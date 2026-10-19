"""Outcome-blind operation obligations and negative-only historical verification.

Requirement interpretation remains model-dependent. Grounded quotes do not
prove interpretation or coverage. This module never declares a task complete.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path

from jsonschema import Draft202012Validator
from text_reader import completed_file_contents

spec = importlib.util.spec_from_file_location('operation_obligation_evidence', Path(__file__).with_name('artifact_evidence.py'))
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)

FIELDS = ['preserve_sources', 'new_destination', 'destination_readback', 'read_sources_before_write']
SYSTEM = (
    '只依 user_request、files 路徑目錄及已解讀的 artifacts，列出使用者的檔案操作義務；你看不到執行結果，不判定完成。'
    '每個 artifact_id 都要列一筆。preserve_sources 是不得修改來源；new_destination 是結果必須新建而非覆寫；'
    'destination_readback 是寫入後必須讀回目的；read_sources_before_write 是建立結果前必須讀來源。'
    '每項含 requirement 與 request_quote。明確要求填 required，沒有這項要求或明確允許不做填 not_required，'
    '條件式、矛盾、指涉不清或無法表達填 conditional_or_unclear。request_quote 必須逐字引用原要求的連續片段；not_required可填空字串。'
    '不要把「不必讀回」判成必須讀回，也不要把「允許修改來源」判成來源不可改。'
    'final_reply 含 mode、text、request_quote；指定逐字回覆填 exact 並照抄 text；只要求說明填 semantic；'
    '不要求回覆填 not_required；分支依結果決定回覆填 conditional_or_unclear。只有exact可有非空text。'
    'reply_after_readback 表示原要求限定回覆在讀回之後，格式與其他requirement相同。'
    '其他無法以以上欄位表達的操作要求，包含條件分支、指定其他App動作、特別讀取順序、等待、額外對象或禁止讀取，'
    '逐字放入 other_operation_requirements；不能悄悄省略。摘要/翻譯/程式內容品質及原樣複製/串接的內容與來源順序由artifact內容核對處理，不放入其他操作要求。'
    '不要增加原要求沒有的流程。只輸出artifact_obligations、final_reply、reply_after_readback、other_operation_requirements的JSON。'
)


def schema(artifact_count):
    requirement = {'type': 'object', 'properties': {
        'requirement': {'type': 'string', 'enum': ['required', 'not_required', 'conditional_or_unclear']},
        'request_quote': {'type': 'string'}}, 'required': ['requirement', 'request_quote'], 'additionalProperties': False}
    item = {'type': 'object', 'properties': {'artifact_id': {'type': 'string', 'enum': [f'a{i}' for i in range(1, artifact_count + 1)] or ['none']},
                                            **{field: copy.deepcopy(requirement) for field in FIELDS}},
            'required': ['artifact_id', *FIELDS], 'additionalProperties': False}
    return {'type': 'object', 'properties': {
        'artifact_obligations': {'type': 'array', 'minItems': artifact_count, 'maxItems': artifact_count, 'items': item},
        'final_reply': {'type': 'object', 'properties': {
            'mode': {'type': 'string', 'enum': ['exact', 'semantic', 'not_required', 'conditional_or_unclear']},
            'text': {'type': 'string'}, 'request_quote': {'type': 'string'}},
            'required': ['mode', 'text', 'request_quote'], 'additionalProperties': False},
        'reply_after_readback': requirement,
        'other_operation_requirements': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}},
        'required': ['artifact_obligations', 'final_reply', 'reply_after_readback', 'other_operation_requirements'],
        'additionalProperties': False}


def compiler_context(artifact_value, prompt, catalog):
    bound = evidence.intent.bind(artifact_value, prompt, catalog)
    return {'user_request': prompt, 'files': copy.deepcopy(catalog),
            'artifacts': [{'artifact_id': f'a{i}', **a} for i, a in enumerate(bound['artifacts'], 1)]}


def bind(value, artifact_value, prompt, catalog):
    context = compiler_context(artifact_value, prompt, catalog)
    Draft202012Validator(schema(len(context['artifacts']))).validate(value)
    actual_ids = [a['artifact_id'] for a in value['artifact_obligations']]
    if set(actual_ids) != {a['artifact_id'] for a in context['artifacts']} or len(set(actual_ids)) != len(actual_ids):
        raise ValueError('Every interpreted artifact needs exactly one obligation record')
    requirements = [r[field] for r in value['artifact_obligations'] for field in FIELDS] + [value['reply_after_readback']]
    for item in requirements:
        quote = item['request_quote']
        if (quote and quote not in prompt) or (item['requirement'] != 'not_required' and not quote):
            raise ValueError('Operation obligation must quote the original request')
    reply = value['final_reply']
    quote = reply['request_quote']
    if (quote and quote not in prompt) or (reply['mode'] != 'not_required' and not quote):
        raise ValueError('Reply requirement must quote the original request')
    if reply['mode'] == 'exact':
        if not reply['text'] or reply['text'] not in quote:
            raise ValueError('Exact reply must be literal text in its request quote')
    elif reply['text']:
        raise ValueError('Only exact replies may supply fixed text')
    if any(q not in prompt for q in value['other_operation_requirements']):
        raise ValueError('Unresolved operations must be quoted rather than invented')
    return {'request_sha256': hashlib.sha256(prompt.encode('utf8')).hexdigest(), **copy.deepcopy(value)}


def check(value, artifact_value, prompt, history):
    catalog = evidence.catalog_from_history(history)
    bound = bind(value, artifact_value, prompt, catalog)
    facts = evidence.build(artifact_value, prompt, history)
    contents = completed_file_contents(history)
    artifacts = {f'a{i}': a for i, a in enumerate(facts['artifacts'], 1)}
    by_path = {}
    for file in catalog:
        for alias in [file['observed_path'], *file['request_paths']]:
            by_path.setdefault(alias, set()).add(file['observed_path'])

    def mutations(path):
        result = []
        for index, item in enumerate(history, 1):
            tool = item.get('tool')
            if tool not in ('WRITE_TEXT_FILE', 'COPY_FILE_VERIFIED') or (item.get('evidence') or {}).get('condition_skipped'):
                continue
            args, output = item.get('args') or {}, item.get('output')
            output = output if isinstance(output, dict) else {}
            key = 'destination' if tool == 'COPY_FILE_VERIFIED' else 'path'
            names = [args.get(key), output.get(key)]
            if not any(isinstance(n, str) and path in by_path.get(n, set()) for n in names):
                continue
            if tool == 'COPY_FILE_VERIFIED' and evidence._trusted(item) and output.get('skipped_existing') is True:
                continue
            result.append((index, item))
        return result

    checks, readback_indices = [], []
    unknown = facts['unclassified_action_indices']
    for declaration in bound['artifact_obligations']:
        artifact = artifacts[declaration['artifact_id']]
        target, sources = artifact['destination_path'], artifact['source_paths']
        changes = mutations(target) if target else []
        committed = [(i, e) for i, e in changes if evidence._trusted(e)]
        copy_proofs = {c['sequence_index']: c for c in artifact['copy_observations']}
        for field in FIELDS:
            req = declaration[field]
            item = {'artifact_id': declaration['artifact_id'], 'kind': field, 'request_quote': req['request_quote'],
                    'status': 'not_required', 'evidence_sequence_indices': []}
            if req['requirement'] == 'conditional_or_unclear':
                item.update(status='uncertain', reason='Conditional or unclear original requirement needs a separate check.')
            elif req['requirement'] == 'required':
                item.update(status='uncertain', reason='Required operation has insufficient trusted evidence.')
                if field == 'preserve_sources':
                    source_actions = [(i, e) for p in sources for i, e in mutations(p)]
                    changed = [i for i, e in source_actions if evidence._trusted(e)]
                    if changed:
                        item.update(status='unmet', reason='Protected source was written during the recorded task.', evidence_sequence_indices=sorted(set(changed)))
                    elif sources and not source_actions and not unknown:
                        item.update(status='satisfied', reason='No source mutation in the complete supported-tool task history.')
                elif field == 'new_destination' and committed:
                    index, event = committed[0]
                    if not any(i < index for i, _ in changes) and not any(i < index for i in unknown):
                        exclusive = index in copy_proofs or event.get('tool') == 'WRITE_TEXT_FILE' and event.get('args', {}).get('overwrite', False) is False
                        if exclusive:
                            item.update(status='satisfied', reason='Exclusive destination creation succeeded.', evidence_sequence_indices=[index])
                        else:
                            item['reason'] = 'Write was not exclusive; this does not prove that the destination was new or pre-existing.'
                elif field == 'destination_readback' and committed:
                    index, event = committed[-1]
                    later_uncertain_write = any(i > index for i, _ in changes)
                    if not later_uncertain_write and not any(i > index for i in unknown):
                        observed = contents.get(target)
                        if index in copy_proofs:
                            item.update(status='satisfied', reason='Verified copy includes destination byte readback.', evidence_sequence_indices=[index])
                        elif observed and min(s['sequence_index'] for s in observed['source_segments']) > index:
                            item.update(status='satisfied', reason='Complete destination read follows the latest write.',
                                        evidence_sequence_indices=sorted({s['sequence_index'] for s in observed['source_segments']}))
                        else:
                            item['reason'] = 'No complete destination readback after the latest write.'
                    if item['status'] == 'satisfied':
                        readback_indices.extend(item['evidence_sequence_indices'])
                elif field == 'read_sources_before_write' and committed:
                    index, _ = committed[0]
                    prior = completed_file_contents(history[:index - 1])
                    witnessed = []
                    for path in sources:
                        if path in prior:
                            witnessed.extend(s['sequence_index'] for s in prior[path]['source_segments'])
                        elif index in copy_proofs and copy_proofs[index]['source'] == path:
                            witnessed.append(index)  # Internal source read precedes copy publication.
                        else:
                            break
                    else:
                        if sources and not any(i < index for i in unknown):
                            item.update(status='satisfied', reason='All specified sources were read before destination creation.', evidence_sequence_indices=sorted(set(witnessed)))
            checks.append(item)
    reply = bound['final_reply']
    final_events = [(i, h) for i, h in enumerate(history, 1) if h.get('tool') == 'FINAL_RESPONSE' and not (h.get('evidence') or {}).get('condition_skipped')]
    latest = final_events[-1] if final_events else None
    final = {'kind': 'final_reply', 'request_quote': reply['request_quote'], 'status': 'not_required', 'evidence_sequence_indices': []}
    if reply['mode'] == 'exact':
        if latest and evidence._trusted(latest[1]) and latest[1].get('output') == reply['text']:
            final.update(status='satisfied', reason='Latest verified response matches the requested literal.', evidence_sequence_indices=[latest[0]])
        else:
            final.update(status='unmet' if latest and evidence._trusted(latest[1]) else 'uncertain', reason='Latest verified response is missing or differs from the requested literal.')
    elif reply['mode'] != 'not_required':
        final.update(status='uncertain', reason='Semantic or conditional reply requires a separate reviewer.')
    checks.append(final)
    order = bound['reply_after_readback']
    ordered = {'kind': 'reply_after_readback', 'request_quote': order['request_quote'], 'status': 'not_required', 'evidence_sequence_indices': []}
    if order['requirement'] != 'not_required':
        ordered.update(status='uncertain', reason='Reply/readback order is not established.')
        readbacks = [c for c in checks if c['kind'] == 'destination_readback' and c['status'] != 'not_required']
        if order['requirement'] == 'required' and readbacks and all(c['status'] == 'satisfied' for c in readbacks) and latest and evidence._trusted(latest[1]):
            ordered.update(status='satisfied' if max(readback_indices) < latest[0] else 'unmet',
                           reason='Compared destination readback sequence indices with the latest response.', evidence_sequence_indices=sorted(set([*readback_indices, latest[0]])))
    checks.append(ordered)
    unresolved = bound['other_operation_requirements']
    blocked = bool(unresolved) or any(c['status'] in ('unmet', 'uncertain') for c in checks)
    return {'request_sha256': bound['request_sha256'], 'checks': checks, 'unresolved_operation_quotes': unresolved,
            'blocks_completion': blocked, 'whole_task_completion_inferred': False,
            'scope': 'Historical operation obligations only. Correct interpretation and full requirement coverage remain unproven; no mutation-free current disk guarantee.'}
