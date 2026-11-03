from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import sqlite3
import pytest
from mesh.ledger import Ledger
from mesh.credits import Wallet,InsufficientCredits,SCALE

class Clock:
    def __init__(self):self.value=datetime(2026,11,2,2,59,59,tzinfo=timezone.utc)
    def __call__(self):return self.value

@pytest.fixture
def setup(tmp_path):
    clock=Clock()
    ledger=Ledger(tmp_path/'credits.db')
    wallet=Wallet(ledger,100,now=clock)
    return wallet,clock,ledger

def workers(owner='bob',layers=(1,1)):
    return [dict(id=f'w{i}',owner=owner,layers=layer,input_tokens=2) for i,layer in enumerate(layers)]

def test_midnight_timezone_no_accumulation_and_clock_rollback(setup):
    w,c,_=setup
    assert w.snapshot('alice')['day']=='2026-11-01'
    w.reserve('a','alice',2,8)
    w.settle('a',0,3,workers())
    w.release('a')
    assert w.snapshot('alice')['daily_remaining']==97
    c.value=datetime(2026,11,2,3,0,0,tzinfo=timezone.utc)
    assert w.snapshot('alice')['daily_remaining']==100
    assert w.snapshot('alice')['day']=='2026-11-02'
    assert w.snapshot('alice')['resets_at']=='2026-11-03T00:00:00-03:00'
    assert w.snapshot('alice')['extra_remaining']==0
    assert w.snapshot('bob')['extra_remaining']==3
    c.value=datetime(2026,11,1,3,0,0,tzinfo=timezone.utc)
    assert w.snapshot('alice')['day']=='2026-11-02'
    assert w.snapshot('alice')['daily_remaining']==100
    assert w.audit()['valid']

def test_layer_shares_conserve_and_no_self_reward(setup):
    w,_,_=setup
    w.reserve('a','alice',2,3)
    stages=[dict(id='self',owner='alice',layers=1,input_tokens=2),dict(id='external',owner='bob',layers=2,input_tokens=2)]
    w.settle('a',0,3,stages)
    w.release('a')
    assert w.snapshot('alice')['extra_remaining']==0
    assert w.snapshot('bob')['extra_remaining']==2
    assert w.snapshot('bob')['contributed_tokens']==2
    assert w.snapshot('bob')['partition_tokens_processed']==2
    assert w.audit()['valid']

def test_rounding_multiple_workers_same_owner(setup):
    w,_,_=setup
    w.reserve('s','a',1,2)
    w.settle('s',0,2,workers(layers=(1,1,1)))
    w.release('s')
    assert w.snapshot('bob')['extra_remaining']==2
    assert w.snapshot('bob')['contributed_tokens']==2
    assert w.snapshot('bob')['partition_tokens_processed']==6
    assert w.audit()['valid']

def test_graph_operations_credit_only_actual_units_without_multiplying_again(setup):
    wallet,_,_=setup
    wallet.reserve('graph','requester',5,1)
    wallet.settle('graph',0,6,[
        dict(id='a',owner='alice',layers=1,input_tokens=5,work_units=15),
        dict(id='b',owner='bob',layers=1,input_tokens=2,work_units=5)])
    wallet.release('graph')
    a,b=wallet.snapshot('alice'),wallet.snapshot('bob')
    assert a['extra_remaining']==4.5 and b['extra_remaining']==1.5
    assert a['partition_tokens_processed']==5 and b['partition_tokens_processed']==2
    assert a['contributed_layer_tokens']==15 and b['contributed_layer_tokens']==5
    assert wallet.audit()['valid']

def test_daily_then_extra_and_refund(setup):
    w,_,_=setup
    w.reserve('a','alice',1,4)
    w.settle('a',0,5,workers())
    w.release('a')
    assert w.snapshot('bob')['extra_remaining']==5
    w.reserve('b','bob',99,6)
    assert w.snapshot('bob')['daily_reserved']==100
    assert w.snapshot('bob')['extra_available']==0
    assert w.snapshot('bob')['extra_reserved']==5
    w.settle('b',0,101,workers('carol'))
    w.release('b')
    state=w.snapshot('bob')
    assert state['daily_remaining']==0 and state['extra_remaining']==4
    assert state['spent_total']==101 and state['earned_total']==5
    assert w.audit()['valid']

