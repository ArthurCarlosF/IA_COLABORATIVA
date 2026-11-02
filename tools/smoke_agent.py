"""Real distributed agent smoke; no canned model answers or substitute file writes."""
import argparse
import ast
import json
from pathlib import Path
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',default='runtime/network');parser.add_argument('--timeout',type=int,default=420);args=parser.parse_args()
    directory=ROOT/args.directory;c=json.loads((directory/'config.json').read_text(encoding='utf8'))
    h={'Authorization':'Bearer '+c['user_token']};url=c['coordinator'];target='greeting_'+str(int(time.time()))+'.py'
    report={'target':target,'real_inference':True,'cloud_api':False,'status':'started'}
    output=directory/'agent-smoke-evidence.json'
    def save():output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    with httpx.Client(timeout=30,trust_env=False) as client:
        before=client.get(url+'/api/status',headers=h);before.raise_for_status();report['before']=before.json()
        catalog=client.get(url+'/api/models',headers=h);catalog.raise_for_status();model=catalog.json()['active']
        response=client.post(url+'/api/agent/runs',headers=h,json={'model':model,'task':'Create '+target+' containing exactly: print("Hello cooperative network"). Use write_file, then check_file on '+target+', then finish. Do not run commands.'});response.raise_for_status();run=response.json()['id'];report['run_id']=run;save();print('Agent started',run,flush=True)
        deadline=time.monotonic()+args.timeout;last=None
        while time.monotonic()<deadline:
            response=client.get(url+'/api/agent/runs/'+run,headers=h);response.raise_for_status();state=response.json();report['state']=state;save()
            marker=(state['run']['status'],state['run']['steps'],len(state['events']))
            if marker!=last:print('Progress',marker,flush=True);last=marker
            if state['run']['status'] not in ('queued','running','waiting_approval'):break
            time.sleep(1)
        else:
            client.post(url+'/api/agent/runs/'+run+'/cancel',headers=h,json={}).raise_for_status();report['status']='timeout_cancelled';save();raise RuntimeError('Timed out; cancellation requested; evidence saved')
        if state['run']['status']!='completed':
            report['status']='failed';save();raise RuntimeError('Agent did not complete: '+state['run']['status'])
        file=client.get(url+'/api/workspace/file',headers=h,params={'path':target});file.raise_for_status();report['file']=file.json()
        tree=ast.parse(report['file']['content']);assert len(tree.body)==1 and isinstance(tree.body[0],ast.Expr)
        call=tree.body[0].value;assert isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='print' and len(call.args)==1 and isinstance(call.args[0],ast.Constant) and call.args[0].value=='Hello cooperative network'
        checks=[e for e in state['events'] if e['kind']=='tool_result' and e['payload']['tool']=='check_file'];automatic=[e for e in state['events'] if e['kind']=='tool_result' and e['payload']['tool']=='write_file'];assert any(e['payload']['result']['ok'] for e in checks) or any(e['payload']['result'].get('verification',{}).get('ok') for e in automatic)
        report['cross_account_status']=client.get(url+'/api/agent/runs/'+run,headers={'Authorization':'Bearer '+c['accounts']['peer-user']}).status_code;assert report['cross_account_status']==404
        report['unknown_model_status']=client.post(url+'/api/chat',headers=h,json={'prompt':'hello','max_tokens':1,'model':'not-installed'}).status_code;assert report['unknown_model_status']==409
        report['after']=client.get(url+'/api/status',headers=h).json();report['audit']=client.get(url+'/api/credits',headers=h).json()['valid'];assert report['audit'];assert not report['after']['busy'];assert report['after']['usage']['daily_reserved']+report['after']['usage']['extra_reserved']==0
        assert report['after']['metrics']['tokens']>report['before']['metrics']['tokens']
        report['status']='passed';save();print('Real distributed agent smoke PASSED; file saved and syntax checked, not executed.',flush=True)

if __name__=='__main__':main()
