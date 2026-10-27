"""Private per-application storage; never exposes raw storage paths."""
from __future__ import annotations
import json, os, sqlite3, threading, time, uuid, shutil
from pathlib import Path
from contextlib import contextmanager

ROOT=Path(os.environ.get('BAPETEN_DATA_DIR', str(Path(__file__).resolve().parents[1]/'runtime_data'))).resolve()
_LOCK=threading.RLock()

@contextmanager
def db():
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    con=sqlite3.connect(ROOT/'metadata.sqlite3',timeout=30)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY, created REAL, updated REAL)')
    con.execute('CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, app_id TEXT NOT NULL, category TEXT NOT NULL, subtype TEXT, filename TEXT NOT NULL, disk_filename TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, uploaded REAL NOT NULL, FOREIGN KEY(app_id) REFERENCES applications(id))')
    con.execute('CREATE INDEX IF NOT EXISTS ix_docs_app ON documents(app_id)')
    con.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, app_id TEXT NOT NULL, status TEXT, progress INTEGER, message TEXT, error TEXT, created REAL, updated REAL, result TEXT)')
    con.commit()
    try:
        yield con
        con.commit()
    finally:
        con.close()

def make_id(): return uuid.uuid4().hex

def row(con,sql,args=()):
    x=con.execute(sql,args).fetchone()
    return dict(x) if x else None

def rows(con,sql,args=()):return [dict(x) for x in con.execute(sql,args).fetchall()]

def create_application():
    aid=make_id(); now=time.time()
    with _LOCK,db() as con:con.execute('INSERT INTO applications VALUES(?,?,?)',(aid,now,now))
    (ROOT/'uploads'/aid).mkdir(parents=True,exist_ok=True,mode=0o700)
    return aid

def app_exists(aid):
    with db() as con:return bool(row(con,'SELECT id FROM applications WHERE id=?',(aid,)))

def documents(aid):
    with db() as con:return rows(con,'SELECT id,category,subtype,filename,size,sha256,uploaded FROM documents WHERE app_id=? ORDER BY uploaded,id',(aid,))

def document(did,aid):
    with db() as con:return row(con,'SELECT * FROM documents WHERE id=? AND app_id=?',(did,aid))

def add_document(aid,category,subtype,name,size,sha,disk_filename):
    did=make_id();now=time.time()
    with _LOCK,db() as con:
        con.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)',(did,aid,category,subtype,name,disk_filename,size,sha,now))
        con.execute('UPDATE applications SET updated=? WHERE id=?',(now,aid))
    return did

def delete_document(did,aid):
    d=document(did,aid)
    if not d:return False
    with _LOCK,db() as con:con.execute('DELETE FROM documents WHERE id=? AND app_id=?',(did,aid))
    (ROOT/'uploads'/aid/d['disk_filename']).unlink(missing_ok=True)
    # A deleted sensitive document must not remain in extraction cache.
    # A label cache can include evidence from several uploaded documents.
    # Evict the entire application's extraction cache on ANY deletion.
    shutil.rmtree(ROOT/'extraction_cache'/aid,ignore_errors=True)
    return True

def file_path(d):
    # Internal ephemeral conversion path; never accepted from user HTTP payload.
    if d.get('_analysis_path'):return Path(d['_analysis_path'])
    return ROOT/'uploads'/d['app_id']/d['disk_filename']

def create_job(aid):
    jid=make_id();now=time.time()
    with _LOCK,db() as con: con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(jid,aid,'queued',0,'Menunggu proses',None,now,now,None))
    return jid

def update_job(jid,**kwargs):
    allowed={'status','progress','message','error','result'}
    values={k:(json.dumps(v,ensure_ascii=False) if k=='result' else v) for k,v in kwargs.items() if k in allowed}
    values['updated']=time.time()
    with _LOCK,db() as con:
        con.execute('UPDATE jobs SET '+', '.join(f'{k}=?' for k in values)+' WHERE id=?',(*values.values(),jid))

def get_job(jid,aid=None):
    with db() as con:
        j=row(con,'SELECT * FROM jobs WHERE id=?'+(' AND app_id=?' if aid else ''),(jid,aid) if aid else (jid,))
    return j

def latest_result(aid):
    with db() as con:
        j=row(con,"SELECT * FROM jobs WHERE app_id=? AND status='completed' ORDER BY updated DESC LIMIT 1",(aid,))
    return json.loads(j['result']) if j and j.get('result') else None

def get_job_latest_running(aid):
    with db() as con:return row(con,"SELECT id,status FROM jobs WHERE app_id=? AND status IN ('queued','running') ORDER BY created DESC LIMIT 1",(aid,))