def test_insufficient_clipping_and_overdraft(setup):
    w,_,_=setup
    assert w.reserve('a','alice',90,20)==10
    with pytest.raises(InsufficientCredits):w.reserve('b','alice',1,1)
    with pytest.raises(ValueError):w.settle('a',0,101,workers())
    w.release('a')
    assert w.snapshot('alice')['total_remaining']==100
    with pytest.raises(InsufficientCredits):w.reserve('c','alice',100,1)
    assert w.audit()['valid']

def test_idempotent_and_conflicting_settlement(setup):
    w,_,_=setup
    w.reserve('a','alice',2,4)
    assert w.settle('a',0,3,workers())
    assert not w.settle('a',0,3,workers())
    with pytest.raises(ValueError):w.settle('a',0,4,workers())
    assert w.release('a') and not w.release('a')
    assert w.snapshot('bob')['extra_remaining']==3
    assert w.snapshot('alice')['daily_remaining']==97
    assert w.audit()['valid']

def test_restart_recovery_and_persistence(setup):
    w,c,ledger=setup
    w.reserve('a','alice',2,8)
    w.settle('a',0,3,workers())
    database=ledger.db.execute('PRAGMA database_list').fetchone()[2]
    restarted=Wallet(Ledger(database),100,now=c)
    assert restarted.recover()==1
    assert restarted.recover()==0
    assert restarted.snapshot('alice')['daily_reserved']==0
    assert restarted.snapshot('alice')['daily_remaining']==97
    assert restarted.snapshot('bob')['extra_remaining']==3
    assert restarted.audit()['valid']

def test_reservation_across_midnight(setup):
    w,c,_=setup
    w.reserve('a','alice',2,8)
    c.value=datetime(2026,11,2,3,0,0,tzinfo=timezone.utc)
    assert w.snapshot('alice')['daily_remaining']==100
    w.settle('a',0,3,workers())
    w.release('a')
    assert w.snapshot('alice')['daily_remaining']==100
    assert w.snapshot('bob')['extra_remaining']==3
    assert w.audit()['valid']

def test_concurrent_no_double_spend(setup):
    w,_,_=setup
    def reserve(i):
        try:w.reserve(str(i),'alice',59,1);return True
        except InsufficientCredits:return False
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(8)))
    assert sum(results)==1
    assert w.snapshot('alice')['daily_reserved']==60
    w.recover()
    assert w.snapshot('alice')['total_remaining']==100
    assert w.audit()['valid']

def test_tampered_balance_and_events_detected(setup):
    w,_,ledger=setup
    w.snapshot('alice')
    assert w.audit()['valid']
    ledger.db.execute("UPDATE credit_accounts SET extra=100 WHERE id='alice'")
    ledger.db.commit()
    assert not w.audit()['valid']
    ledger.db.execute("UPDATE credit_accounts SET extra=0 WHERE id='alice'")
    ledger.db.commit()
    assert w.audit()['valid']
    ledger.db.execute("UPDATE credit_events SET event='{}' WHERE seq=1")
    ledger.db.commit()
    assert not w.audit()['valid']

def test_private_history_and_legacy_not_converted(setup):
    w,_,ledger=setup
    ledger.append('old','alice','worker',1000000,.1)
    assert w.snapshot('alice')['extra_remaining']==0
    w.reserve('a','alice',2,4)
    w.settle('a',0,3,workers())
    w.release('a')
    private=w.audit('bob')
    assert all(e['event']['account']=='bob' for e in private['entries'])
    assert private['valid']

def test_zero_quota_and_policy_same_day_no_remint(setup):
    w,c,ledger=setup
    w.snapshot('alice')
    changed=Wallet(ledger,1000,now=c)
    assert changed.snapshot('alice')['daily_remaining']==100
    zero=Wallet(ledger,0,now=c)
    assert zero.snapshot('new')['daily_remaining']==0
    with pytest.raises(InsufficientCredits):zero.reserve('no','new',1,1)
    assert zero.audit()['valid']


def test_usage_revisions_and_visible_remaining_during_reservation(setup):
    w,_,_=setup
    before=w.snapshot('alice')
    w.reserve('s','alice',2,8)
    reserved=w.snapshot('alice')
    assert reserved['daily_remaining']==100 and reserved['daily_available']==90
    assert reserved['revision']>before['revision']
    w.settle('s',0,3,workers())
    settled=w.snapshot('alice')
    assert settled['daily_remaining']==97 and settled['daily_available']==90
    assert settled['revision']>reserved['revision']
    w.release('s')
    released=w.snapshot('alice')
    assert released['daily_remaining']==97 and released['daily_available']==97
    assert released['revision']>settled['revision']
    assert w.audit()['valid']
