"""Durable action receipts. An interrupted attempt is never replay authorization."""
import datetime,json,sqlite3,threading,uuid
from pathlib import Path

class TaskJournal:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.Lock();self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, request_id TEXT NOT NULL, step_id INTEGER NOT NULL, attempt INTEGER NOT NULL, tool TEXT NOT NULL, goal TEXT NOT NULL, arguments TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, result TEXT)')
        self.db.commit()

    def begin(self,request_id,step_id,attempt,tool,goal,arguments):
        token=uuid.uuid4().hex
        with self._lock,self.db:
            self.db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,NULL,NULL)',(token,request_id,step_id,attempt,tool,goal,json.dumps(arguments,ensure_ascii=False),datetime.datetime.now(datetime.timezone.utc).isoformat()))
        return token

    def finish(self,token,result):
        encoded=json.dumps(result,ensure_ascii=False,default=str)
        with self._lock,self.db:
            row=self.db.execute('UPDATE attempts SET finished_at=?, result=? WHERE id=? AND result IS NULL',(datetime.datetime.now(datetime.timezone.utc).isoformat(),encoded,token))
            if row.rowcount!=1:raise ValueError('Unknown or already finalized action receipt')

    def read(self,request_id):
        with self._lock:
            cursor=self.db.execute('SELECT id,step_id,attempt,tool,goal,arguments,started_at,finished_at,result FROM attempts WHERE request_id=? ORDER BY rowid',(request_id,))
            names=[x[0] for x in cursor.description];rows=[dict(zip(names,row)) for row in cursor.fetchall()]
        for row in rows:
            row['arguments']=json.loads(row['arguments']);row['result']=json.loads(row['result']) if row['result'] is not None else None
            row['outcome_recorded']=row['result'] is not None
            row['replay_authorized']=False
        return rows

    def close(self):
        with self._lock:self.db.close()
