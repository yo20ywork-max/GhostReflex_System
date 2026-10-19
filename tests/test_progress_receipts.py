"""The UI must show the matching committed result or identify its text as a summary."""
import tempfile
import unittest
from pathlib import Path
from desktop_ui.progress import completed_progress, display_detail
from task_journal import TaskJournal


class ProgressReceipts(unittest.TestCase):
    def event(self, **values):
        return {'request_id': 'task-a', 'step_id': 4, 'attempt': 2, 'tool': 'READ_TEXT_FILE',
                'ok': True, 'output': '截短摘要…', 'error': None, **values}

    def test_exact_receipt_preserves_long_literal_and_other_tasks_cannot_replace_it(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = TaskJournal(Path(directory) / 'workspace_state/execution.sqlite3')
            try:
                literal = '  開頭\r\n\t' + '繁體 μ🙂 <b>原文</b>\n' * 300 + '  結尾\t'
                for task, attempt, output in [('task-a', 1, '先前嘗試'), ('task-b', 2, '另一個任務'), ('task-a', 2, literal)]:
                    token = journal.begin(task, 4, attempt, 'READ_TEXT_FILE', '讀回全文', {'path': '原文.txt'})
                    journal.finish(token, {'ok': True, 'verified': True, 'output': output, 'error': None, 'evidence': {'path': '原文.txt'}})
                result = completed_progress(directory, self.event())
                self.assertFalse(result['evidence_summary'])
                self.assertEqual(display_detail(result), literal)
                self.assertEqual(result['args'], {'path': '原文.txt'})
                self.assertEqual(result['evidence'], {'path': '原文.txt'})
                mismatch = completed_progress(directory, self.event(tool='WRITE_TEXT_FILE'))
                self.assertTrue(mismatch['evidence_summary'])
                self.assertEqual(mismatch['output'], '截短摘要…')
            finally:
                journal.close()

    def test_unfinished_ambiguous_or_missing_receipts_never_become_full_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(completed_progress(directory, self.event())['evidence_summary'])
            self.assertFalse((Path(directory) / 'workspace_state').exists())
            journal = TaskJournal(Path(directory) / 'workspace_state/execution.sqlite3')
            try:
                first = journal.begin('task-a', 4, 2, 'READ_TEXT_FILE', '讀取', {})
                self.assertTrue(completed_progress(directory, self.event())['evidence_summary'])
                journal.finish(first, {'ok': True, 'output': '第一次記錄'})
                second = journal.begin('task-a', 4, 2, 'READ_TEXT_FILE', '讀取', {})
                journal.finish(second, {'ok': True, 'output': '重複識別的記錄'})
                self.assertTrue(completed_progress(directory, self.event())['evidence_summary'])
            finally:
                journal.close()

    def test_unreadable_receipt_does_not_raise_into_the_successful_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workspace_state/execution.sqlite3'
            path.parent.mkdir()
            path.write_bytes(b'not a database')
            result = completed_progress(directory, self.event())
            self.assertTrue(result['ok'])
            self.assertTrue(result['evidence_summary'])
            self.assertEqual(path.read_bytes(), b'not a database')

    def test_zero_false_and_empty_collections_are_not_erased(self):
        for value, text in [(0, '0'), (False, 'false'), ([], '[]'), ({}, '{}'), ('  \r\n\t', '  \r\n\t')]:
            self.assertEqual(display_detail({'output': value, 'error': None}), text)
        self.assertEqual(display_detail({'error': '實際錯誤', 'output': '  部分內容\r\n'}), '錯誤：實際錯誤\n\n工具輸出：\n  部分內容\r\n')


if __name__ == '__main__':
    unittest.main()
