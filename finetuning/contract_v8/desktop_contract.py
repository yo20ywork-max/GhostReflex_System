"""Extract the actual desktop catalog without starting UI, models or devices."""
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'finetuning'))
from build_product_data import contract as core_contract
from product_tools import register


def extend_scope(scope, catalog):
    source = (ROOT/'run_daemon.py').read_text(encoding='utf-8-sig')
    wanted = {'ToolSpec', 'tool', 'object_schema', 'build_tool_catalog', 'build_plan_schema'}
    nodes = [n for n in ast.parse(source).body if getattr(n, 'name', '') in wanted]
    scope.setdefault('dataclass', dataclass)
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<desktop catalog registration>', 'exec'), scope)
    old = scope.get('TOOL_REGISTRY', {})
    scope['TOOL_REGISTRY'] = {
        item['name']: scope['ToolSpec'](item['name'], item['description'], item['parameters'], item['risk'],
                                      getattr(old.get(item['name']), 'handler', None))
        for item in catalog
    }
    register(SimpleNamespace(**scope))


def contract(*, max_plan_steps=24, explicit_tool_defaults=False):
    core, _, prompt, _ = core_contract(max_plan_steps=max_plan_steps, explicit_tool_defaults=explicit_tool_defaults)
    scope = {'__name__': __name__, 'json': json}
    extend_scope(scope, core)
    catalog = scope['build_tool_catalog']()
    schema = scope['build_plan_schema'](SimpleNamespace(max_plan_steps=max_plan_steps, explicit_tool_defaults=explicit_tool_defaults))
    def system(planner):
        return prompt(SimpleNamespace(catalog=planner.catalog, schema=getattr(planner, 'schema', schema)))
    names = ('run_daemon.py', 'product_tools.py', 'verified_copy.py', 'desktop_ui/app.py', 'finetuning/build_product_data.py')
    hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    return catalog, schema, system, hashes
