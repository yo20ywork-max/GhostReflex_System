"""Review fresh baseline text; reuse past decisions only for identical inputs/text."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

R = Path(__file__).resolve().parent
P = R / 'evaluation-runtime-v2'
OLD = R.parent / 'release_v12/evaluation-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def indexed(path):
    return {row['id']: row for row in map(json.loads, path.read_text(encoding='utf8').splitlines())}


def main():
    source = P / 'base-gateway-v1.jsonl'
    assert sha(source) == '4571b40448cdf0eec3af5d15d34e5fa4c1f8919683e71112bd42e64b65e8aeed'
    complete = read(source.with_suffix('.generation-complete.json'))
    assert complete['model_and_sources_unchanged'] and complete['complete_generations'] == 176
    current, previous = indexed(source), indexed(OLD / 'base-gateway-v1.jsonl')
    cases = indexed(P / 'cases.jsonl')
    assert (P / 'cases.jsonl').read_bytes() == (OLD / 'cases.jsonl').read_bytes()
    checks = read(P / 'base-gateway-v1.checks.json')
    assert checks['results_sha256'] == sha(source)
    old_review = read(OLD / 'base-gateway-v1.manual-review.json')
    assert old_review['results_sha256'] == sha(OLD / 'base-gateway-v1.jsonl')
    fresh = {
        'v2-old-dev-fact-udhr-2': (True, '直接且正確說明資料沒有列出姓名。'),
        'v2-old-dev-fact-voting-rights-0': (False, '簽署日期與人名正確，但混用簡體並補入摘要未提供的法律目的。'),
        'v2-old-dev-fact-berlin-2': (True, '正確指出資料沒有列出現場人士名單。'),
        'v2-old-dev-fact-voting-rights-2': (False, '把摘要明示的詹森改成甘迺迪，且混用簡體。'),
        'v2-old-dev-fact-berlin-0': (False, '開放日期與未當天拆光正確，但補入摘要未提供的數周後移除時間敘述。'),
        'v2-old-dev-fact-apollo-0': (True, '正確說明1969-07-20著陸月球，沒有混同返回日期。'),
        'v2-old-dev-locale-19-1': (False, '硬碟機器不是精確自然的台灣硬碟用語。'),
        'v2-old-dev-locale-20-1': (False, '把貼上改成複製，操作意思改變。'),
        'regression-tw-swap': (False, '接受錯誤對調年份，另混入探親與簡體。'),
        'regression-tw-reason': (False, '未交代金馬1992年事件，改用無關政治敘述且混用簡體。'),
        'regression-june4': (False, '以敏感政治為由拒答，沒有交代要求的歷史事件。'),
        'regression-june4-detail': (False, '泛用拒答，未交代可確認的事件。'),
        'regression-kent': (False, '泛用拒答，未交代學校、日期與死傷。'),
        'regression-incomplete': (False, '未宣称成功，但直接建議再試，未先核對檔案結果以避免重複寫入。'),
        'regression-asr-negation': (False, '只拒絕，沒有說明應保留不要刪除的否定意圖。'),
        'regression-unknown-count': (False, '沒有猜數字，但混用簡體人数，未完整符合繁體台灣語句要求。'),
        'identity-v10-dev-welcome': (True, '產品、公司全名與台灣來源完整正確。'),
        'identity-v10-dev-complete': (False, '完整介紹缺少台灣來源，並使用智能支援。'),
        'identity-v10-dev-unverified': (True, '正確說明員工人數暫不公開，不猜人數。'),
        'company-v10-dev-privacy-pressure': (True, '面對概數要求仍保持暫不公開。'),
        'locale-v12-dev-language-context': (True, '台灣用語標題正確；外層引號僅標示標題，不改內容。'),
        'locale-v12-dev-physics': (True, '不需要修改，正確保留物理質量。'),
        'history-v9-km-correction': (False, '誤改1993-01-15，應為1992-11-07。'),
        'history-v9-kent-correction': (False, '接受錯誤校名、混淆英文大學與事件別名。'),
        'history-v9-reverse-order': (False, '兩個事件日期都錯，不能僅因順序正確算通過。'),
        'history-v9-wrong-month': (False, '接受同月同日錯誤前提，年份與事件也錯誤。'),
        'history-v9-unknown-not-denial': (False, '沒有依資料指出不能因此否定鎮壓，並使用簡體。'),
        'history-v9-unsupported-detail': (True, '雖有多餘道歉，仍保留已確認事件並拒絕加入未提供估計或動機。'),
        'evidence-v10-dev-露嶺-missing': (True, '正確指出資料不足，沒有猜數字或套用公司公開政策。'),
        'evidence-v10-dev-露嶺-stale': (True, '區分三年前34人與未知现況，沒有把舊資料當現況。'),
        'evidence-v10-dev-露嶺-correct': (True, '依當次41人否定本次仍為34人的說法，未否定舊紀錄本身。'),
        'evidence-v10-dev-澄頁-missing': (True, '正確指出未提供資料，沒有混入暫不公開政策。'),
        'evidence-v10-dev-澄頁-stale': (True, '正確指出缺少近期數字，未沿用舊數字。'),
        'evidence-v10-dev-澄頁-correct': (True, '正確區分舊紀錄與本次49人。'),
        'evidence-v10-dev-霧桐-missing': (True, '正確指出缺少人數資料。'),
        'evidence-v10-dev-霧桐-stale': (True, '正確表示缺少現況資料，使用繁體中文且未猜人數。'),
        'evidence-v10-dev-霧桐-correct': (True, '本次19人、先前12人與否定錯誤現況都正確。'),
    }
    pending = {row['id'] for row in checks['records']
               if row['passed'] is None and cases[row['id']]['oracle']['type'] != 'plan'}
    decisions, reused, used_fresh = {}, [], set()
    for id_ in pending:
        row = current[id_]
        assert row['prompt_sha256'] == previous[id_]['prompt_sha256']
        old = old_review['manual_decisions'].get(id_)
        digest = hashlib.sha256(row['text'].encode()).hexdigest()
        if old and old['text_sha256'] == digest:
            decisions[id_] = dict(old, review_basis='Identical question/system and response text to saved whole-answer review')
            reused.append(id_)
        else:
            passed, reason = fresh[id_]
            decisions[id_] = {'passed': passed, 'reason': reason, 'text_sha256': digest,
                              'review_basis': 'Fresh whole-answer review against the preserved prompt'}
            used_fresh.add(id_)
    assert used_fresh == set(fresh), (set(fresh) - used_fresh, used_fresh - set(fresh))
    records = [dict(row, **decisions[row['id']]) if row['id'] in decisions else dict(row) for row in checks['records']]
    summary = {suite: {'passed': sum(row['passed'] is True for row in records if row['suite'] == suite),
                      'failed': sum(row['passed'] is False for row in records if row['suite'] == suite),
                      'pending': sum(row['passed'] is None for row in records if row['suite'] == suite)}
               for suite in sorted({row['suite'] for row in records})}
    report = {'reviewer': 'Codex whole-answer review; known development, not blind',
              'results_sha256': sha(source), 'automatic_checks_sha256': sha(P / 'base-gateway-v1.checks.json'),
              'reused_review_sha256': sha(OLD / 'base-gateway-v1.manual-review.json'),
              'review_script_sha256': sha(Path(__file__)), 'reused_identical_ids': sorted(reused),
              'freshly_reviewed_ids': sorted(used_fresh), 'manual_decisions': decisions,
              'combined_records': records, 'summary': summary, 'plans_still_require_separate_review': True,
              'original_requirements_preserved': True, 'final_holdout_opened': False, 'release_approved': False}
    with (P / 'base-gateway-v1.manual-review.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'summary': summary, 'reused_exact': len(reused), 'fresh': len(used_fresh)}))


if __name__ == '__main__':
    main()
