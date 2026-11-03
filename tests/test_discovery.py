import copy
import pytest
from mesh.discovery import new_identity,PeerDirectory,Gossip

def directories(tmp_path):
    a,b=new_identity(),new_identity()
    urls=['https://127.0.0.2:9101','https://127.0.0.3:9102']
    trusted={identity['peer_id']:dict(public_key=identity['public_key'],endpoints=[url]) for identity,url in zip([a,b],urls)}
    now=[1000.0]
    return [PeerDirectory(identity,url,trusted,{'role':'worker'},tmp_path/f'{i}.json',now=lambda:now[0]) for i,(identity,url) in enumerate(zip([a,b],urls))],now

def test_signed_contacts_replay_expiry_and_persistence(tmp_path):
    (a,b),now=directories(tmp_path)
    first=a.own_record()
    assert b.accept(first) and not b.accept(first)
    new=a.own_record();assert b.accept(new)
    with pytest.raises(ValueError):b.accept(first)
    tampered=copy.deepcopy(new);tampered['payload']['capability']['role']='admin'
    with pytest.raises(ValueError):b.accept(tampered)
    reloaded=PeerDirectory(b.identity,b.endpoint,b.trusted,b.capability,b.state_path,now=lambda:now[0])
    assert len(reloaded.snapshot())==1
    now[0]+=31
    assert not b.snapshot()
    with pytest.raises(ValueError):b.accept(new)

def test_unknown_identity_and_ssrf_seed_denied(tmp_path):
    (a,b),_=directories(tmp_path)
    outsider=new_identity()
    roster={outsider['peer_id']:dict(public_key=outsider['public_key'],endpoints=['https://example.invalid'])}
    c=PeerDirectory(outsider,'https://example.invalid',roster,{})
    with pytest.raises(ValueError):b.accept(c.own_record())
    with pytest.raises(ValueError):Gossip(a,['http://169.254.169.254'])
    record=a.own_record();record['payload']['endpoint']='http://169.254.169.254'
    with pytest.raises(ValueError):b.accept(record)

def test_large_authorized_roster_sends_bounded_exchange_batches():
    identities=[new_identity() for _ in range(72)]
    urls=[f'https://127.0.0.1:{10000+i}' for i in range(len(identities))]
    roster={k['peer_id']:dict(public_key=k['public_key'],endpoints=[u])
            for k,u in zip(identities,urls)}
    directory=PeerDirectory(identities[0],urls[0],roster,{},now=lambda:1000.0)
    directory.own_record()
    for identity,url in zip(identities[1:],urls[1:]):
        remote=PeerDirectory(identity,url,roster,{},now=lambda:1000.0)
        assert directory.accept(remote.own_record(),persist=False)
    assert len(directory.snapshot())==72
    batch=directory.exchange_batch()
    assert len(batch)==64
    assert any(r['payload']['peer_id']==identities[0]['peer_id'] for r in batch)
