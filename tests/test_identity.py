import copy
import pytest
from cryptography.exceptions import InvalidSignature
from mesh.discovery import new_identity
from mesh.identity import sign_result,verify_result,peer_for_endpoint

def test_receipt_binds_result_request_and_identity():
    identity=new_identity();other=new_identity()
    peer=(identity['peer_id'],identity['public_key'])
    request={'session':'a','position':0}
    result=sign_result(identity,request,dict(position=1,units=1))
    assert verify_result(result,request,peer)
    tampered=copy.deepcopy(result);tampered['units']=2
    with pytest.raises(ValueError):verify_result(tampered,request,peer)
    with pytest.raises(ValueError):verify_result(result,{'session':'b','position':0},peer)
    with pytest.raises(ValueError):verify_result(result,request,(other['peer_id'],other['public_key']))
    bad=copy.deepcopy(result);bad['proof']['signature']='A'*88
    with pytest.raises((ValueError,InvalidSignature)):verify_result(bad,request,peer)


def test_endpoint_has_unique_pinned_identity():
    identity=new_identity()
    roster={identity['peer_id']:dict(public_key=identity['public_key'],endpoints=['https://peer.invalid'])}
    assert peer_for_endpoint(roster,'https://peer.invalid')==(identity['peer_id'],identity['public_key'])
    with pytest.raises(ValueError):peer_for_endpoint(roster,'https://unknown.invalid')


def test_sender_signature_binds_route_body_and_time():
    from fastapi import FastAPI,Request,HTTPException
    from fastapi.testclient import TestClient
    from mesh.identity import signed_headers,verify_sender
    from mesh.protocol import authenticated,encode
    identity=new_identity()
    app=FastAPI()
    @app.post('/step')
    async def endpoint(request:Request):
        message=await authenticated(request,'secret')
        try:verify_sender(request,message,(identity['peer_id'],identity['public_key']))
        except Exception:raise HTTPException(401)
        return {'ok':True}
    body=encode({'session':'a'})
    client=TestClient(app)
    assert client.post('/step',content=body,headers=signed_headers('secret',body,'/step',identity)).status_code==200
    assert client.post('/step',content=body,headers=signed_headers('secret',body,'/release',identity)).status_code==401
    assert client.post('/step',content=body,headers=signed_headers('secret',body,'/step')).status_code==401
