"""Diagnostic evidence projection; no authorization or completion decisions."""
import copy
import json


def project_messages(messages):
    """Remove planned goals only, retaining every actual argument/result field.

    Not a claim that untrusted tool output is safe or semantically sufficient.
    No predicate here can promote a task to completed.
    """
    result=copy.deepcopy(messages)
    payload=json.loads(result[-1]['content'])
    history=payload['observed_history']
    goals=[]
    for index,row in enumerate(history,1):
        if 'goal' in row:goals.append({'sequence_index':index,'goal':row.pop('goal')})
    payload['successful_explicit_final_responses']=[
        {'sequence_index':i,'output':row.get('output'),'verified':row.get('verified')}
        for i,row in enumerate(history,1)
        if row.get('tool')=='FINAL_RESPONSE' and row.get('ok') is True]
    result[0]['content']+=(
        '\n此核對輸入刻意移除步驟的預定goal；預定要做的事不是觀察證據。'
        'args是已呼叫工具的參數，output/evidence才描述該次工具結果；不得由參數裡的願望推斷未執行的動作。'
        'successful_explicit_final_responses只列出歷史中成功的FINAL_RESPONSE輸出；空陣列代表沒有這種明確回覆步驟，'
        '不是自動判失敗：只在原始需求要求特定回覆時核對它，不能替未要求回覆的任務增加條件。'
        '只核對原始需求；不要用計畫文字補足缺少的操作、順序、檔案內容或回覆。')
    result[-1]['content']=json.dumps(payload,ensure_ascii=False)
    return result,goals
