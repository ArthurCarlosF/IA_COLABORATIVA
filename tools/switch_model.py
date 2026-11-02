"""Switch through the actual control API and optionally verify distributed generation."""
import argparse
import json
from pathlib import Path
import time
import httpx

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='runtime/network/config.json');parser.add_argument('--profile',required=True);parser.add_argument('--ca');parser.add_argument('--timeout',type=int,default=1900);parser.add_argument('--prompt');parser.add_argument('--tokens',type=int,default=16);parser.add_argument('--report',default='runtime/model-switch-report.json');args=parser.parse_args()
    cfg=json.loads(Path(args.config).read_text(encoding='utf8'));url=cfg['coordinator'];headers={'Authorization':'Bearer '+cfg['user_token']};report=dict(profile=args.profile,real_inference=True,status='started');output=Path(args.report);output.parent.mkdir(parents=True,exist_ok=True)
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    with httpx.Client(timeout=120,verify=args.ca or True,trust_env=False) as client:
        before=client.get(url+'/api/status',headers=headers);before.raise_for_status();report['before']=before.json()
        response=client.post(url+'/api/models/switch',headers=headers,json={'profile':args.profile});response.raise_for_status();save()
        deadline=time.monotonic()+args.timeout;previous=None
        while time.monotonic()<deadline:
            response=client.get(url+'/api/models/job',headers=headers);response.raise_for_status();job=response.json();report['job']=job;save()
            marker=(job['state'],tuple((k,v.get('bytes_downloaded',0)) for k,v in job.get('workers',{}).items()))
            if marker!=previous:print(marker,flush=True);previous=marker
            if job['state'] in ('completed','failed','recovery_required'):break
            time.sleep(1)
        else:raise RuntimeError('Client wait timed out; inspect /api/models/job; switch was not cancelled')
        if job['state']!='completed':report['status']='failed';save();raise RuntimeError(job.get('error',job['state']))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            status=client.get(url+'/api/status',headers=headers).json()
            if sum(n['online'] for n in status['nodes'])==status['required_parts']:break
            time.sleep(1)
        else:raise RuntimeError('Workers did not re-register')
        if args.prompt:
            response=client.post(url+'/api/chat',headers=headers,json={'model':status['model'],'prompt':args.prompt,'max_tokens':args.tokens});response.raise_for_status();events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')];report['events']=events
            if any(e['type']=='error' for e in events) or not any(e['type']=='done' for e in events):raise RuntimeError('Generation did not finish')
            print(next((e['text'] for e in reversed(events) if e['type']=='token'),'(EOS)'),flush=True)
        report['after']=client.get(url+'/api/status',headers=headers).json();report['audit_valid']=client.get(url+'/api/credits',headers=headers).json()['valid'];assert report['audit_valid'];assert not report['after']['busy'];report['status']='passed';save();print('Switch verified:',status['model'],flush=True)

if __name__=='__main__':main()
