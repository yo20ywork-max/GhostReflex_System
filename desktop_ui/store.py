"""Local task journal. Interrupted work is never automatically replayed."""
import json,sqlite3,threading,uuid
from datetime import datetime,timezone
from pathlib import Path

class TaskStore:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.journal_path=path.parent/'execution.sqlite3'
        self.lock=threading.RLock();self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,prompt TEXT NOT NULL,status TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,history TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS task_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,event TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.db.execute("UPDATE tasks SET status='interrupted',result='上次執行已中斷。請先確認應用程式的目前狀態，再決定後續操作。' WHERE status IN ('queued','running','cancelling')")
        self.db.commit()
    def add(self,prompt):
        task_id=uuid.uuid4().hex;now=datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',(task_id,prompt,'queued','',now,now,'[]'));self.db.commit()
        return task_id
    def update(self,task_id,status,result='',history=None):
        if status not in {'queued','running','cancelling','completed','partial','failed','blocked','cancelled','interrupted'}:raise ValueError('Unknown task status')
        with self.lock:
            if history is None:self.db.execute('UPDATE tasks SET status=?,result=?,updated_at=? WHERE id=?',(status,result,datetime.now(timezone.utc).isoformat(),task_id))
            else:self.db.execute('UPDATE tasks SET status=?,result=?,history=?,updated_at=? WHERE id=?',(status,result,json.dumps(history,ensure_ascii=False),datetime.now(timezone.utc).isoformat(),task_id))
            self.db.commit()
    def list(self):
        with self.lock:
            rows=self.db.execute('SELECT id,prompt,status,result,created_at FROM tasks ORDER BY created_at DESC LIMIT 200').fetchall()
        return [dict(zip(['id','prompt','status','result','created_at'],r)) for r in rows]
    def add_event(self,task_id,event):
        with self.lock:
            self.db.execute('INSERT INTO task_events(task_id,event) VALUES(?,?)',(task_id,json.dumps(event,ensure_ascii=False)));self.db.commit()
    def history(self,task_id):
        with self.lock:
            row=self.db.execute('SELECT history FROM tasks WHERE id=?',(task_id,)).fetchone()
            if row and json.loads(row[0]):return json.loads(row[0])
            if self.journal_path.is_file():
                connection=sqlite3.connect(self.journal_path.resolve().as_uri()+'?mode=ro',uri=True)
                try:attempts=connection.execute('SELECT step_id,attempt,tool,goal,arguments,result FROM attempts WHERE request_id=? ORDER BY rowid',(task_id,)).fetchall()
                finally:connection.close()
                if attempts:
                    return [{'step_id':step,'attempt':attempt,'tool':tool,'goal':goal,'args':json.loads(arguments),'outcome_recorded':result is not None,**(json.loads(result) if result is not None else {'ok':False,'verified':False,'output':None,'error':'操作已派發，但結果未記錄；需重新核對，不能自動重做。'})} for step,attempt,tool,goal,arguments,result in attempts]
            return [json.loads(r[0]) for r in self.db.execute('SELECT event FROM task_events WHERE task_id=? ORDER BY seq',(task_id,)).fetchall()]
    def close(self):
        with self.lock:self.db.close()
    def preference(self,key,default=None):
        with self.lock:row=self.db.execute('SELECT value FROM preferences WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def set_preference(self,key,value):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)));self.db.commit()
