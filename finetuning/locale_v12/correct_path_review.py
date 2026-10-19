"""Correct an escaping-display interpretation; preserve original reports."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    for version,folder in ((1,'draft-v1'),(2,'candidate-v2')):
        raw=HERE/f'epoch3-locale-v{version}.jsonl'
        prior=HERE/f'epoch3-locale-v{version}.review.json'
        report=json.loads(prior.read_text(encoding='utf8'))
        data={r['id']:r for r in map(json.loads,(HERE/folder/'dev.jsonl').read_text(encoding='utf8').splitlines())}
        outputs={r['id']:r for r in map(json.loads,raw.read_text(encoding='utf8').splitlines())}
        assert report['raw_sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()
        for check in report['checks']:
            if check['id'].endswith('recognition-literal'):
                parsed=json.loads(outputs[check['id']]['text'])
                path=parsed['path'] if isinstance(parsed,dict) else parsed
                expected=data[check['id']]['oracle']['json_expected']['path']
                assert path==expected
                check['decoded_literal_passed']=True
                if version==1:
                    check['strict_expected_object_passed']=check.pop('passed')
                    check['status']='ambiguous_prompt_not_counted_as_confirmed_model_failure'
                    check['detail']='Decoded path is exact. Output is a JSON string rather than the expected object, but original field-only wording is ambiguous. Supersedes erroneous doubled-separator explanation.'
                else:
                    check['detail']='Decoded path and JSON object both exactly match. Explicit object instruction resolves the v1 shape ambiguity; no weight change.'
            if check['id'].endswith('literal-second-unc'):
                parsed=json.loads(outputs[check['id']]['text'])['path']
                expected=data[check['id']]['oracle']['json_expected']['path']
                check['detail']=f'Decoded path has {parsed.count(chr(92))} backslashes; expected {expected.count(chr(92))}. Leading UNC prefix has one instead of two. Exact path failure.'
        report['passed']=sum(c.get('passed') is True for c in report['checks'])
        report['confirmed_failed']=sum(c.get('passed') is False for c in report['checks'])
        report['ambiguous']=sum('passed' not in c for c in report['checks'])
        report['supersedes_review']=prior.name
        report['superseded_review_sha256']=hashlib.sha256(prior.read_bytes()).hexdigest()
        report['correction']='Path escaping must be judged after JSON decoding, not from nested log display. Original outputs retained; no rerun for this correction.'
        with (HERE/f'epoch3-locale-v{version}.review-corrected.json').open('x',encoding='utf8') as out:json.dump(report,out,ensure_ascii=False,indent=2)
        print(json.dumps({k:report[k] for k in ('passed','confirmed_failed','ambiguous')}))


if __name__=='__main__':main()
