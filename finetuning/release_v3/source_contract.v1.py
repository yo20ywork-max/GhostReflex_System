"""Compile source-cited task constraints without accepting invented values.

Experimental: source membership and type checks do not establish entailment or
complete semantic coverage. This module never authorizes an action or release.
"""
import hashlib
import re

from evidence_contract import fingerprint


class SourceContractError(ValueError):
    pass


def _quote(request, value):
    if not isinstance(value, str) or not value or value not in request:
        raise SourceContractError('Every value needs an exact, nonempty source quote')
    return value


def _keys(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise SourceContractError('Unexpected or missing fields')


def _integer(text):
    """Strict bounded numeral conversion; no searching a longer sentence."""
    if re.fullmatch(r'[0-9]{1,6}', text):
        return int(text)
    if text == '兩':
        return 2
    digits = {c: i for i, c in enumerate('零一二三四五六七八九')}
    if len(text) == 1 and text in digits:
        return digits[text]
    # Standard Chinese numerals through 9999, descending units only.
    if not text or not re.fullmatch(r'[零一二三四五六七八九兩十百千]+', text):
        raise SourceContractError('Unsupported numeral')
    value, pending, prior = 0, None, 10000
    for char in text:
        if char in digits or char == '兩':
            digit = digits.get(char, 2)
            if pending is not None and pending != 0:
                raise SourceContractError('Ambiguous numeral')
            pending = digit
        else:
            unit = {'十': 10, '百': 100, '千': 1000}[char]
            if unit >= prior or (pending is None and (unit != 10 or value)) or pending == 0:
                raise SourceContractError('Invalid numeral order')
            value += (pending if pending is not None else 1) * unit
            prior, pending = unit, None
    return value + (pending or 0)


def _count(quote, kind):
    units = '次下' if kind == 'max_dispatches' else '筆項'
    match = re.fullmatch(r'(?:最多|至多|不超過|上限(?:為)?|僅|只)?\s*([0-9零一二三四五六七八九兩十百千]+)\s*([' + units + r'])', quote)
    if not match:
        raise SourceContractError('Count quote must name the number and the correct unit')
    return _integer(match[1])


# Explicit lexical conversions. A model cannot provide its own enum value.
# These are not a general natural-language entailment checker.
_ALIASES = {
    'by': {'CSS': 'css', 'CSS 選擇器': 'css', '文字': 'text', '標籤': 'label', '角色': 'role', '提示文字': 'placeholder'},
    'state': {'消失': 'hidden', '隱藏': 'hidden', '可見': 'visible', '出現': 'visible', '從 DOM 移除': 'detached'},
    'recursive': {'遞迴': True, '包含子資料夾': True, '不遞迴': False, '不包含子資料夾': False},
    'exact': {'完全符合': True, '完全相同': True},
    'overwrite': {'覆寫': True, '不要覆寫': False, '不覆寫': False},
}


def _argument(name, quote, parameter):
    typ = parameter.get('type')
    if name in _ALIASES and quote in _ALIASES[name]:
        value = _ALIASES[name][quote]
    elif typ == 'string':
        value = quote
    elif typ == 'integer':
        value = _integer(quote)
    elif typ == 'number' and re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', quote):
        value = float(quote)
    elif typ == 'boolean' and quote in ('true', 'false'):
        value = quote == 'true'
    else:
        raise SourceContractError('Unsupported source-to-argument conversion')
    if 'enum' in parameter and value not in parameter['enum']:
        raise SourceContractError('Source does not identify a valid enum value')
    if typ in ('integer', 'number'):
        if type(value) not in (int, float) or not parameter.get('minimum', -float('inf')) <= value <= parameter.get('maximum', float('inf')):
            raise SourceContractError('Argument outside its tool limits')
    if typ == 'boolean' and type(value) is not bool:
        raise SourceContractError('Not a boolean')
    return value


def compile_source_contract(request, extracted, catalog):
    """Return a mechanical contract plus auditable per-field provenance.

    No default tool arguments are inserted. Unsupported conversions fail the
    entire extraction; they are never silently removed to improve a score.
    """
    _keys(extracted, ('requirements', 'before', 'unresolved'))
    if not isinstance(extracted['unresolved'], list):
        raise SourceContractError('Unresolved requirements must be an array')
    for unresolved in extracted['unresolved']:
        _keys(unresolved, ('source_quote', 'reason'))
        _quote(request, unresolved['source_quote'])
        if not isinstance(unresolved['reason'], str) or not unresolved['reason'].strip():
            raise SourceContractError('Unresolved requirement needs a reason')
    if extracted['unresolved']:
        raise SourceContractError('Some requested conditions cannot be represented')
    if not isinstance(extracted['requirements'], list) or not 1 <= len(extracted['requirements']) <= 128:
        raise SourceContractError('Bounded nonempty requirements required')
    if not isinstance(extracted['before'], list) or len(extracted['before']) > 512:
        raise SourceContractError('Invalid ordering constraints')
    tools = {x['name']: x for x in catalog}
    compiled, provenance, ids = [], [], set()
    for req in extracted['requirements']:
        _keys(req, ('id', 'source_quote', 'tool', 'mode', 'arguments', 'constraints'))
        rid = req['id']
        if not isinstance(rid, str) or not rid or rid in ids:
            raise SourceContractError('Unique nonempty identifiers required')
        ids.add(rid)
        quote = _quote(request, req['source_quote'])
        if req['tool'] not in tools or req['mode'] not in ('require', 'forbid'):
            raise SourceContractError('Unknown tool or mode')
        if not isinstance(req['arguments'], list) or not isinstance(req['constraints'], list):
            raise SourceContractError('Arguments and constraints must be arrays')
        properties = tools[req['tool']]['parameters'].get('properties', {})
        args, fields = {}, []
        for arg in req['arguments']:
            _keys(arg, ('name', 'quote'))
            name = arg['name']
            if name not in properties or name in args:
                raise SourceContractError('Unknown or duplicate argument')
            source = _quote(request, arg['quote'])
            value = _argument(name, source, properties[name])
            args[name] = value
            fields.append({'field': 'args.' + name, 'quote': source, 'value': value})
        item = {'id': rid, 'source_quote': quote, 'tool': req['tool'], 'args': args, 'mode': req['mode'], 'selection': 'any'}
        seen = set()
        for constraint in req['constraints']:
            _keys(constraint, ('kind', 'quote'))
            kind, source = constraint['kind'], _quote(request, constraint['quote'])
            if kind in seen or kind not in ('max_dispatches', 'max_output_items', 'output_equals', 'latest'):
                raise SourceContractError('Unknown or duplicate constraint')
            seen.add(kind)
            if req['mode'] == 'forbid':
                raise SourceContractError('Forbidden dispatches cannot have result constraints')
            if kind == 'max_output_items' and req['tool'] != 'LIST_DIRECTORY':
                raise SourceContractError('This tool has no declared list result')
            if kind in ('max_dispatches', 'max_output_items'):
                value = _count(source, kind)
                item[kind] = value
            elif kind == 'latest':
                if source not in ('最新', '最後一次', '最後的結果'):
                    raise SourceContractError('Unsupported latest-selection quote')
                value = 'latest'
                item['selection'] = value
            else:
                value = source
                item[kind] = value
            fields.append({'field': kind, 'quote': source, 'value': value})
        compiled.append(item)
        provenance.append({'id': rid, 'fields': fields})
    edges = []
    required_ids = {x['id'] for x in compiled if x['mode'] == 'require'}
    for edge in extracted['before']:
        _keys(edge, ('first', 'then', 'source_quote'))
        _quote(request, edge['source_quote'])
        if edge['first'] not in required_ids or edge['then'] not in required_ids or edge['first'] == edge['then']:
            raise SourceContractError('Order edges must refer to required observations')
        edges.append(dict(edge))
    contract = {'request_sha256': hashlib.sha256(request.encode()).hexdigest(), 'requirements': compiled, 'before': edges}
    return {'contract': contract, 'field_provenance': provenance, 'extraction_sha256': fingerprint(extracted),
            'contract_semantics_verified': False, 'product_release_approved': False,
            'limitations': ['A source quote does not establish entailment or complete coverage.',
                           'Tool aliases, reference resolution, conditional goals and opaque process effects require separate verification.']}
