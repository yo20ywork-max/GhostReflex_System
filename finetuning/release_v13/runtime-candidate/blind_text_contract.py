"""Outcome-blind exact-text operand compiler contract, not a release checker."""
import hashlib
from jsonschema import Draft202012Validator

SYSTEM = (
    '根據 user_request 與檔案目錄，只擷取使用者要求的原樣複製或直接串接關係。'
    '不可判斷內容是否相同，也不可宣稱任務完成。目錄不包含檔案內容。'
    '原樣複製的 source_file_ids 有一個來源；串接則按要求順序列出來源，可重複引用同一來源。'
    'destination_file_id 必須是要求產生的結果檔，不能是任何來源檔。'
    '摘要、翻譯、創作和依規格寫程式都不是原樣複製，queries 應為空陣列；'
    '要求產生新內容或禁止原樣複製，不能反過來解讀為複製關係。'
    '必要來源或結果檔不在目錄時回空陣列，不可用另一個檔案冒充。'
    '只輸出 queries JSON；每項只含 source_file_ids 與 destination_file_id。'
)


def schema(catalog):
    ids = [item['file_id'] for item in catalog]
    if len(set(ids)) != len(ids) or not all(isinstance(key, str) and key for key in ids):
        raise ValueError('File identifiers must be unique nonempty strings')
    queries = {'type': 'array'}
    if len(ids) < 2:
        queries.update(maxItems=0, items={'type': 'object'})
    else:
        queries['items'] = {'oneOf': [
            {'type': 'object', 'properties': {
                'source_file_ids': {'type': 'array', 'minItems': 1,
                                    'items': {'type': 'string', 'enum': [key for key in ids if key != destination]}},
                'destination_file_id': {'type': 'string', 'const': destination}},
             'required': ['source_file_ids', 'destination_file_id'], 'additionalProperties': False}
            for destination in ids]}
    return {'type': 'object', 'properties': {'queries': queries}, 'required': ['queries'], 'additionalProperties': False}


def bind(value, prompt, catalog):
    """Host binds provenance; model cannot invent the source request/quote."""
    Draft202012Validator(schema(catalog)).validate(value)
    return {'request_sha256': hashlib.sha256(prompt.encode('utf8')).hexdigest(),
            'queries': [{'source_file_ids': list(q['source_file_ids']), 'destination_file_id': q['destination_file_id']} for q in value['queries']],
            'scope': 'Operand interpretation only. No query is not completion; correctness of interpreted intent still requires evaluation.'}
