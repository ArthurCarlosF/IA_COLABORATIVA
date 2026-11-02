import hashlib
import json
import sqlite3
import threading
import time

class Ledger:
    def __init__(self,path):
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.lock=threading.RLock()
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.execute('CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY, event TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL, receipt TEXT UNIQUE NOT NULL)')
        self.db.commit()

    def append(self,receipt,user,worker,units,seconds):
        event=json.dumps(dict(receipt=receipt,user=user,worker=worker,units=units,seconds=seconds,time=time.time(),debit=-units,credit=units),sort_keys=True,separators=(',',':'))
        with self.lock, self.db:
            previous=self.db.execute('SELECT hash FROM entries ORDER BY seq DESC LIMIT 1').fetchone()
            previous=previous[0] if previous else '0'*64
            digest=hashlib.sha256((previous+event).encode()).hexdigest()
            self.db.execute('INSERT OR IGNORE INTO entries(event,previous,hash,receipt) VALUES (?,?,?,?)',(event,previous,digest,receipt))

    def export(self):
        with self.lock:
            rows=self.db.execute('SELECT seq,event,previous,hash FROM entries ORDER BY seq').fetchall()
        return [dict(seq=r[0],event=json.loads(r[1]),previous=r[2],hash=r[3]) for r in rows]

    def verify(self):
        previous='0'*64
        with self.lock:
            rows=self.db.execute('SELECT event,previous,hash FROM entries ORDER BY seq').fetchall()
        for event,prev,digest in rows:
            if prev!=previous or hashlib.sha256((prev+event).encode()).hexdigest()!=digest:
                return False
            previous=digest
        return True
