"""Deterministic checks plus explicit semantic-review queue; no false automatic history pass."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from build_product_data import check

def native_key(value):
    """Match run_daemon.key_from_name; never normalize browser keys or literal text."""
    normalized=value.strip().lower().replace(' ','_')
    aliases={'control':'ctrl','ctrl_l':'ctrl_l','ctrl_r':'ctrl_r','return':'enter','escape':'esc','windows':'cmd','win':'cmd','pageup':'page_up','pagedown':'page_down','arrow_up':'up','arrow_down':'down','arrow_left':'left','arrow_right':'right'}
    return aliases.get(normalized,normalized)

def equivalent_argument(tool,key,actual,expected):
    if tool=='PRESS_KEY' and key=='key' and isinstance(actual,str) and isinstance(expected,str):return native_key(actual)==native_key(expected)
    if tool=='HOTKEY' and key=='keys' and isinstance(actual,list) and isinstance(expected,list):return [native_key(k) for k in actual]==[native_key(k) for k in expected]
    return actual==expected

def validate_result_identity(row,result):
    expected=hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest()
    if result.get('prompt_sha256')!=expected:raise ValueError('Result is for a different prompt: '+row['id'])
    if result.get('category')!=row['category'] or result.get('group')!=row['group']:raise ValueError('Result labels do not match the locked row')
    if result.get('candidate') not in ('base','adapter'):raise ValueError('Unknown candidate label')
    if type(result.get('completed')) is not bool or not isinstance(result.get('text'),str):raise ValueError('Missing completion evidence')

def score(row,result):
    text=result['text'].strip();oracle=row['oracle'];kind=oracle['type']
    if not result.get('completed',True):return {'passed':False,'reason':'incomplete generation'}
    if kind=='exact':
        matched=text==oracle['value'].strip()
        if row['category']=='asr' and not matched:
            return {'passed':None,'exact_match':False,'reference':oracle['value'],'reason':'Review intent, target and negation; equivalent wording is allowed'}
        return {'passed':matched,'reason':'exact text'}
    if kind=='plan':
        contract=json.loads((ROOT/'contract.json').read_text(encoding='utf8'))
        tools={t['name']:t for t in contract['catalog']}
        try:
            value=json.loads(text);check(value,contract['schema'])
            # Validate every action before allowing review of an alternate sequence.
            for step in value['steps']:check(step['args'],tools[step['tool']]['parameters'])
            if len(value['steps'])!=len(oracle['actions']):
                return {'passed':None,'reason':'Different valid action sequence; review every operation, target, side effect and completion claim','semantic_review':'Alternative sequence is not automatically equivalent'}
            requires_review=False
            for s,expected in zip(value['steps'],oracle['actions']):
                parameters=tools[s['tool']]['parameters']
                check(s['args'],parameters)
                if s['tool']!=expected['tool']:raise ValueError('Action semantics mismatch')
                # Schema defaults are actual executor semantics, not mandatory serialized tokens.
                effective={k:v['default'] for k,v in parameters.get('properties',{}).items() if 'default' in v}
                effective.update(s['args'])
                for k,v in expected['args'].items():
                    if (s['tool']=='BLOCKED' and k in ('reason','missing_capability','suggested_next_action')) or (s['tool']=='ANALYZE_SCREEN' and k=='question' and effective.get(k)!=v):
                        requires_review=True
                    elif not equivalent_argument(s['tool'],k,effective.get(k),v):raise ValueError('Action semantics mismatch')
                for k,v in s['args'].items():
                    if k not in expected['args'] and v!=parameters.get('properties',{}).get(k,{}).get('default'):
                        requires_review=True
            if requires_review:return {'passed':None,'reason':'Valid plan with free prose or additional nondefault arguments; requires semantic review','semantic_review':'Check arguments, scope, uncertainty and completion claims'}
            return {'passed':True,'reason':'schema and expected action arguments','semantic_review':'Check goals and completion claims separately'}
        except (ValueError,KeyError,TypeError) as exc:return {'passed':False,'reason':str(exc)}
    if kind=='code':
        code=text
        if code.startswith('```'):
            match=re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```',code,re.S)
            if match:code=match.group(1)
        payload={'code':code,'function':oracle['function'],'tests':oracle['tests']}
        try:
            proc=subprocess.run([sys.executable,'-I',str(ROOT/'code_sandbox.py')],input=json.dumps(payload),capture_output=True,text=True,timeout=3,encoding='utf8')
            answer=json.loads(proc.stdout);answer['format_clean']=text==code;return answer
        except (subprocess.TimeoutExpired,ValueError) as exc:return {'passed':False,'reason':type(exc).__name__}
    if kind=='identity':
        required=all(s in text for s in ['CrossGen-AGI-μ','跨世代媒體科技股份有限公司','台灣','Qwen'])
        return {'passed':None,'keyword_check':required,'reason':'Requires semantic provenance review; keyword presence is insufficient'}
    return {'passed':None,'reason':'Requires factual/semantic review','reference':row['answer']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--results',required=True);args=p.parse_args()
    rows={r['id']:r for r in [json.loads(l) for l in Path(args.data).read_text(encoding='utf8').splitlines()]}
    results=[json.loads(l) for l in Path(args.results).read_text(encoding='utf8').splitlines()]
    checked=[];summary={};seen=set()
    for r in results:
        validate_result_identity(rows[r['id']],r)
        pair=(r['candidate'],r['id'])
        if pair in seen:raise ValueError('Duplicate output')
        seen.add(pair)
        outcome=score(rows[r['id']],r)
        checked.append({**r,'check':outcome})
        counts=summary.setdefault(r['candidate'],{}).setdefault(r['category'],{'pass':0,'fail':0,'pending':0})
        counts['pending' if outcome['passed'] is None else 'pass' if outcome['passed'] else 'fail']+=1
    report={'summary':summary,'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'data_sha256':hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),'expected_per_candidate':len(rows),'actual_per_candidate':{c:sum(r['candidate']==c for r in results) for c in summary},'results':checked,'release_approved':False}
    Path(args.results+'.checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
