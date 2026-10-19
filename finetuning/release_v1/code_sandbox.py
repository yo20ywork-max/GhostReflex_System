"""Restricted pure-function evaluator. Run in a disposable subprocess with a timeout."""
import ast
import json
import sys
import collections
import itertools
import math
from types import SimpleNamespace

SAFE_BUILTINS={name:getattr(__import__('builtins'),name) for name in ('abs','all','any','bin','bool','dict','enumerate','filter','float','int','isinstance','len','list','map','max','min','next','range','reversed','round','set','sorted','str','sum','tuple','type','zip')}
SAFE_MODULES={'collections':{'Counter':collections.Counter},'itertools':{'accumulate':itertools.accumulate,'chain':itertools.chain},'math':{'prod':math.prod,'isqrt':math.isqrt,'factorial':math.factorial,'ceil':math.ceil,'floor':math.floor}}
METHODS={'append','count','endswith','fromkeys','get','index','items','join','keys','lower','replace','split','splitlines','startswith','strip','swapcase','upper','values','from_iterable','isalpha','isdigit','isspace','isupper'} | {n for m in SAFE_MODULES.values() for n in m}
NODES=(ast.Module,ast.Import,ast.ImportFrom,ast.alias,ast.Lambda,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.Assign,ast.AugAssign,ast.AnnAssign,ast.Name,ast.Load,ast.Store,ast.Constant,ast.List,ast.Tuple,ast.Dict,ast.Set,ast.ListComp,ast.SetComp,ast.DictComp,ast.GeneratorExp,ast.comprehension,ast.Call,ast.keyword,ast.Attribute,ast.Subscript,ast.Slice,ast.If,ast.IfExp,ast.For,ast.Break,ast.Continue,ast.Pass,ast.Expr,ast.BinOp,ast.UnaryOp,ast.BoolOp,ast.Compare,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.Mod,ast.Pow,ast.BitAnd,ast.BitOr,ast.BitXor,ast.LShift,ast.RShift,ast.USub,ast.UAdd,ast.Not,ast.And,ast.Or,ast.Eq,ast.NotEq,ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Is,ast.IsNot,ast.In,ast.NotIn)

def validate_code(code,function):
    tree=ast.parse(code)
    if not tree.body or any(not isinstance(n,(ast.FunctionDef,ast.Import,ast.ImportFrom)) for n in tree.body):raise ValueError('Only functions and allowlisted imports permitted')
    if len(list(ast.walk(tree)))>800:raise ValueError('Program too large')
    functions={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
    imported=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            if any(a.name not in SAFE_MODULES for a in node.names):raise ValueError('Forbidden import')
        if isinstance(node,ast.ImportFrom):
            if node.level or node.module not in SAFE_MODULES or any(a.name not in SAFE_MODULES[node.module] for a in node.names):raise ValueError('Forbidden import')
            imported.update(a.asname or a.name for a in node.names)
    if function not in functions:raise ValueError('Required function missing')
    for node in ast.walk(tree):
        if not isinstance(node,NODES):raise ValueError('Forbidden syntax: '+type(node).__name__)
        if isinstance(node,ast.Name) and node.id.startswith('_') and node.id!='_':raise ValueError('Private name')
        if isinstance(node,ast.Attribute) and node.attr not in METHODS:raise ValueError('Forbidden method')
        if isinstance(node,ast.FunctionDef):
            if node.decorator_list or node.args.defaults or node.args.kw_defaults:raise ValueError('No decorators/default expressions')
            if node.name.startswith('_'):raise ValueError('Private function')
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name) and node.func.id not in SAFE_BUILTINS and node.func.id not in functions and node.func.id not in imported:raise ValueError('Forbidden call')
            if not isinstance(node.func,(ast.Name,ast.Attribute)):raise ValueError('Indirect call')
    return tree

def run(payload):
    tree=validate_code(payload['code'],payload['function'])
    def safe_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level or name not in SAFE_MODULES:raise ValueError('Forbidden import')
        return SimpleNamespace(**SAFE_MODULES[name])
    scope={'__builtins__':{**SAFE_BUILTINS,'__import__':safe_import}}
    exec(compile(tree,'<candidate>','exec'),scope)
    outcomes=[]
    for test in payload['tests']:
        args=test['args'];before=json.dumps(args,sort_keys=True,ensure_ascii=False)
        actual=scope[payload['function']](*args)
        # JSON transports integer dictionary keys as strings; compare the same wire representation.
        normalized=json.loads(json.dumps(actual,ensure_ascii=False))
        outcomes.append(normalized==test['expected'] and before==json.dumps(args,sort_keys=True,ensure_ascii=False))
    return {'passed':all(outcomes),'tests_passed':sum(outcomes),'tests_total':len(outcomes)}

if __name__=='__main__':
    try:print(json.dumps(run(json.load(sys.stdin))))
    except BaseException as exc:print(json.dumps({'passed':False,'error':type(exc).__name__+': '+str(exc)[:200]}))
