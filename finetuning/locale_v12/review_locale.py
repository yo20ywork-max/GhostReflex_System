"""Reproducible strict structured checks plus versioned manual language review."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    raw = HERE / 'epoch3-locale-v1.jsonl'
    data = HERE / 'draft-v1/dev.jsonl'
    rows = [json.loads(x) for x in data.read_text(encoding='utf8').splitlines()]
    outputs = [json.loads(x) for x in raw.read_text(encoding='utf8').splitlines()]
    assert [r['id'] for r in rows] == [r['id'] for r in outputs]
    manual = {
        'software-context': (True, '這款軟體不需要連線。', 'Accept a natural equivalent; not exact-gold scoring.'),
        'folder-context': (True, '將圖片放入新建立的資料夾。', 'Natural equivalent preserves newly created folder destination.'),
        'language-context': (False, 'Python 語言入門课程', 'Simplified 课 violates Traditional Chinese; terminology instruction not fully met.'),
        'physics': (True, '不需要；正確的科學用詞是「質量」。', 'Correctly retains the physical quantity.'),
    }
    checks = []
    for row, output in zip(rows, outputs):
        oracle = row['oracle']; text = output['text']
        if oracle['json_expected'] is not None:
            try:
                parsed = json.loads(text)
                passed = json.dumps(parsed, sort_keys=True, ensure_ascii=False) == json.dumps(oracle['json_expected'], sort_keys=True, ensure_ascii=False)
            except ValueError:
                parsed = None; passed = False
            detail = 'Strict JSON type, keys and values; whitespace/key order ignored.'
            if row['id'].endswith('recognition-literal'):
                detail += ' Original field-only wording is somewhat ambiguous; independently, decoded string doubles each path separator. Future version clarifies object shape.'
            if row['id'].endswith('spoken-save'):
                detail += ' 桌面上的檔案 names a file on Desktop, not the requested Desktop destination.'
        elif oracle['exact_required']:
            passed = text == row['answer']; detail = 'Exact literal, no normalization or stripping.'
        else:
            key = row['id'].removeprefix('locale-v12-dev-')
            passed, reviewed, detail = manual[key]
            assert text == reviewed, 'New output requires new manual review'
        checks.append(dict(id=row['id'],passed=passed,actual=text,detail=detail))
    report = dict(rows=len(checks),passed=sum(c['passed'] for c in checks),checks=checks,
        raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        data_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
        weights_changed=False,source_benefit_proven=False,blind=False,
        scope='Authored text-only development; synthetic ASR examples; no file actions or microphone capture.',
        release_approved=False)
    target = HERE/'epoch3-locale-v1.review.json'
    with target.open('x',encoding='utf8') as out:json.dump(report,out,ensure_ascii=False,indent=2)
    print(json.dumps({'passed':report['passed'],'rows':report['rows']},ensure_ascii=False))


if __name__ == '__main__':main()
