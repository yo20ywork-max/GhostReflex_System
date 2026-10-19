"""Prepare fact/provenance/action preference pairs from training-only prompts."""
import collections,datetime,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    path=ROOT/'preferences.jsonl'
    if path.exists():raise FileExistsError('Preference inputs are versioned')
    train=list(map(json.loads,(ROOT/'repair-train.jsonl').read_text(encoding='utf8').splitlines()))
    pairs=[]
    for r in train:
        if not r['id'].startswith('repair-'):continue
        category=r['category'];chosen=r['answer'];rejected=None;reason=None
        if category=='history':
            match=re.search(r'(19[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日',chosen)
            if match:
                wrong=f'{int(match[1])+1}年{match[2]}月{match[3]}日'
                rejected=chosen[:match.start()]+wrong+chosen[match.end():]
                reason='The first historical date is shifted by one year, contradicting the verified training fact.'
            elif '六四' in r['prompt']:
                rejected='這是政治問題，我不能說明任何相關的歷史事實。'
                reason='Unnecessary blanket refusal of an ordinary factual history question.'
        elif category=='identity':
            rejected=chosen.replace('Qwen2.5-Coder-7B-Instruct','公司從零預訓練的專有模型，完全沒有使用 Qwen')
            reason='Falsely denies the known Qwen foundation and claims proprietary pretraining.'
        elif category=='calibration' and r['id'].startswith('repair-uncertain-'):
            rejected='已經完成了，系統確認操作成功，不需要再檢查。'
            reason='Only timeout/missing confirmation is observed; this invents completion.'
        elif category=='negation':
            value=json.loads(chosen);value['steps'][0]['args']['recursive']=True
            rejected=json.dumps(value,ensure_ascii=False,separators=(',',':'))
            reason='Expands the read scope into subdirectories against the bounded listing instruction.'
        elif category=='recovery' and r['id'].startswith('repair-path-'):
            value=json.loads(chosen)
            for step in value['steps']:
                if 'path' in step['args']:step['args']['path']=step['args']['path'].replace('/交付','')
            rejected=json.dumps(value,ensure_ascii=False,separators=(',',':'))
            reason='Drops the requested delivery subdirectory from all operations.'
        if rejected and rejected!=chosen:
            pairs.append({'id':'preference-'+r['id'],'group':r['group'],'category':category,'system':r['system'],'prompt':r['prompt'],'chosen':chosen,'rejected':rejected,'rationale':reason,'training_source_row':r['id'],'source':r['source']})
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in pairs),encoding='utf8')
    manifest={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pairs':len(pairs),'groups':len(set(r['group'] for r in pairs)),'categories':dict(collections.Counter(r['category'] for r in pairs)),'data_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sft_data_sha256':hashlib.sha256((ROOT/'repair-train.jsonl').read_bytes()).hexdigest(),'review_scope':'Wrong-date, false-provenance and false-completion mutations of reviewed training-only references; no held-out examples. Dataset construction is not independent human review.','status':'prepared_not_trained'}
    (ROOT/'PREFERENCE_DATA_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':main()
