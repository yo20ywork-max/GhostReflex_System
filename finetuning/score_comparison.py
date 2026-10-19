"""Strict output-contract checks; history and general semantics require review."""
import argparse
import ast
import json
from pathlib import Path
from build_product_data import check


def first_even_check(text, function_name='first_even'):
    # Accept Markdown only for semantic checking; record formatting separately.
    code=text.strip()
    if code.startswith('```python') and code.endswith('```'):
        code=code[len('```python'):-3].strip()
    tree=ast.parse(code)
    if len(list(ast.walk(tree))) > 100 or sum(isinstance(n,(ast.For,ast.comprehension)) for n in ast.walk(tree)) > 1:
        return 'manual review: function exceeds bounded evaluator limits'
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.For,ast.If,
             ast.Compare,ast.Eq,ast.BinOp,ast.Mod,ast.Name,ast.Load,ast.Store,
             ast.Constant,ast.Return,ast.GeneratorExp,ast.comprehension,ast.Call,
             ast.Gt,ast.Subscript,ast.Slice,ast.UnaryOp,ast.USub)
    if any(not isinstance(node,allowed) for node in ast.walk(tree)):
        return 'manual review: syntax outside restricted evaluator'
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in ('next','reversed') or node.keywords):
            return 'manual review: call outside restricted evaluator'
        if isinstance(node,ast.Name) and node.id.startswith('__'):
            return 'manual review: disallowed name'
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef) or tree.body[0].name!=function_name:
        return False
    function=tree.body[0]
    if function.decorator_list or function.args.defaults or function.args.kw_defaults:
        return False
    scope={'__builtins__':{},'next':next,'reversed':reversed}
    exec(compile(tree,'<restricted-function-check>','exec'),scope)
    cases=([([],None),([5,8,2],8),([-3,0,4],0),([1,3,5],None),([-4,2],-4)]
           if function_name=='first_even' else
           [([],None),([-2,0],None),([1,-2,3,-4],3),([0,5,0],5),([5,2],2)])
    return all(scope[function_name](xs)==expected for xs,expected in cases)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path)
    args=parser.parse_args()
    contract=json.loads(Path(__file__).with_name('product_contract.json').read_text(encoding='utf-8'))
    catalog={t['name']:t for t in contract['catalog']}
    results=[]
    for record in map(json.loads,args.input.read_text(encoding='utf-8').splitlines()):
        result={k:record[k] for k in ('id','candidate','train_diagnostic')}
        text=record['text']
        try:
            if record['id'].startswith('format-'):
                plan=json.loads(text)
                check(plan,contract['schema'])
                for step in plan['steps']:
                    check(step['args'],catalog[step['tool']]['parameters'])
                result['strict_json_and_schema']=True
                if record['id']=='format-capture-dev':
                    captures=[s for s in plan['steps'] if s['tool']=='CAPTURE_SCREEN']
                    result['exact_requested_action']=len(captures)==1 and captures[0]['args'].get('prefix')=='Demo' and all(s['tool'] in ('CAPTURE_SCREEN','GET_ACTIVE_WINDOW') for s in plan['steps'])
                if record['id']=='format-reply-dev':
                    result['exact_requested_action']=len(plan['steps'])==1 and plan['steps'][0]['tool']=='FINAL_RESPONSE' and plan['steps'][0]['args'].get('message')=='明天再處理。'
            elif record['id']=='dev-3':
                result['exact_literal_path']=text=='D:\\项目\\视频.mp4'
            elif record['id']=='dev-4':
                result['plain_code_format']=not text.strip().startswith('```')
                result['five_python_cases']=first_even_check(text)
            elif record['id']=='test-4':
                result['plain_code_format']=not text.strip().startswith('```')
                result['five_python_cases']=first_even_check(text,'last_positive')
            elif record['id']=='test-3':
                result['exact_literal_text']=text=='默认设置'
            else:
                result['semantic_review']='manual; do not grade history using keywords alone'
        except (ValueError,KeyError,SyntaxError,TypeError) as exc:
            result['check_failed']=type(exc).__name__
        results.append(result)
    output=args.input.with_suffix('.checks.json')
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
