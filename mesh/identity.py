"""Assinaturas individuais de requisições e recibos (não prova neural)."""
import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from .protocol import encode,headers


def peer_for_endpoint(trusted,endpoint):
    matches=[(peer_id,item['public_key']) for peer_id,item in trusted.items() if endpoint in item['endpoints']]
    if len(matches)!=1:raise ValueError('Endpoint deve ter exatamente uma identidade autorizada')
    return matches[0]


def signed_headers(secret,body,path,identity=None):
    result=headers(secret,body)
    if identity:
        signed=b'POST\n'+path.encode()+b'\n'+result['X-Time'].encode()+b'\n'+body
        key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(identity['private_key']))
        result['X-Peer-ID']=identity['peer_id']
        result['X-Peer-Signature']=base64.b64encode(key.sign(signed)).decode()
    return result


def verify_sender(request,message,peer):
    peer_id,public_key=peer
    if request.headers.get('x-peer-id')!=peer_id:raise ValueError('Identidade do remetente incorreta')
    signed=b'POST\n'+request.url.path.encode()+b'\n'+request.headers.get('x-time','').encode()+b'\n'+encode(message)
    signature=base64.b64decode(request.headers.get('x-peer-signature',''),validate=True)
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature,signed)


def sign_result(identity,message,result):
    proof=dict(peer_id=identity['peer_id'],request_hash=hashlib.sha256(encode(message)).hexdigest(),result_hash=hashlib.sha256(encode(result)).hexdigest())
    key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(identity['private_key']))
    proof['signature']=base64.b64encode(key.sign(encode(proof))).decode()
    return dict(result,proof=proof)


def verify_result(result,message,peer):
    peer_id,public_key=peer
    proof=result.get('proof')
    if not isinstance(proof,dict) or set(proof)!={'peer_id','request_hash','result_hash','signature'}:raise ValueError('Recibo individual ausente')
    payload={key:value for key,value in result.items() if key!='proof'}
    expected=dict(peer_id=peer_id,request_hash=hashlib.sha256(encode(message)).hexdigest(),result_hash=hashlib.sha256(encode(payload)).hexdigest())
    if any(proof.get(key)!=value for key,value in expected.items()):raise ValueError('Recibo não corresponde à requisição/resposta')
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(base64.b64decode(proof['signature'],validate=True),encode(expected))
    return proof
