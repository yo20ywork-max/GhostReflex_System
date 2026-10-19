"""Diagnostic projection of the current runtime's successful final rendering.

No instructions are extracted from the request. This is observed delivery data,
not proof of fulfilled actions. Unknown reconstruction cannot prove delivery.
"""
import copy
import json


_DIRECT_OUTPUT = {'MODEL_GENERATE', 'TRANSLATE_TEXT', 'READ_TEXT_FILE', 'BROWSER_GET_TEXT', 'HTTP_GET'}


def candidate_visible_reply(history):
    if not history:
        return {'known': False, 'text': None, 'basis': 'no_history'}
    if not all(isinstance(row, dict) for row in history):
        return {'known': False, 'text': None, 'basis': 'invalid_history'}
    final_index = next((i for i in range(len(history) - 1, -1, -1)
                        if history[i].get('tool') == 'FINAL_RESPONSE'), None)
    if final_index is not None:
        final = history[final_index]
        if final.get('ok') is not True or not isinstance(final.get('output'), str):
            return {'known': False, 'text': None, 'basis': 'failed_or_unknown_final_response'}
        return {'known': True, 'text': final['output'], 'basis': 'explicit_final_response',
                'sequence_index': final_index + 1}
    actual = [(i, row) for i, row in enumerate(history, 1) if row.get('tool') != 'CONDITION_SKIP']
    if not actual:
        return {'known': False, 'text': None, 'basis': 'no_executed_steps'}
    last_index, last = actual[-1]
    if last.get('ok') is not True:
        return {'known': False, 'text': None, 'basis': 'last_step_failed'}
    if last.get('tool') in _DIRECT_OUTPUT:
        value = last.get('output')
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False, default=str)
            text = text if len(text) <= 30000 else text[:30000] + '…'
        return {'known': True, 'text': text, 'basis': 'direct_last_output', 'sequence_index': last_index}
    success = sum(row.get('ok') is True for _, row in actual)
    verified = sum(row.get('ok') is True and row.get('verified') is True for _, row in actual)
    skipped = len(history) - len(actual)
    return {'known': True,
            'text': f'任務狀態：completed。成功步驟 {success}/{len(actual)}；已驗證 {verified}；僅送出命令、未能獨立驗證 {success - verified}。'
                    + (f'因條件不符略過 {skipped} 步。' if skipped else ''),
            'basis': 'generic_runtime_summary'}


def project_delivery_messages(messages):
    result = copy.deepcopy(messages)
    payload = json.loads(result[-1]['content'])
    history = payload['observed_history']
    delivery = candidate_visible_reply(history)
    goals = []
    for i, row in enumerate(history, 1):
        if 'goal' in row:
            goals.append({'sequence_index': i, 'planned_goal': row.pop('goal')})
    payload['candidate_user_visible_reply'] = delivery
    result[0]['content'] += (
        '\n額外核對實際交付：candidate_user_visible_reply 是依目前 runtime 回覆規則由程式重建的候選訊息，'
        '不是新的工具觀察。known=true 時，text 才是任務若以 completed 結束會呈現的文字；'
        '空字串代表沒有文字，不是使用者指定的成功回覆。known=false 時不能假設回覆已交付。'
        '請分開核對：(1)每個動作、條件與限制；(2)使用者要求的回覆內容。任一缺少就 complete=false。'
        '沒有要求指定回覆時，不可額外強求 FINAL_RESPONSE；一般直接讀取輸出也可以是有效交付。'
        '條件式任務須先依真實證據選擇適用分支，再比較該分支的回覆與 text；'
        '已正確跳過複製不等於已回覆指定文字。'
        '預定 goal 已移除，不能把原先預定要回覆的話當成已呈現；不要用 success 或 completed 字樣代替原需求。')
    result[-1]['content'] = json.dumps(payload, ensure_ascii=False)
    return result, goals
