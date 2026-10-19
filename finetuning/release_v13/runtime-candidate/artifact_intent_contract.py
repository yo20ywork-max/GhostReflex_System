"""Classify each requested artifact before computing any content comparison."""
import hashlib
from jsonschema import Draft202012Validator

SYSTEM = (
    '根據 user_request 與檔案目錄，列出每個要求產生的檔案。你只分析要求，不判定任務完成。'
    '每個 artifact 先選 kind：exact_copy 代表原樣複製一份完整來源；'
    'exact_concat 代表依序直接串接多份完整來源；semantic_generation 代表摘要、翻譯、'
    '改寫、創作或依規格產生程式等需要產生不同內容的工作。'
    '保留原始來源不變不等於結果也要與來源相同。禁止複製原文不能解讀成要求原樣複製。'
    'source_file_ids 依要求順序列出，可重複；semantic_generation 也列出使用者指定的來源檔。'
    'destination_file_id 是要求的結果檔，不是來源；目錄沒有結果檔時填 unobserved，'
    'destination_name 填使用者要求的結果檔名，不可拿來源當目的。'
    '若沒有檔案產出要求，artifacts 可以為空；空陣列或 unobserved 都不代表已完成。'
    '同一要求可含不同類型的多個產出，分開列出。目錄沒有內容，不得推論資料值或相同與否。'
    '只輸出 artifacts JSON，每項含 kind、source_file_ids、destination_file_id、destination_name。'
)


def schema(catalog):
    ids = [item['file_id'] for item in catalog]
    if len(set(ids)) != len(ids) or 'unobserved' in ids:
        raise ValueError('Invalid file identifiers')
    source = {'type': 'array', 'items': {'type': 'string', 'enum': ids or ['no_source']}}
    if not ids:
        source['maxItems'] = 0
    return {'type': 'object', 'properties': {'artifacts': {'type': 'array', 'items': {
        'type': 'object', 'properties': {
            'kind': {'type': 'string', 'enum': ['exact_copy', 'exact_concat', 'semantic_generation']},
            'source_file_ids': source,
            'destination_file_id': {'type': 'string', 'enum': [*ids, 'unobserved']},
            'destination_name': {'type': 'string', 'minLength': 1}},
        'required': ['kind', 'source_file_ids', 'destination_file_id', 'destination_name'], 'additionalProperties': False}}},
        'required': ['artifacts'], 'additionalProperties': False}


def bind(value, prompt, catalog):
    Draft202012Validator(schema(catalog)).validate(value)
    by_id = {item['file_id']: item for item in catalog}
    artifacts = []
    for item in value['artifacts']:
        sources, destination, kind = item['source_file_ids'], item['destination_file_id'], item['kind']
        if kind == 'exact_copy' and len(sources) != 1:
            raise ValueError('Exact copy requires one source')
        if kind == 'exact_concat' and len(sources) < 2:
            raise ValueError('Exact concatenation requires ordered sources')
        if kind != 'semantic_generation' and destination in sources:
            raise ValueError('Exact copy/concatenation cannot target its source')
        if destination != 'unobserved':
            metadata = by_id[destination]
            aliases = [metadata.get('filename'), metadata.get('observed_path'), *metadata.get('request_paths', [])]
            if item['destination_name'] not in aliases:
                raise ValueError('Destination name does not match selected observed file')
        elif item['destination_name'] not in prompt:
            raise ValueError('Unobserved destination must be grounded in original request')
        artifacts.append({**item, 'source_file_ids': list(sources), 'destination_observed': destination != 'unobserved'})
    return {'request_sha256': hashlib.sha256(prompt.encode('utf8')).hexdigest(), 'artifacts': artifacts,
            'scope': 'Interpreted artifact requirements only; not proof of semantic intent accuracy, evidence completeness or task completion.'}
