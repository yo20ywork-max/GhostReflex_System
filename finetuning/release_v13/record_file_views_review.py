"""Review all role responses and preserve new counterexamples, not just old passes."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
P = R / 'runtime-candidate/file_completion_views.py'
spec = importlib.util.spec_from_file_location('file_views_review', P)
views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(views)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def lines(p):
    return [json.loads(l) for l in p.read_text(encoding='utf8').splitlines()]


def main():
    target = R / 'FILE_COMPLETION_VIEWS_REVIEW.json'
    assert not target.exists()
    collected = {}
    for name in ['FILE_COMPLETION_VIEWS_V1', 'FILE_VIEWS_CONTROLS_V1', 'FILE_VIEWS_BASE_ROLES_V1']:
        path = R / (name + '.jsonl')
        summary, run, receipt = [read(R / (name + suffix)) for suffix in ['.summary.json', '.run.json', '.integrity.json']]
        assert summary['results_sha256'] == sha(path) and summary['sources_and_tag_unchanged']
        assert receipt['actual_model_unchanged'] and receipt['sources_unchanged'] and receipt['child_exit_code'] == 0
        assert all(sha(Path(p)) == h for p, h in run['sources'].items())
        if 'raw_sha256' in summary:
            assert summary['raw_sha256'] == sha(path.with_suffix('.raw.jsonl'))
        collected[name] = {'summary': summary, 'integrity_receipt_sha256': sha(R / (name + '.integrity.json'))}
    controlled = lines(R / 'FILE_VIEWS_CONTROLS_V1.jsonl')
    base = lines(R / 'FILE_VIEWS_BASE_ROLES_V1.jsonl')
    raw = {(r['case'], r['role']): r for r in lines(R / 'FILE_VIEWS_CONTROLS_V1.raw.jsonl')}
    by_case = {}
    for row in base:
        original = raw[(row['case'], row['role'])]['request']
        actual = dict(row['request'])
        actual['model'] = original['model']
        assert actual == original
        assert row['valid']
        by_case.setdefault(row['case'], {})[row['role']] = row['value']
    base_results = []
    for row in controlled:
        outcome = views.aggregate(row['views'], by_case[row['case']])
        base_results.append({'case': row['case'], 'expected_complete': row['expected_complete'],
            'aggregate': outcome, 'role_verdicts': by_case[row['case']],
            'correct': outcome['complete'] is row['expected_complete']})
    assert sum(r['correct'] for r in base_results) == 5
    notes = {
        'correct_creative': '兩句繁體歡迎詞明確涵蓋初訪鄰居與修復舊物。E3內容角色誤拒，base同輸入接受；各操作與回覆均有證據。',
        'correct_summary': '三點摘要符合6月18日下午2點四樓、6月10日截止、三萬元。兩模型均接受；理由仍有越過角色範圍的敘述。',
        'wrong_summary_date': '唯一改動為6月18日變19日。兩模型均拒絕；base指出確切日期差異，E3只泛稱日期或金額不同。',
        'summary_without_readback': '摘要內容正確，但歷史只有來源讀取、結果寫入、最終回覆，沒有目的讀回。兩模型的操作角色均錯判satisfied，形成誤報。',
        'legitimate_status_translation': '使用者要求翻譯「尚未讀回。」；英文It has not been read back yet.符合要求。兩模型均誤拒，base甚至在理由提出與實際產出相同的譯文再稱不相符。',
        'correct_python_function': '純Python實作add(a,b)回傳a+b，符合來源整數相加規格。E3誤拒，base接受；不從這一題推論整體程式驗收通過。',
        'source_overwritten_before_copy': '工具歷史先有來源overwrite=true寫入，再複製修改後內容。兩模型都無視來源写入事實，錯稱來源保留並誤報完成。',
        'wrong_exact_reply': '要求備份完成，實際為備份完程。兩模型的交付角色均拒絕，檔案內容本身無誤。'}
    replay_notes = {
        'copy_correct': '合併判定與實際相符，角色理由籠統但沒有直接反證。',
        'merge_correct': '完整串接11字元正確；操作理由「未讀來源」與實際已讀來源矛盾，不能只憑正確布林認定理由可靠。',
        'empty_copy_correct': '零位元組排他複製、來源與目的讀回、回覆均有證據；此次各角色判定正確。',
        'merge_altered': '精確文字主程式比對攔下11對9字元的差異；各角色成功不會蓋過內容差異。',
        'creative_status_instead_of_welcome': '內容角色仍以缺少讀回／回覆為由拒絕，而非指出文案是工作狀態、不是兩句歡迎詞。布林正確但理由錯誤。',
        'summary_invented_facts': '內容角色正確指出來源事實不同；操作角色捏造覆寫取消，交付角色越界核對讀寫。',
        'v9_empty_copy_correct': '此次分開核對接受已驗證空檔與指定回覆，解決這份歷史輸入的誤拒；尚非新的自主操作驗收。',
        'v9_empty_copy_without_reply': '只移除FINAL_RESPONSE後正確拒絕，但理由仍混入讀回；讀回實際已有證據。'}
    tests = ['tests.test_file_completion_views_candidate', 'tests.test_artifact_completion_guard_candidate',
             'tests.test_artifact_evidence_candidate', 'tests.test_artifact_intent_v2', 'tests.test_artifact_intent_candidate']
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', *tests], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0 and 'Ran 43 tests' in result.stderr
    record = {'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'reports': collected,
        'replayed_eight_whole_reason_review': replay_notes,
        'new_controls_whole_reason_review': notes,
        'new_control_artifact_compilation_review': {'correct': 8, 'total': 8, 'scope': 'Type, source and destination only; not operation constraint coverage.'},
        'base_same_input_aggregate': {'records': base_results, 'correct': 5, 'total': 8, 'false_positives': 2,
                                    'only_model_name_changed': True},
        'controls': {'tests_run': 43, 'exit_code': result.returncode, 'output': result.stderr,
            'sources': {str(p.relative_to(ROOT)): sha(p) for p in [P, ROOT / 'tests/test_file_completion_views_candidate.py']}},
        'findings': [
            'Historical8boolean results improved4/8FP1 to8/8FP0, but several role reasons remained false or out of scope.',
            'New8positive/negative controls only3/8FP2 on E3; base same22role inputs5/8FP2. Switching to base does not fix release blockers.',
            'E3 rejects correct creative/code where base accepts on identical inputs: localized adaptation-associated regression evidence, not proof of global capability loss or its training cause.',
            'Both models accept missing required readback and source overwrite despite trusted contrary observations. Operation requirements must be bound to mechanical checks, not merely added to a prose prompt.',
            'Both models reject legitimate status translation; explicit positive/negative content contrasts and evidence-grounded explanations are needed. Never blacklist status phrases regardless of task intent.'],
        'next': [
            'Compile original operation obligations without showing results, with grounded request spans and targets; bind required readback, source preservation, new-file semantics and exact reply to actual history. Unknown requirements must remain unresolved rather than silently omitted.',
            'Prepare diverse evidence-grounded training/retention examples for correct creative/code/translation and specific factual differences. Keep all current controls out of new training and preserve original frozen holdout/identity requirements.',
            'Do not install this candidate or switch default models based on historical8/8. Re-run unchanged autonomous file8/full12/synthesis/full development and target hardware gates after composed checks and model behavior meet requirements.'],
        'all_three_inference_jobs_terminal': True, 'production_runtime_unchanged': True,
        'candidate_installed': False, 'model_default_changed': False, 'cloud_resources_created': False, 'release_approved': False}
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'historical': '8/8 FP0 with reason errors', 'new_e3': '3/8 FP2', 'new_base': '5/8 FP2', 'controls': 43, 'release_approved': False}))


if __name__ == '__main__':
    main()
