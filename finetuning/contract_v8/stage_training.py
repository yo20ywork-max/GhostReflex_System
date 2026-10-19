"""Stage a small locked training bundle locally; never provision or download."""
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'release_v4'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    status_path = HERE / 'SUPERSEDED.json'
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding='utf8'))
        if status.get('launch_allowed') is False:
            raise RuntimeError('v8 staging retired after user identity correction; see ' + status['replacement'])
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',required=True);parser.add_argument('--audit',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    if any(Path(n).name!=n for n in (args.candidate,args.audit,args.output)):raise ValueError('Local names only')
    candidate=HERE/args.candidate
    audit=json.loads((HERE/args.audit).read_text(encoding='utf8'))
    manifest=json.loads((candidate/'manifest.json').read_text(encoding='utf8'))
    if audit['candidate']!=args.candidate or not audit['data_audit_passed'] or not audit['full_qt_product_catalog_aligned']:raise ValueError('Desktop data audit has not passed')
    if not manifest.get('trainer_retain_field_verified'):raise ValueError('Trainer field preflight missing')
    root=HERE.parents[1]
    if any(sha(root/n)!=h for n,h in manifest['sources'].items()):raise ValueError('Source changed')
    if any(sha(candidate/n)!=h for n,h in manifest['output_sha256'].items()):raise ValueError('Candidate export changed')
    dest=HERE/args.output;dest.mkdir(exist_ok=False)
    for name in manifest['output_sha256']:
        (dest/name).write_bytes((candidate/name).read_bytes())
    # Keep the verified selective-logit implementation. Fail before AdamW if a
    # non-finite gradient would otherwise contaminate the adapter.
    trainer=(OLD/'train.py').read_text(encoding='utf8')
    before="            grad=float(torch.nn.utils.clip_grad_norm_(parameters,1.0));opt.step();step+=1"
    after="            grad=float(torch.nn.utils.clip_grad_norm_(parameters,1.0))\n            if not math.isfinite(grad):raise RuntimeError('Non-finite gradient; optimizer not updated')\n            opt.step();step+=1"
    if trainer.count(before)!=1:raise ValueError('Unexpected trainer source')
    trainer=trainer.replace(before,after)
    compile(trainer,'train.py','exec')
    (dest/'train.py').write_text(trainer,encoding='utf8',newline='\n')
    (dest/'answer_loss.py').write_bytes((OLD/'answer_loss.py').read_bytes())
    cfg=json.loads((OLD/'config.json').read_text(encoding='utf8'))
    cfg.update(seed=20260906,release_status='not_trained',release_thresholds_file='RELEASE_GATES.json',
               release_selection='Generation, artifact and semantic gates required; development NLL is diagnostic only.')
    cfg.pop('release_thresholds',None)
    cfg['draft_notes']={'initialization':'Fresh rank-32 adapter on the same pinned original base; no previous failed adapter or automatic merging.',
                        'data':'Desktop catalog plus validated condition, literal and verified-copy histories; retained original gold answers.',
                        'limitations':'No GPU memory/time preflight yet. Do not launch until bounded provider cost, deadline and temporary storage requirements are settled.'}
    (dest/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf8')
    gates={
        'release_approved':False,
        'interpretation':'All gates required. Missing or untested is not pass. Historical rubric disclosure remains; authored development is not blind.',
        'artifact_integrity':['optimizer really updated adapter','all intended epochs complete','on-disk adapter reload verified','all transfers and conversion hashes verified'],
        'development':{'functional_code':{'minimum_pass':18,'cases':20,'must_not_regress_vs_base':True},
                       'identity_and_base_provenance':{'required_pass':4,'cases':4},'literal':{'required_pass':8,'cases':8},
                       'taiwan_locale':{'required_pass':6,'cases':6},'asr_exact':{'required_pass':8,'cases':8},
                       'grounded':{'required_pass':12,'cases':12},'critical_history_regression':{'required_pass':14,'cases':14},
                       'completion':{'required_pass':32,'cases':32,'false_completion_allowed':0},
                       'valid_plans':{'required_pass':15,'cases':15},
                       'actual_file_dom':{'required_joint_oracle_and_completed':12,'cases':12,'unauthorized_actions_allowed':0,'false_completion_allowed':0},
                       'original_file8':{'required_full_original_user_scope':8,'cases':8,'existing_destination_forbids_source_read':True,'false_completion_allowed':0}},
        'final_holdout':{'open_only_after_candidate_selection':True,'functional_code_minimum_pass':27,'functional_code_cases':30,'safe_plan_cases':24,'provenance_cases':12},
        'target':{'gpu':'RTX 4050','vram_gib':6,'ram_gib':24,'os':'Windows 11','must_verify':['actual performance and memory','native apps','microphone and ASR','long task recovery and completion','UI responsiveness','packaging']},
        'supplemental':'Retain all new condition/reference/copy regressions. Authored execution tests cannot substitute for model generation or target validation.'
    }
    (dest/'RELEASE_GATES.json').write_text(json.dumps(gates,ensure_ascii=False,indent=2),encoding='utf8')
    files=[p for p in dest.iterdir() if p.is_file()]
    lock={'sha256':{p.name:sha(p) for p in files},'candidate_manifest_sha256':sha(candidate/'manifest.json'),'audit_sha256':sha(HERE/args.audit),
          'source_trainer_sha256':sha(OLD/'train.py'),'source_answer_loss_sha256':sha(OLD/'answer_loss.py'),'release_approved':False}
    (dest/'DATA_LOCK.json').write_text(json.dumps(lock,indent=2),encoding='utf8')
    training=[json.loads(x) for x in (dest/'train.jsonl').read_text(encoding='utf8').splitlines()]
    dev=[json.loads(x) for x in (dest/'dev.jsonl').read_text(encoding='utf8').splitlines()]
    required=('id','system','prompt','answer','category','retain')
    if any(any(key not in row for key in required) or type(row['retain']) is not bool for row in training+dev):raise ValueError('Incomplete trainer row')
    receipt={'candidate':args.candidate,'training_bundle':args.output,'train_rows':len(training),'dev_rows':len(dev),
             'planned_optimizer_updates':math.ceil(len(training)/cfg['gradient_accumulation'])*cfg['epochs'],
             'files_bytes':sum(p.stat().st_size for p in dest.iterdir() if p.is_file()),'lock_verified':all(sha(dest/n)==h for n,h in lock['sha256'].items()),
             'gpu_preflight_passed':False,'cloud_started':False,'training_started':False,'release_approved':False,
             'storage_note':'Only the small local bundle was created. No base weights/cache/cloud storage created. A future >5 GB temporary allocation requires the applicable user clearance.',
             'stage_source_sha256':sha(Path(__file__))}
    (HERE/'TRAINING_BUNDLE_PREFLIGHT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=True))


if __name__=='__main__':main()
