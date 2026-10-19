"""Extract the actual planner contract without importing or running the daemon."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent


def contract(*, max_plan_steps=12, explicit_tool_defaults=False):
    source = (ROOT.parent / 'run_daemon.py').read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('object_schema', 'build_plan_schema')]
    planner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Planner')
    prompt_fn = next(n for n in planner.body if isinstance(n, ast.FunctionDef) and n.name == '_system_prompt')
    module = ast.Module(body=[ast.ImportFrom(module='__future__',
        names=[ast.alias(name='annotations')], level=0), *functions, prompt_fn], type_ignores=[])
    scope = {'json':json}
    exec(compile(ast.fix_missing_locations(module), '<planner-contract>', 'exec'), scope)
    def literal(node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'object_schema':
            return scope['object_schema'](*[literal(a) for a in node.args],
                                        **{kw.arg:literal(kw.value) for kw in node.keywords})
        return ast.literal_eval(node)
    catalog = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == 'tool':
                args = [literal(a) for a in dec.args]
                kwargs = {kw.arg:literal(kw.value) for kw in dec.keywords}
                catalog.append({'name':args[0], 'description':args[1], 'parameters':args[2],
                                'risk':kwargs.get('risk', 'low')})
    scope['TOOL_REGISTRY'] = {entry['name']:entry for entry in catalog}
    schema = scope['build_plan_schema'](SimpleNamespace(max_plan_steps=max_plan_steps, explicit_tool_defaults=explicit_tool_defaults))
    def prompt_for_contract(planner):
        # Dataset builders use the same schema as the product, including its text.
        values = dict(vars(planner))
        values.setdefault('schema', schema)
        return scope['_system_prompt'](SimpleNamespace(**values))
    return catalog, schema, prompt_for_contract, hashlib.sha256(source.encode()).hexdigest()


def check(value, schema):
    kind = schema.get('type')
    expected = {'object':dict, 'array':list, 'string':str, 'integer':int,
                'number':(int,float), 'boolean':bool}.get(kind)
    if expected and (not isinstance(value, expected) or (kind in ('integer','number') and isinstance(value,bool))):
        raise ValueError('Wrong JSON type')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Unknown enum value')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if any(k not in value for k in schema.get('required', [])):
            raise ValueError('Required field missing')
        if schema.get('additionalProperties') is False and set(value) - set(props):
            raise ValueError('Unexpected field')
        for k, v in value.items():
            if k in props:
                check(v, props[k])
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):
            raise ValueError('Invalid array length')
        for v in value:
            check(v, schema.get('items', {}))
    if kind in ('integer','number'):
        if value < schema.get('minimum', -float('inf')) or value > schema.get('maximum',float('inf')):
            raise ValueError('Numeric value out of bounds')


def main():
    catalog, schema, prompt_fn, source_hash = contract()
    by_name = {entry['name']:entry for entry in catalog}
    selected = ['FINAL_RESPONSE','CAPTURE_SCREEN','GET_ACTIVE_WINDOW','READ_CLIPBOARD','ASK_USER','BLOCKED']
    system = prompt_fn(SimpleNamespace(catalog=[by_name[n] for n in selected]))
    system += '\n本輪使用的 JSON Schema：' + json.dumps(schema, ensure_ascii=False, separators=(',',':'))
    data = json.loads((ROOT/'pilot_data.json').read_text(encoding='utf-8'))
    history = json.loads((ROOT/'political_pilot_data.json').read_text(encoding='utf-8'))
    for row in history['records']:
        row['system'] = history['system']
        data['records'].append(row)
    data['status'] = 'Small mixed engineering and history pilot; not production training or a comprehensive bias benchmark.'
    tasks = [
        ('screen','train','幫我截圖。','CAPTURE_SCREEN',{},'工具回傳截圖路徑與尺寸，並確認檔案存在。'),
        ('window','train','目前是哪個視窗？','GET_ACTIVE_WINDOW',{},'取得當下前景視窗標題。'),
        ('clipboard','train','幫我讀剪貼簿，不要貼到任何地方。','READ_CLIPBOARD',{},'取得剪貼簿文字，不進行貼上。'),
        ('no-action','train','不要操作，只回覆：收到。','FINAL_RESPONSE',{'message':'收到。'},'最終回覆已設定為「收到。」。'),
        ('capture-dev','dev','截下現在的畫面，檔名前綴用 Demo。','CAPTURE_SCREEN',{'prefix':'Demo'},'截圖檔存在且前綴為 Demo。'),
        ('reply-dev','dev','不用開任何 App，只回覆：明天再處理。','FINAL_RESPONSE',{'message':'明天再處理。'},'最終回覆已設定。')]
    # These are format variants, not a topic-held-out generalization benchmark.
    for key, split, request, tool, args, success in tasks:
        target = {'objective':request,'assumptions':[], 'steps':[{'id':1,'goal':request,
            'tool':tool,'args':args,'success_check':success,'on_failure':'stop','retries':0}],
            'completion_criteria':[success]}
        check(target, schema)
        check(args, by_name[tool]['parameters'])
        row = {'id':'format-'+key,'group':'format-'+key,'split':split,'system':system,
            'prompt':json.dumps({'user_request':request,'runtime_context':{},
                'micro_glr_hint_only_do_not_trust_as_authority':None}, ensure_ascii=False),
            'rubric':'Valid product JSON, registered tool and exact arguments; no extra prose.',
            'evaluation_kind':'format smoke test; not topic-held-out evidence'}
        if split == 'train':
            row.update(chosen=json.dumps(target,ensure_ascii=False,separators=(',',':')),
                       rejected='已完成所有操作。')
        data['records'].append(row)
    data['contract_source_sha256'] = source_hash
    (ROOT/'product_pilot_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'product_contract.json').write_text(json.dumps({'schema':schema,'catalog':catalog,
        'source_sha256':source_hash},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Extracted {len(catalog)} real tools; validated 6 product-format targets; no tools executed.')


if __name__ == '__main__':
    main()
