"""Quota diária e reciprocidade para um coordenador e identidades autorizadas.

Inteiros em milionésimos de token; nenhuma moeda, venda ou consenso P2P.
"""
from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

SCALE=1_000_000

class InsufficientCredits(ValueError):
    pass

class Wallet:
    def __init__(self,ledger,daily_tokens=20000,zone='America/Sao_Paulo',now=None):
        if type(daily_tokens) is not int or not 0<=daily_tokens<=10_000_000:
            raise ValueError('Franquia diária inválida')
        self.ledger=ledger
        self.db=ledger.db
        self.lock=ledger.lock
        self.daily=daily_tokens*SCALE
        self.zone=ZoneInfo(zone)
        self.now=now or (lambda:datetime.now(timezone.utc))
        with self.lock,self.db:
            self.db.executescript("""
CREATE TABLE IF NOT EXISTS credit_accounts (
 id TEXT PRIMARY KEY, extra INTEGER NOT NULL DEFAULT 0 CHECK(extra>=0),
 earned INTEGER NOT NULL DEFAULT 0, spent INTEGER NOT NULL DEFAULT 0,
 processed INTEGER NOT NULL DEFAULT 0, layer_tokens INTEGER NOT NULL DEFAULT 0,
 last_day TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS credit_days (
 account TEXT NOT NULL, day TEXT NOT NULL, allowance INTEGER NOT NULL,
 spent INTEGER NOT NULL DEFAULT 0, reserved INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(account,day), CHECK(spent>=0 AND reserved>=0 AND spent+reserved<=allowance));
CREATE TABLE IF NOT EXISTS credit_reservations (
 id TEXT PRIMARY KEY, account TEXT NOT NULL, day TEXT NOT NULL,
 daily_left INTEGER NOT NULL, extra_left INTEGER NOT NULL, max_output INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', CHECK(daily_left>=0 AND extra_left>=0));
CREATE TABLE IF NOT EXISTS credit_events (
 seq INTEGER PRIMARY KEY, receipt TEXT UNIQUE NOT NULL, event TEXT NOT NULL,
 previous TEXT NOT NULL, hash TEXT NOT NULL);
""")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def _event(self,receipt,kind,**data):
        event=json.dumps(dict(type=kind,recorded_at=self.now().isoformat(),**data),sort_keys=True,separators=(',',':'),allow_nan=False)
        row=self.db.execute('SELECT hash FROM credit_events ORDER BY seq DESC LIMIT 1').fetchone()
        previous=row[0] if row else '0'*64
        digest=hashlib.sha256((previous+event).encode()).hexdigest()
        self.db.execute('INSERT INTO credit_events(receipt,event,previous,hash) VALUES (?,?,?,?)',(receipt,event,previous,digest))

    def _account(self,user):
        if not isinstance(user,str) or not 1<=len(user)<=100:
            raise ValueError('Identidade inválida')
        self.db.execute('INSERT OR IGNORE INTO credit_accounts(id) VALUES (?)',(user,))

    def _day(self,user):
        self._account(user)
        stamp=self.now()
        if stamp.tzinfo is None:raise ValueError('Relógio deve incluir fuso')
        observed=stamp.astimezone(self.zone).date().isoformat()
        last=self.db.execute('SELECT last_day FROM credit_accounts WHERE id=?',(user,)).fetchone()[0]
        # Recuo do relógio nunca reabre franquias antigas.
        day=max(last,observed)
        row=self.db.execute('SELECT allowance FROM credit_days WHERE account=? AND day=?',(user,day)).fetchone()
        if row is None:
            self.db.execute('INSERT INTO credit_days(account,day,allowance) VALUES (?,?,?)',(user,day,self.daily))
            self._event('grant:'+user+':'+day,'daily_grant',account=user,day=day,amount=self.daily)
        self.db.execute('UPDATE credit_accounts SET last_day=? WHERE id=?',(day,user))
        return day

    def _snapshot(self,user,day):
        allowance,spent,reserved=self.db.execute('SELECT allowance,spent,reserved FROM credit_days WHERE account=? AND day=?',(user,day)).fetchone()
        extra,earned,total_spent,processed,layers=self.db.execute('SELECT extra,earned,spent,processed,layer_tokens FROM credit_accounts WHERE id=?',(user,)).fetchone()
        reserved_extra=self.db.execute("SELECT COALESCE(SUM(extra_left),0) FROM credit_reservations WHERE account=? AND status='open'",(user,)).fetchone()[0]
        reset=(datetime.fromisoformat(day).replace(tzinfo=self.zone)+timedelta(days=1)).isoformat()
        revision=self.db.execute('SELECT COALESCE(MAX(seq),0) FROM credit_events').fetchone()[0]
        return dict(account=user,day=day,timezone=self.zone.key,resets_at=reset,revision=revision,
                    daily_allowance=allowance/SCALE,daily_spent=spent/SCALE,daily_reserved=reserved/SCALE,
                    daily_remaining=(allowance-spent)/SCALE,daily_available=(allowance-spent-reserved)/SCALE,
                    extra_remaining=(extra+reserved_extra)/SCALE,extra_available=extra/SCALE,extra_reserved=reserved_extra/SCALE,
                    total_remaining=(allowance-spent+extra+reserved_extra)/SCALE,total_available=(allowance-spent-reserved+extra)/SCALE,
                    earned_total=earned/SCALE,spent_total=total_spent/SCALE,
                    contributed_tokens=earned/SCALE,partition_tokens_processed=processed,contributed_layer_tokens=layers,
                    unit='token-equivalent',payments=False)

    def snapshot(self,user):
        with self.transaction():
            return self._snapshot(user,self._day(user))

    def reserve(self,sid,user,input_tokens,max_output):
        if type(input_tokens) is not int or input_tokens<1 or type(max_output) is not int or max_output<1:
            raise ValueError('Orçamento inválido')
        with self.transaction():
            if self.db.execute('SELECT 1 FROM credit_reservations WHERE id=?',(sid,)).fetchone():
                raise ValueError('Reserva já existe')
            day=self._day(user)
            allowance,spent,reserved=self.db.execute('SELECT allowance,spent,reserved FROM credit_days WHERE account=? AND day=?',(user,day)).fetchone()
            daily=allowance-spent-reserved
            extra=self.db.execute('SELECT extra FROM credit_accounts WHERE id=?',(user,)).fetchone()[0]
            output=min(max_output,(daily+extra)//SCALE-input_tokens)
            if output<1:raise InsufficientCredits('Saldo insuficiente para a entrada e um token de saída')
            amount=(input_tokens+output)*SCALE
            from_daily=min(daily,amount)
            from_extra=amount-from_daily
            self.db.execute('UPDATE credit_days SET reserved=reserved+? WHERE account=? AND day=?',(from_daily,user,day))
            self.db.execute('UPDATE credit_accounts SET extra=extra-? WHERE id=?',(from_extra,user))
            self.db.execute('INSERT INTO credit_reservations(id,account,day,daily_left,extra_left,max_output) VALUES (?,?,?,?,?,?)',(sid,user,day,from_daily,from_extra,output))
            self._event('reserve:'+sid,'reserve',account=user,session=sid,day=day,daily=from_daily,extra=from_extra,max_output=output)
            return int(output)

    def settle(self,sid,iteration,cost_tokens,workers):
        """Workers report layers or explicit graph work units; only complete steps."""
        if type(cost_tokens) is not int or cost_tokens<1 or type(iteration) is not int or iteration<0:
            raise ValueError('Liquidação inválida')
        if not workers or len({w['id'] for w in workers})!=len(workers):raise ValueError('Workers inválidos')
        if any(type(w['layers']) is not int or w['layers']<1 or type(w['input_tokens']) is not int or w['input_tokens']<1 for w in workers):
            raise ValueError('Contribuição inválida')
        if any('work_units' in w and (type(w['work_units']) is not int or w['work_units']<1)
               for w in workers):
            raise ValueError('Unidades de operação inválidas')
        receipt=f'settle:{sid}:{iteration}'
        amount=cost_tokens*SCALE
        total_layers=sum(w.get('work_units',w['layers']) for w in workers)
        with self.transaction():
            row=self.db.execute('SELECT account,day,daily_left,extra_left,status FROM credit_reservations WHERE id=?',(sid,)).fetchone()
            if row is None:raise ValueError('Reserva desconhecida')
            user,day,daily_left,extra_left,status=row
            identity=dict(account=user,session=sid,iteration=iteration,amount=amount,workers=workers)
            existing=self.db.execute('SELECT event FROM credit_events WHERE receipt=?',(receipt,)).fetchone()
            if existing:
                old=json.loads(existing[0])
                if any(old.get(k)!=v for k,v in identity.items()):raise ValueError('Repetição conflitante')
                return False
            if status!='open' or amount>daily_left+extra_left:raise ValueError('Reserva insuficiente ou encerrada')
            spent_daily=min(daily_left,amount)
            spent_extra=amount-spent_daily
            self.db.execute('UPDATE credit_reservations SET daily_left=daily_left-?,extra_left=extra_left-? WHERE id=?',(spent_daily,spent_extra,sid))
            self.db.execute('UPDATE credit_days SET reserved=reserved-?,spent=spent+? WHERE account=? AND day=?',(spent_daily,spent_daily,user,day))
            self.db.execute('UPDATE credit_accounts SET spent=spent+? WHERE id=?',(amount,user))
            distributed=0
            rewards=[]
            for index,worker in enumerate(workers):
                share=amount-distributed if index==len(workers)-1 else amount*worker.get('work_units',worker['layers'])//total_layers
                distributed+=share
                owner=worker['owner']
                self._account(owner)
                reward=share if owner!=user else 0
                # Só trabalho para outras pessoas aparece como contribuição remunerada.
                if owner!=user:
                    self.db.execute('UPDATE credit_accounts SET extra=extra+?,earned=earned+?,processed=processed+?,layer_tokens=layer_tokens+? WHERE id=?',
                                    (reward,reward,worker['input_tokens'],worker.get('work_units',worker['input_tokens']*worker['layers']),owner))
                rewards.append(dict(worker=worker['id'],owner=owner,amount=reward,self_work=owner==user))
            assert sum(r['amount'] for r in rewards)<=amount
            self._event(receipt,'settlement',**identity,daily_spent=spent_daily,extra_spent=spent_extra,rewards=rewards)
            return True

    def _release(self,sid,recovered=False):
        row=self.db.execute('SELECT account,day,daily_left,extra_left,status FROM credit_reservations WHERE id=?',(sid,)).fetchone()
        if not row or row[4]!='open':return False
        user,day,daily,extra,_=row
        self.db.execute('UPDATE credit_days SET reserved=reserved-? WHERE account=? AND day=?',(daily,user,day))
        self.db.execute('UPDATE credit_accounts SET extra=extra+? WHERE id=?',(extra,user))
        self.db.execute("UPDATE credit_reservations SET daily_left=0,extra_left=0,status='closed' WHERE id=?",(sid,))
        self._event('release:'+sid,'recovery' if recovered else 'release',account=user,session=sid,daily_refund=daily,extra_refund=extra)
        return True

    def release(self,sid):
        with self.transaction():return self._release(sid)

    def recover(self):
        """Somente no início do coordenador exclusivo deste banco."""
        with self.transaction():
            ids=[r[0] for r in self.db.execute("SELECT id FROM credit_reservations WHERE status='open'")]
            for sid in ids:self._release(sid,recovered=True)
            return len(ids)

    def _projection_valid(self,events):
        accounts=defaultdict(lambda:[0,0,0,0,0])
        days={}
        reservations={}
        for e in events:
            kind=e['type']
            if kind=='daily_grant':
                accounts[e['account']]
                days[e['account'],e['day']]=[e['amount'],0,0]
            elif kind=='reserve':
                accounts[e['account']][0]-=e['extra']
                days[e['account'],e['day']][2]+=e['daily']
                reservations[e['session']]=[e['account'],e['day'],e['daily'],e['extra'],e['max_output'],'open']
            elif kind=='settlement':
                r=reservations[e['session']]
                r[2]-=e['daily_spent']
                r[3]-=e['extra_spent']
                days[r[0],r[1]][1]+=e['daily_spent']
                days[r[0],r[1]][2]-=e['daily_spent']
                accounts[e['account']][2]+=e['amount']
                for w,reward in zip(e['workers'],e['rewards']):
                    account=accounts[w['owner']]
                    if w['owner']!=e['account']:
                        account[0]+=reward['amount']
                        account[1]+=reward['amount']
                        account[3]+=w['input_tokens']
                        account[4]+=w.get('work_units',w['input_tokens']*w['layers'])
            elif kind in ('release','recovery'):
                r=reservations[e['session']]
                days[r[0],r[1]][2]-=e['daily_refund']
                accounts[e['account']][0]+=e['extra_refund']
                r[2:4]=[0,0]
                r[5]='closed'
            else:return False
        actual={r[0]:list(r[1:]) for r in self.db.execute('SELECT id,extra,earned,spent,processed,layer_tokens FROM credit_accounts')}
        actual_days={(r[0],r[1]):list(r[2:]) for r in self.db.execute('SELECT account,day,allowance,spent,reserved FROM credit_days')}
        actual_reservations={r[0]:list(r[1:]) for r in self.db.execute('SELECT id,account,day,daily_left,extra_left,max_output,status FROM credit_reservations')}
        return dict(accounts)==actual and days==actual_days and reservations==actual_reservations

    def audit(self,user=None):
        with self.lock:
            rows=self.db.execute('SELECT seq,event,previous,hash FROM credit_events ORDER BY seq').fetchall()
            previous='0'*64
            valid=True
            events=[]
            all_events=[]
            for seq,text,prev,digest in rows:
                if prev!=previous or hashlib.sha256((prev+text).encode()).hexdigest()!=digest:valid=False
                previous=digest
                try:event=json.loads(text)
                except (ValueError,TypeError):
                    valid=False
                    continue
                all_events.append(event)
                if user is None or event.get('account')==user:
                    events.append(dict(seq=seq,event=event,previous=prev,hash=digest))
                elif event.get('type')=='settlement':
                    owned=[r for r in event['rewards'] if r['owner']==user]
                    if owned:events.append(dict(seq=seq,event=dict(type='contribution',account=user,rewards=owned)))
            try:valid=valid and self._projection_valid(all_events)
            except (KeyError,TypeError,ValueError,IndexError):valid=False
            return dict(valid=valid,entries=events,head=previous,scope='own-account' if user else 'all')
