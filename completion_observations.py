"""Disambiguate executor control metadata without changing raw observations."""
import copy


def checker_history(history):
    projected = copy.deepcopy(history)
    for row in projected:
        if 'terminal' in row:
            row['failure_requires_stop'] = row.pop('terminal')
    return projected


CONTROL_SEMANTICS = (
    'failure_requires_stop 是執行器的失敗處理設定：只有該步驟失敗時才決定是否停止；'
    'false 不代表步驟失敗或任務未完成，true 也不代表任務已完成。'
    'step_id 是步驟識別碼，不是預期步驟總數；重試後的歷史可能含失敗紀錄，'
    '不能以成功筆數小於歷史筆數單獨判定任務未完成。'
    '點選結果的 URL 與 title 是頁面背景資訊；同頁點選可能不改變網址或標題，'
    '不能僅因網址未變或標題為空就推定點選失敗。若原始需求要求導航或後續結果，仍須相應證據。'
)
