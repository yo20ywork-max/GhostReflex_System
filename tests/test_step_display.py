"""Receipt streaming preserves the identity and literal contents of visible rows."""
import unittest
from PySide6.QtCore import QCoreApplication, QPersistentModelIndex
from PySide6.QtTest import QSignalSpy
from desktop_ui.steps import StepListModel
from desktop_ui.progress import step_display


class StepDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_streaming_preserves_existing_row_without_model_reset(self):
        model = StepListModel()
        literal = '  原文\r\n\t資料 <b>不是標籤</b> μ🙂  '
        first = {'label': '步驟 1', 'status': '工具已回應', 'detail': literal}
        model.append(first)
        index = QPersistentModelIndex(model.index(0, 0))
        resets = QSignalSpy(model.modelReset)
        inserts = QSignalSpy(model.rowsInserted)
        first['detail'] = '外部物件已變動'
        for number in range(2, 102):
            model.append({'label': f'步驟 {number}', 'status': '工具已回應', 'detail': str(number)})
        self.assertTrue(index.isValid())
        self.assertEqual(index.data(model.ItemRole)['detail'], literal)
        self.assertEqual((model.rowCount(), resets.count(), inserts.count()), (101, 0, 100))
        returned = index.data(model.ItemRole)
        returned['detail'] = '不要改寫模型內的原文'
        self.assertEqual(index.data(model.ItemRole)['detail'], literal)

    def test_task_switch_clears_prior_evidence_and_invalid_input_is_atomic(self):
        model = StepListModel()
        model.append({'label': '舊任務', 'status': '未完成', 'detail': '舊證據'})
        previous = QPersistentModelIndex(model.index(0, 0))
        with self.assertRaises(ValueError):
            model.replace([{'label': '錯誤輸入', 'status': '未知'}])
        self.assertTrue(previous.isValid())
        self.assertEqual(model.rowCount(), 1)
        model.clear()
        self.assertFalse(previous.isValid())
        self.assertEqual(model.rowCount(), 0)
        model.replace([{'label': '新任務', 'status': '尚未執行', 'detail': ''}])
        self.assertEqual(model.index(0, 0).data(model.ItemRole)['label'], '新任務')

    def test_conditional_skip_is_displayed_identically_live_and_from_history(self):
        proof = {'condition': {'step_id': 1, 'field': 'exists', 'equals': False}, 'observed': True}
        live = {'step_id': 3, 'tool': 'CONDITION_SKIP', 'ok': True, 'executed': False, **proof}
        saved = {'step_id': 3, 'tool': 'CONDITION_SKIP', 'ok': True, 'executed': False, 'evidence': proof}
        self.assertEqual(step_display(live), step_display(saved))
        row = step_display(live)
        self.assertEqual(row['status'], '條件不符，已略過')
        self.assertIn('沒有執行操作', row['detail'])
        self.assertNotIn('第 1 次', row['label'])

    def test_unrecorded_action_remains_uncertain(self):
        row = step_display({'step_id': 1, 'tool': 'WRITE_TEXT_FILE', 'ok': True, 'outcome_recorded': False})
        self.assertEqual(row['status'], '結果待核對')


if __name__ == '__main__':
    unittest.main()
