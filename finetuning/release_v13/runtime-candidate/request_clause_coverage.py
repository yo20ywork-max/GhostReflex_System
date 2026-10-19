"""Lossless request units, all mandatory in a model classification response.

This prevents omitted units/fabricated quotes, not wrong semantic labels. It
does not bind targets, evaluate evidence or declare task completion.
"""
from jsonschema import Draft202012Validator

KINDS = ['read_sources_before_write', 'preserve_sources', 'new_destination',
         'destination_readback', 'reply_after_readback', 'exact_reply', 'semantic_reply',
         'permission_or_waiver', 'content_requirement', 'other_operation']
SYSTEM = (
    '逐段分類原始要求，不判定任務是否完成。每個clauses鍵都必須回答，不得略過任何一段。'
    '每段可有多個標籤，請完整列出。原檔不可改、不要修改來源、保留來源＝preserve_sources；'
    '先讀來源再建立結果＝read_sources_before_write；建立新檔或不得覆寫＝new_destination；'
    '寫後讀回目的＝destination_readback；读回後才能回覆＝reply_after_readback；'
    '要求特定回覆字句＝exact_reply；要求說明但未限定字句＝semantic_reply。'
    '只是允許某操作或取消某項要求＝permission_or_waiver，例如不必讀回、允許修改來源、可以覆寫、不要回覆。'
    '原樣複製、串接內容與順序、摘要、翻譯、程式、文案、句數與文字保留等內容規格＝content_requirement。'
    '條件式分支、禁止讀取、其他App、等待或以上標籤不足以表達的操作＝other_operation。'
    '引號內文字只是原要求的字串，不可把回覆文字中的「不必讀回」解讀為取消外面的讀回要求。'
    '一段同時要求讀回再回覆，要同時列destination_readback、reply_after_readback、exact_reply或semantic_reply。'
    '只輸出JSON物件，鍵與clauses的鍵完全相同，每個值是該段所有標籤的陣列。'
)


def split(prompt):
    if not isinstance(prompt, str) or not prompt:
        raise ValueError('Nonempty original request required')
    matching = {'「': '」', '『': '』', '“': '”', '‘': '’', '(': ')', '[': ']', '{': '}'}
    stack, start, parts = [], 0, []
    escaped = False
    for index, char in enumerate(prompt):
        if escaped:
            escaped = False
            continue
        if char == '\\' and stack and stack[-1] in ('"', "'", '`'):
            escaped = True
            continue
        if stack and char == stack[-1]:
            stack.pop()
            continue
        if char in ('"', "'", '`'):
            # Do not interpret the apostrophe in a word as an opening quote.
            if not stack and not (char == "'" and index and prompt[index - 1].isalnum()):
                stack.append(char)
            continue
        if char in matching and (not stack or stack[-1] not in ('"', "'", '`')):
            stack.append(matching[char])
            continue
        numeric_comma = char == ',' and 0 < index < len(prompt) - 1 and prompt[index - 1].isdigit() and prompt[index + 1].isdigit()
        if not stack and char in '，。；;,\n' and not numeric_comma:
            parts.append((start, index + 1)); start = index + 1
    if start < len(prompt):
        parts.append((start, len(prompt)))
    # Empty punctuation-only fragments stay attached to their preceding unit.
    merged = []
    for a, b in parts:
        if merged and not prompt[a:b].strip('，。；;,\r\n\t '):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    result = {f'c{i}': {'start': a, 'end': b, 'text': prompt[a:b]} for i, (a, b) in enumerate(merged, 1)}
    assert ''.join(v['text'] for v in result.values()) == prompt
    return result


def schema(prompt):
    return {'type': 'object', 'properties': {key: {'type': 'array', 'minItems': 1, 'uniqueItems': True,
                'items': {'type': 'string', 'enum': KINDS}} for key in split(prompt)},
            'required': list(split(prompt)), 'additionalProperties': False}


def bind(value, prompt):
    Draft202012Validator(schema(prompt)).validate(value)
    units = split(prompt)
    return {'clauses': [{**unit, 'clause_id': key, 'kinds': list(value[key])} for key, unit in units.items()],
            'all_request_characters_accounted_for': True,
            'semantic_classification_proven': False, 'whole_task_completion_inferred': False}
