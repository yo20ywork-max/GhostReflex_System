import tempfile,unittest
from pathlib import Path
from desktop_ui.store import TaskStore

class TaskPersistence(unittest.TestCase):
    def test_interrupted_ui_task_can_find_its_unresolved_action_receipt(self):
        from task_journal import TaskJournal
        with tempfile.TemporaryDirectory() as tmp:
            store=TaskStore(Path(tmp)/'tasks.sqlite3');task=store.add('追加一次')
            journal=TaskJournal(Path(tmp)/'execution.sqlite3')
            try:
                journal.begin(task,1,1,'APPEND_TEXT_FILE','追加',{'content':'一次'})
                row=store.history(task)[0]
                self.assertEqual(row['tool'],'APPEND_TEXT_FILE');self.assertFalse(row['outcome_recorded'])
                self.assertIn('不能自動重做',row['error'])
            finally:journal.close();store.close()
    def test_each_observed_step_survives_before_task_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tasks.sqlite3';store=TaskStore(path);task=store.add('等待結果');store.update(task,'running')
            event={'step_id':1,'tool':'BROWSER_WAIT_FOR','ok':True,'output':'元素已消失','evidence_summary':True};store.add_event(task,event);store.close()
            reopened=TaskStore(path)
            try:self.assertEqual(reopened.history(task),[event]);self.assertEqual(reopened.list()[0]['status'],'interrupted')
            finally:reopened.close()
    def test_restart_marks_inflight_interrupted_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tasks.sqlite3';store=TaskStore(path)
            raw='  工作\n\t原文  ';task=store.add(raw);store.update(task,'running','仍在處理',[{'step_id':1,'ok':True,'output':'已讀取'}]);store.close()
            reopened=TaskStore(path)
            try:
                row=reopened.list()[0];self.assertEqual(row['prompt'],raw);self.assertEqual(row['status'],'interrupted');self.assertNotEqual(row['status'],'completed')
                evidence=reopened.db.execute('SELECT history FROM tasks WHERE id=?',(task,)).fetchone()[0];self.assertIn('已讀取',evidence)
            finally:reopened.close()
    def test_finished_work_is_not_replayed_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tasks.sqlite3';store=TaskStore(path);task=store.add('讀取');store.update(task,'completed','實際結果');store.close()
            reopened=TaskStore(path)
            try:self.assertEqual(reopened.list()[0]['status'],'completed');self.assertEqual(reopened.list()[0]['result'],'實際結果')
            finally:reopened.close()
