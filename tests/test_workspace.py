import pytest
from mesh.workspace import Workspace,RevisionConflict

def test_private_files_revisions_and_syntax(tmp_path):
    w=Workspace(tmp_path)
    created=w.write('alice','src/add.py','def add(a,b):\n    return a+b\n')
    assert w.listing('bob')==[]
    assert w.check('alice','src/add.py')['ok']
    with pytest.raises(RevisionConflict):w.write('alice','src/add.py','x=1')
    changed=w.write('alice','src/add.py','def broken(:',created['revision'])
    assert changed['diff'] and not w.check('alice','src/add.py')['ok']
    with pytest.raises(FileNotFoundError):w.read('bob','src/add.py')

@pytest.mark.parametrize('name',['.','../key','.env','a/../../key','/etc/passwd','C:/secret','a\\b','x/./a','a//b','a/.hidden/x'])
def test_traversal(tmp_path,name):
    with pytest.raises(ValueError):Workspace(tmp_path).write('alice',name,'x')

def test_symlink_and_limits(tmp_path):
    w=Workspace(tmp_path/'files')
    with pytest.raises(ValueError):w.write('a','big.txt','x'*131073)
    outside=tmp_path/'outside';outside.mkdir()
    link=w.directory('a')/'link'
    try:link.symlink_to(outside,target_is_directory=True)
    except OSError:return # Windows pode não permitir criar links sem privilégio.
    with pytest.raises(ValueError):w.write('a','link/x.txt','x')


def test_directory_cannot_be_replaced_by_file(tmp_path):
    w=Workspace(tmp_path)
    w.write('a','src/main.py','x=1')
    with pytest.raises(ValueError):w.write('a','src','overwrite')
