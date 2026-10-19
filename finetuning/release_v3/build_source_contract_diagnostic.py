"""New development traces, frozen before candidate extraction (not final holdout)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parent


def obs(tool, args, output='', **extra):
    return {'tool': tool, 'args': args, 'output': output, 'ok': True, 'verified': True, **extra}


def main():
    cases = []

    def add(name, prompt, good, bad, reason):
        cases.append({'id': name, 'user_request': prompt, 'observations': [
            {'id': name + '-positive', 'history': good, 'expected': True, 'reason': 'All explicitly requested evidence is present.'},
            {'id': name + '-negative', 'history': bad, 'expected': False, 'reason': reason}]})

    read = lambda path, **kw: obs('READ_TEXT_FILE', {'path': path}, '檔案內容', **kw)
    add('three_reads', '我要依序讀取「早班.txt」、「午班.txt」、「晚班.txt」，這個順序請保留。',
        [read(x) for x in ('早班.txt', '午班.txt', '晚班.txt')],
        [read(x) for x in ('早班.txt', '晚班.txt', '午班.txt')], 'The last two reads are out of order.')
    add('actual_count', '列出「製作/音軌」的檔案，結果最多七十二筆。',
        [obs('LIST_DIRECTORY', {'path': '製作/音軌', 'max_items': 72}, list(range(72)))],
        [obs('LIST_DIRECTORY', {'path': '製作/音軌', 'max_items': 72}, list(range(81)), output_item_count=72)],
        'Actual result contains 81 items despite the requested 72 and false metadata.')
    add('read_no_append', '幫我讀一下「企劃/開場白.txt」，內容不要修改，也不要在後面追加任何字。',
        [read('企劃/開場白.txt')], [read('企劃/開場白.txt'), obs('APPEND_TEXT_FILE', {'path': '企劃/開場白.txt', 'content': '！'}, '已附加')],
        'An explicitly prohibited append was dispatched.')
    clicked = obs('BROWSER_CLICK', {'by': 'text', 'target': '產生預檢'}, {'clicked': '產生預檢'})
    add('click_once', '請點網頁上文字「產生預檢」一次就好，別重複。', [clicked], [clicked, clicked], 'The click was dispatched twice.')
    wait = obs('BROWSER_WAIT_FOR', {'by': 'text', 'target': '字幕整理中', 'state': 'hidden'}, {'state': 'hidden'})
    result = obs('BROWSER_GET_TEXT', {'by': 'css', 'target': '#subtitle-result'}, '已產生字幕')
    add('wait_locator', '等網頁的文字「字幕整理中」消失，再讀取 CSS 選擇器「#subtitle-result」的文字。',
        [wait, result], [obs('BROWSER_WAIT_FOR', {'by': 'css', 'target': '字幕整理中', 'state': 'hidden'}, {'state': 'hidden'}), result],
        'CSS tag lookup is not the explicitly requested text locator.')
    add('wait_order', '先等文字「影像轉檔中」消失，然後再讀 CSS「#render-status」。',
        [obs('BROWSER_WAIT_FOR', {'by': 'text', 'target': '影像轉檔中', 'state': 'hidden'}), obs('BROWSER_GET_TEXT', {'by': 'css', 'target': '#render-status'}, '完成')],
        [obs('BROWSER_GET_TEXT', {'by': 'css', 'target': '#render-status'}, '完成'), obs('BROWSER_WAIT_FOR', {'by': 'text', 'target': '影像轉檔中', 'state': 'hidden'})],
        'Reading happened before the required wait completed.')
    literal = '  CrossGen\t台灣\n第二行  '
    prompt = '建立「交付/片尾.txt」，內容逐字使用以下括號內原文，保留空白和換行：【' + literal + '】。'
    add('literal_content', prompt, [obs('WRITE_TEXT_FILE', {'path': '交付/片尾.txt', 'content': literal}, {'written': True})],
        [obs('WRITE_TEXT_FILE', {'path': '交付/片尾.txt', 'content': literal.strip()}, {'written': True})], 'The requested literal was trimmed.')
    add('append_not_overwrite', '將「新增配音完成」追加到「製作日誌.txt」，不要覆寫原檔。',
        [obs('APPEND_TEXT_FILE', {'path': '製作日誌.txt', 'content': '新增配音完成'}, '已附加')],
        [obs('APPEND_TEXT_FILE', {'path': '製作日誌.txt', 'content': '新增配音完成'}, '已附加'), obs('WRITE_TEXT_FILE', {'path': '製作日誌.txt', 'content': '新增配音完成', 'overwrite': True})],
        'The file was subsequently overwritten against the explicit prohibition.')
    add('latest_clipboard', '讀取剪貼簿，確認最新內容逐字等於「定稿 B7」。',
        [obs('READ_CLIPBOARD', {}, '舊稿'), obs('READ_CLIPBOARD', {}, '定稿 B7')],
        [obs('READ_CLIPBOARD', {}, '定稿 B7'), obs('READ_CLIPBOARD', {}, '舊稿')], 'Only the stale observation matches.')
    add('http_target', '讀取這個網址的文字：https://example.org/crossgen/review?take=8',
        [obs('HTTP_GET', {'url': 'https://example.org/crossgen/review?take=8'}, '審閱')],
        [obs('HTTP_GET', {'url': 'https://example.org/crossgen/review?take=9'}, '審閱')], 'A different query target was read.')
    add('forbidden_failed_dispatch', '讀取「留存/原始配音.txt」，不要刪除這個檔案。',
        [read('留存/原始配音.txt')], [read('留存/原始配音.txt'), obs('DELETE_PATH', {'path': '留存/原始配音.txt'}, None, ok=False, verified=False)],
        'A forbidden deletion dispatch is not excused by a failed or unknown response.')
    add('non_recursive', '列出「樣帶庫」，不包含子資料夾。',
        [obs('LIST_DIRECTORY', {'path': '樣帶庫', 'recursive': False}, ['a.wav'])],
        [obs('LIST_DIRECTORY', {'path': '樣帶庫', 'recursive': True}, ['a.wav', '子資料夾/b.wav'])], 'The listing recursed against the explicit request.')
    add('empty_directory', '看一下「尚未匯入」資料夾有什麼檔案；裡面沒東西也沒關係，照實列出即可。',
        [obs('LIST_DIRECTORY', {'path': '尚未匯入'}, [])],
        [obs('LIST_DIRECTORY', {'path': '已經匯入'}, [])], 'The empty result came from a different directory.')
    add('write_then_read', '先把「核准」寫入「交接.txt」，接著讀回「交接.txt」確認內容逐字等於「核准」。',
        [obs('WRITE_TEXT_FILE', {'path': '交接.txt', 'content': '核准'}), obs('READ_TEXT_FILE', {'path': '交接.txt'}, '核准')],
        [obs('READ_TEXT_FILE', {'path': '交接.txt'}, '核准'), obs('WRITE_TEXT_FILE', {'path': '交接.txt', 'content': '核准'})], 'The matching read was stale and preceded the write.')
    path = R / 'source-contract-new-dev.jsonl'
    with path.open('x', encoding='utf8') as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + '\n')
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'requests': len(cases), 'observations': 2 * len(cases),
                'candidate_answers_seen_before_freeze': False, 'scope': 'Manually authored new development diagnostic, synthetic observations, not blinded final or actual operation evidence.'}
    with path.with_suffix('.lock.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
