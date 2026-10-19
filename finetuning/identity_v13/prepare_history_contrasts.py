"""Grounded event/date binding and quotation contrasts; no evaluation answers imported."""
import hashlib
import itertools
import json
from pathlib import Path

R = Path(__file__).resolve().parent
NEUTRAL = '使用台灣繁體中文，依問題直接回答，遵守指定格式。程式、路徑和引文保持原文。不要捏造資訊。'


def main():
    destination = R / 'history-additions-v1'
    if destination.exists():
        raise FileExistsError(destination)
    events = [
        ('tw', '台灣地區解除戒嚴', '1987-07-15', '1987年7月15日', 'https://www.president.gov.tw/NEWS/11454'),
        ('km', '金門、馬祖終止戰地政務', '1992-11-07', '1992年11月7日', 'https://kmfinance.kinmen.gov.tw/cp.aspx?n=2B1FBC681FF4F40B'),
        ('election', '台灣首次總統直接民選', '1996-03-23', '1996年3月23日', 'https://www.president.gov.tw/NEWS/10214'),
        ('kent', '肯特州立大學槍擊事件', '1970-05-04', '1970年5月4日', 'https://www.kent.edu/may-4-historical-accuracy'),
    ]
    rows, internal = [], []
    def add(slug, prompt, answer, sources, category='history'):
        rows.append({'id': 'history-v13-' + slug, 'group': 'history-v13-' + slug,
                     'category': category, 'split': 'train', 'system': NEUTRAL,
                     'prompt': prompt, 'answer': answer})
        internal.append({'id': rows[-1]['id'], 'factual_sources': sources,
                         'purpose': 'Internal factual verification only; not serialized as model messages.'})
    for slug, event, iso, date, url in events:
        year, month, day = map(int, iso.split('-'))
        wrong = f'{year + 2}年{month}月{day}日'
        variants = [
            ('caption', f'展覽的時間軸要加入「{event}」，給我一句含確切日期的簡短圖說。', f'{date}，{event}。'),
            ('object', f'資料表新增一筆「{event}」。只回JSON物件，event填事件名稱，date填西元日期，格式YYYY-MM-DD。', json.dumps({'event': event, 'date': iso}, ensure_ascii=False)),
            ('roc', f'「{event}」換算成民國紀年的完整日期怎麼寫？不要列出其他事件。', f'民國{year - 1911}年{month}月{day}日。'),
            ('edit', f'編輯把「{event}」寫在{wrong}的年表欄位。請給正確日期並說明這個年份是否對。', f'年份不對；{event}的日期是{date}。'),
            ('quote', f'這是逐字轉錄任務，請原樣複製引號內的草稿，不要查核或修改日期：「{wrong}，{event}。」', f'{wrong}，{event}。'),
            ('iso', f'把「{event}」的發生日期放入行事曆，只輸出西元數字日期YYYY/MM/DD。', iso.replace('-', '/')),
            ('provided', f'以下是待轉換資料，請只輸出date欄位的值，不補其他內容：' + json.dumps({'event': event, 'date': iso, 'note': '保留欄位值'}, ensure_ascii=False), iso),
            ('missing', f'這份摘要只寫「{date}，{event}」。摘要有提供當日每位在場者的姓名和住址嗎？', '沒有；這份摘要只有日期與事件名稱，沒有提供每位在場者的姓名或住址。'),
        ]
        for kind, prompt, answer in variants:
            add(slug + '-' + kind, prompt, answer, [url], 'literal' if kind == 'quote' else 'history')
    for index, order in enumerate(itertools.permutations(events[:3])):
        names = '、'.join(x[1] for x in order)
        add(f'ordered-json-{index}', f'請依這個順序查填事件日期：{names}。只回JSON陣列，每筆包含event與date，日期用YYYY-MM-DD，不自行重排。',
            json.dumps([{'event': x[1], 'date': x[2]} for x in order], ensure_ascii=False), [x[4] for x in order])
        add(f'ordered-text-{index}', f'製作三張事件標籤，順序固定為：{names}。每行一件事，包含事件與完整年月日，不合併日期。',
            '\n'.join(f'{x[1]}：{x[3]}。' for x in order), [x[4] for x in order])
    source = 'https://nsarchive2.gwu.edu/NSAEBB/NSAEBB16/'
    summary = '1989年6月4日前後，北京發生軍隊武力鎮壓並造成死傷；不同資料中的死亡估計並不一致。'
    uncertainty = [
        ('brief', '請用兩句繁體中文說明六四鎮壓的基本事件，不寫無法確定的精確死亡總數。', '1989年6月4日前後，中國軍隊在北京以武力鎮壓示威者與民眾，造成死傷。精確死亡總數不能在缺乏可確認證據時任意填寫。'),
        ('claim', '編輯說「因為無法核定六四死亡總數，所以不能承認北京曾有軍隊鎮壓」。這個推論合理嗎？', '不合理。軍隊在北京武力鎮壓並造成死傷有相關紀錄；精確死亡總數的不確定性，不能否定事件本身。'),
        ('limited', '只依摘要回答，不延伸情節：' + summary + ' 問：這段資料能確定每位死者的姓名嗎？', '不能；摘要沒有列出每位死者的姓名。'),
        ('null', '只依摘要回JSON，event_confirmed是布林值，exact_deaths沒有確定數字就填null：' + summary,
         '{"event_confirmed":true,"exact_deaths":null}'),
        ('motive', '只依這段資料判斷能否替每位行動者加上個人動機：' + summary,
         '不能；摘要沒有提供每位行動者的個人動機，不應自行添加。'),
        ('mention', '我想了解1989年北京示威遭鎮壓的事件。可以直接說明已知事實，同時標出不知道的部分嗎？',
         '可以。1989年6月4日前後，中國軍隊在北京以武力鎮壓示威者與民眾，造成死傷。不同資料的傷亡估計有差異，不能把單一估計當作已確定的總數。'),
    ]
    for slug, prompt, answer in uncertainty:
        add('beijing-' + slug, prompt, answer, [source])
    assert len(rows) == 50
    old = R.parent / 'release_v12'
    excluded = list(map(json.loads, (old / 'dev.jsonl').read_text(encoding='utf8').splitlines()))
    excluded += list(map(json.loads, (old / 'evaluation-v1/cases.jsonl').read_text(encoding='utf8').splitlines()))
    assert not {r['prompt'] for r in rows} & {r['prompt'] for r in excluded}
    assert len({r['prompt'] for r in rows}) == len(rows)
    assert all('http' not in r['system'] + r['prompt'] + r['answer'] for r in rows)
    destination.mkdir()
    text = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    (destination / 'additions.jsonl').write_text(text, encoding='utf8')
    report = {'rows': len(rows), 'data_sha256': hashlib.sha256((destination / 'additions.jsonl').read_bytes()).hexdigest(),
              'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'authored_events': 4, 'beijing_uncertainty_questions': 6,
              'explicit_quotation_rows_preserve_inaccurate_drafts': 4,
              'exact_development_prompts_not_copied': True, 'topics_overlap_known_development': True,
              'source_identity_not_in_model_tokens': True, 'internal_source_records': internal,
              'source_review': 'Verified primary/official excerpts during this turn. Old date URLs lacked a direct date match; current supporting links retained here separately.',
              'training_ready': False, 'training_started': False, 'release_approved': False}
    (destination / 'PREPARATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'internal_source_records'}))


if __name__ == '__main__':
    main()
