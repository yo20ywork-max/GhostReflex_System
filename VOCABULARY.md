# Unicode 詞表擴充

詞表保留原有 214 個 token 的 ID，追加 256 個 UTF-8 byte token，共 470 個。
原有字元仍使用一個 token；其他字元使用 1–4 個 byte token。這涵蓋所有
Unicode scalar values，包括罕見漢字、各國文字、emoji、控制字元及未指派碼位。
不接受孤立的 UTF-16 surrogate。多字元 emoji 會分成多個字元編碼。

新增 token 以舊 `<UNK>` 權重初始化，既有權重保持不變。這是編碼覆蓋擴充，
不是語意訓練：新字元雖已具有不同的 token 序列，模型還沒有學到其含義。
本次沒有執行訓練或啟動自進化守護程式。

`tokenizer.py` 是訓練、微調及兩版原始碼推論的共同編解碼器。
訓練不再根據單一資料集重建／縮小詞表；140 的長度上限現在明確以 token
計算，目標截斷避免切斷 UTF-8 字元，過長提示會明確報錯。
`train.py` 仍然是從頭訓練，並非續訓入口；不要為了套用詞表而執行它。

`expand_vocab.py` 負責一次性配對遷移詞表與 checkpoint，執行前備份至
`backups/vocab_<時間>/`，重複執行不會再次擴充。遷移時應先關閉正在使用
或寫入這些資源的 GhostReflex / 訓練程序。還原時必須一起還原詞表、權重
及相應版本的程式，不能單獨還原其中一份。

本次更新的是專案根目錄的原始碼版本；既有 `dist/GhostReflex_Portable`
執行檔沒有重建，不會自動取得本次修改。使用 `python run_daemon.py` 啟動
更新後的版本。後續發行須重新打包，並確認執行檔內的 tokenizer、詞表與
權重是同一組。

驗證：`python -m unittest discover -s tests -v`
