import tempfile,unittest
from pathlib import Path
from task_journal import TaskJournal

class DurableReceipts(unittest.TestCase):
    def test_inflight_action_survives_restart_without_replay_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'journal.sqlite3';journal=TaskJournal(path)
            journal.begin('request',1,1,'APPEND_TEXT_FILE','追加',{'path':'原稿.txt','text':'  原文\n'})
            journal.close();journal=TaskJournal(path)
            try:
                row=journal.read('request')[0]
                self.assertFalse(row['outcome_recorded']);self.assertFalse(row['replay_authorized'])
                self.assertEqual(row['arguments']['text'],'  原文\n')
            finally:journal.close()

    def test_full_structured_evidence_survives_without_log_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=TaskJournal(Path(tmp)/'journal.sqlite3')
            try:
                token=journal.begin('request',3,1,'READ_TEXT_FILE','讀回',{'path':'原稿.txt'})
                output={'ok':True,'verified':True,'output':'字'*10000+'\n\t','error':None}
                journal.finish(token,output)
                self.assertEqual(journal.read('request')[0]['result'],output)
                with self.assertRaises(ValueError):journal.finish(token,{'ok':False})
            finally:journal.close()
