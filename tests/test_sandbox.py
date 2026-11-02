import os
import pytest
from mesh.workspace import Workspace

IMAGE=os.getenv('MESH_TEST_IMAGE')
pytestmark=pytest.mark.skipif(not IMAGE,reason='Set MESH_TEST_IMAGE to an approved local Docker image ID')

def test_docker_execution_and_boundaries(tmp_path):
    w=Workspace(tmp_path)
    content="""import unittest,os,socket
class Boundaries(unittest.TestCase):
 def test_identity(self):self.assertEqual(os.getuid(),65534)
 def test_readonly(self):
  with self.assertRaises(OSError):open('/workspace/escape.txt','w')
 def test_no_docker_socket(self):self.assertFalse(os.path.exists('/var/run/docker.sock'))
 def test_no_network(self):
  with socket.socket() as s:
   s.settimeout(.2)
   with self.assertRaises(OSError):s.connect(('1.1.1.1',443))
"""
    w.write('alice','test_boundaries.py',content)
    result=w.run_tests('alice',IMAGE)
    assert result['ok'],result
    assert 'Ran 4 tests' in result['output']
    assert not (w.directory('alice')/'escape.txt').exists()


def test_docker_timeout_and_output_limit(tmp_path):
    w=Workspace(tmp_path)
    original=w.write('alice','test_busy.py','while True: pass\n')
    result=w.run_tests('alice',IMAGE,timeout=1)
    assert result['timeout'] and not result['ok']
    w.write('alice','test_busy.py',"print('x'*70000)\n",original['revision'])
    result=w.run_tests('alice',IMAGE)
    assert result['truncated'] and not result['ok']
    assert len(result['output'])<66000
