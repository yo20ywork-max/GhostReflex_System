"""Constrain exact source/destination relations while retaining semantic edits."""
import importlib.util
from pathlib import Path
from jsonschema import Draft202012Validator

spec = importlib.util.spec_from_file_location('artifact_intent_base', Path(__file__).with_name('artifact_intent_contract.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
SYSTEM = base.SYSTEM


def schema(catalog):
    base.schema(catalog)  # Validate identifiers with the unchanged host contract.
    ids = [item['file_id'] for item in catalog]
    metadata = {item['file_id']: item for item in catalog}
    choices = []
    for kind in ['exact_copy', 'exact_concat', 'semantic_generation']:
        for destination in [*ids, 'unobserved']:
            allowed = ids if kind == 'semantic_generation' else [i for i in ids if i != destination]
            if kind != 'semantic_generation' and not allowed:
                continue
            sources = {'type': 'array', 'items': {'type': 'string', 'enum': allowed}} if allowed else {
                'type': 'array', 'items': {'type': 'string'}, 'maxItems': 0}
            if kind == 'exact_copy':
                sources.update(minItems=1, maxItems=1)
            elif kind == 'exact_concat':
                sources['minItems'] = 2
            if destination == 'unobserved':
                name = {'type': 'string', 'minLength': 1}
            else:
                item = metadata[destination]
                aliases = [item.get('filename'), item.get('observed_path'), *item.get('request_paths', [])]
                aliases = list(dict.fromkeys(a for a in aliases if isinstance(a, str) and a))
                if not aliases:
                    raise ValueError('Observed destination needs at least one name or path')
                name = {'type': 'string', 'enum': aliases}
            choices.append({'type': 'object', 'properties': {
                'kind': {'type': 'string', 'const': kind},
                'source_file_ids': sources,
                'destination_file_id': {'type': 'string', 'const': destination},
                'destination_name': name},
                'required': ['kind', 'source_file_ids', 'destination_file_id', 'destination_name'],
                'additionalProperties': False})
    return {'type': 'object', 'properties': {'artifacts': {'type': 'array', 'items': {'oneOf': choices}}},
            'required': ['artifacts'], 'additionalProperties': False}


def bind(value, prompt, catalog):
    Draft202012Validator(schema(catalog)).validate(value)
    return base.bind(value, prompt, catalog)
