"""Typed predicates over verified earlier outputs. Never evaluate model code."""


def condition_schema():
    return {'type': 'object', 'properties': {
        'step_id': {'type': 'integer', 'minimum': 1},
        'field': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'equals': {'type': 'boolean'},
    }, 'required': ['step_id', 'field', 'equals'], 'additionalProperties': False}


def validate_condition(value, available_ids):
    if not isinstance(value, dict) or set(value) != {'step_id', 'field', 'equals'}:
        raise ValueError('when 必須只包含 step_id、field、equals。')
    if type(value['step_id']) is not int or value['step_id'] < 1 or value['step_id'] not in available_ids:
        raise ValueError('when 只能引用歷史或前面步驟。')
    if not isinstance(value['field'], str) or not 1 <= len(value['field']) <= 128:
        raise ValueError('when.field 必須是原樣的頂層輸出欄位名稱。')
    if type(value['equals']) is not bool:
        raise ValueError('when.equals 必須是 boolean，不能用字串或數字代替。')


def check_condition(value, results):
    validate_condition(value, set(results))
    result = results[value['step_id']]
    if result.ok is not True or result.verified is not True or (result.evidence or {}).get('condition_skipped'):
        raise ValueError('條件依據未成功驗證，不能推定成立或不成立。')
    output = result.output
    if not isinstance(output, dict) or value['field'] not in output or type(output[value['field']]) is not bool:
        fields = [name for name, item in output.items() if type(item) is bool] if isinstance(output, dict) else []
        field_type = type(output[value['field']]).__name__ if isinstance(output, dict) and value['field'] in output else '不存在'
        available = repr(fields[:20]) if fields else '無'
        if len(fields) > 20:
            available += f'（共 {len(fields)} 個，僅列前 20 個）'
        raise ValueError(
            '條件依據缺少指定 boolean 欄位；不能把缺少、文字或數字當作 false。'
            f" step:{value['step_id']} 的 output 型別為 {type(output).__name__}；"
            f"要求欄位 {value['field']!r} 的型別為 {field_type}；可用 boolean 欄位：{available}。"
            '請依已驗證的輸出修正 when，或重新規劃；不要重試相同的無效條件。'
        )
    actual = output[value['field']]
    return actual is value['equals'], {'condition': dict(value), 'observed': actual}
