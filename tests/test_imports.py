from seahealth import __version__
from seahealth import db, schemas, agents, pipelines, eval as eval_pkg, api  # eval is a builtin


def test_package_imports():
    assert __version__ == "0.0.1"
    assert db is not None
    assert schemas is not None
    assert agents is not None
    assert pipelines is not None
    assert eval_pkg is not None
    assert api is not None
