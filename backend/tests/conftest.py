import os
from pathlib import Path
import pytest

def pytest_addoption(parser):
    parser.addoption('--fc-archive', default=None, help='Optional local official FC 1.1.0 archive for synthetic compatibility checks.')

@pytest.fixture
def fc_archive(request):
    value = request.config.getoption('--fc-archive')
    if not value:
        pytest.skip('Official FC archive not supplied; no live FC access is attempted.')
    return Path(value)
os.environ['PYTHON_DOTENV_DISABLED']='1'
for name in tuple(os.environ):
    if name.startswith(('FINANCE_CORE_','OPENAI_','FRAG_')):
        os.environ.pop(name)
@pytest.fixture
def source_root(tmp_path:Path):
    root=tmp_path/'sources';root.mkdir();(root/'evidence.md').write_text('# Finding\nA synthetic finding is supported.\n# Limits\nEvidence is incomplete.',encoding='utf8');return root
