import asyncio
import json
import sys
import threading
import pytest
from mesh.agent import AgentStore,AgentManager,parse_action,execute_command
from mesh.workspace import Workspace

def test_protocol_rejects_extra_and_bad_args():
    assert parse_action('```json\n{"tool":"list_files","args":{}}\n```')['tool']=='list_files'
    for text in ['hello','{"tool":"x","args":{}} trailing','{"tool":"x","args":[],"other":1}']:
        with pytest.raises(ValueError):parse_action(text)

def test_agent_files_correction_history_and_privacy(tmp_path):
    async def scenario():
        actions=iter([
            dict(tool='write_file',args=dict(path='add.py',content='def add(:')),
            dict(tool='check_file',args=dict(path='add.py')),
            dict(tool='finish',args=dict(summary='False success')),
            dict(tool='write_file',args=dict(path='add.py',content='def add(a,b):\n    return a+b\n')),
            dict(tool='check_file',args=dict(path='add.py')),
            dict(tool='finish',args=dict(summary='Created and syntax checked; not executed'))])
        async def infer(auth,prompt,max_tokens):return json.dumps(next(actions))
        store=AgentStore(tmp_path/'runs.db');workspace=Workspace(tmp_path/'files')
        manager=AgentManager(store,workspace,infer)
        run=manager.start('alice','Create add','Bearer private')
        await manager.tasks[run]
        assert store.get(run,'alice')['status']=='completed'
        assert workspace.check('alice','add.py')['ok']
        assert any(e['kind']=='tool_error' for e in store.events(run,'alice'))
        with pytest.raises(KeyError):store.get(run,'bob')
        assert 'Bearer private' not in json.dumps(store.events(run,'alice'))
        reopened=AgentStore(tmp_path/'runs.db');assert reopened.get(run,'alice')['status']=='completed'
    asyncio.run(scenario())

def test_approval_origin_single_use_and_changed_project(tmp_path):
    async def scenario():
        store=AgentStore(tmp_path/'runs.db');w=Workspace(tmp_path/'files')
        async def infer(*args):return ''
        m=AgentManager(store,w,infer,host_commands=True)
        run=store.create('local-user','test');m.cancels[run]=threading.Event()
        task=asyncio.create_task(m.tool(run,'local-user','run_command',dict(argv=[sys.executable,'-c','print(1)']),{},True,set(),set()))
        for _ in range(100):
            await asyncio.sleep(.001)
            events=store.events(run,'local-user')
            proposals=[e for e in events if e['kind']=='approval_requested']
            if proposals:break
        aid=proposals[0]['payload']['id']
        with pytest.raises(PermissionError):m.approve('local-user',run,aid,True,False)
        w.write('local-user','changed.py','x=1')
        m.approve('local-user',run,aid,True,True)
        with pytest.raises(ValueError):m.approve('local-user',run,aid,True,True)
        with pytest.raises(ValueError,match='Arquivos mudaram'):await task
        with pytest.raises(PermissionError):await m.tool(run,'bob','run_command',dict(argv=['python']),{},True,set(),set())
    asyncio.run(scenario())

def test_commands_really_run_bounded_and_timeout(tmp_path):
    result=execute_command([sys.executable,'-c','print(6*7)'],tmp_path,threading.Event())
    assert result['ok'] and result['output'].strip()=='42'
    result=execute_command([sys.executable,'-c','import time;time.sleep(10)'],tmp_path,threading.Event(),timeout=.15)
    assert not result['ok'] and result['timeout']

def test_interrupted_runs_expire_approval(tmp_path):
    store=AgentStore(tmp_path/'runs.db');run=store.create('alice','test');aid=store.proposal(run,{})
    store.update(run,'waiting_approval');reopened=AgentStore(tmp_path/'runs.db')
    assert reopened.get(run,'alice')['status']=='interrupted'
    with pytest.raises(ValueError):reopened.decide(run,'alice',aid,True)
