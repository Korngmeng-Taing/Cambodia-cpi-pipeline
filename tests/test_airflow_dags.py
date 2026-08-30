import ast
import os
import pytest

DAGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orchestration", "dags")

DAG_FILES = [
    "cpi_master_dag.py",
    "scraper_dags.py",
    "silver_dag.py",
    "gold_dag.py",
    "gold_cpi_dag.py"
]

@pytest.mark.parametrize("filename", DAG_FILES)
def test_dag_files_exist(filename):
    path = os.path.join(DAGS_DIR, filename)
    assert os.path.exists(path), f"DAG file {filename} does not exist in {DAGS_DIR}"

@pytest.mark.parametrize("filename", DAG_FILES)
def test_dag_python_syntax(filename):
    path = os.path.join(DAGS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    # Must parse without SyntaxError
    parsed = ast.parse(source, filename=filename)
    assert parsed is not None

@pytest.mark.parametrize("filename", DAG_FILES)
def test_dag_contains_dag_declaration(filename):
    path = os.path.join(DAGS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "DAG(" in content or "@dag" in content, f"File {filename} does not contain a DAG declaration"
    assert "dag_id=" in content or "@dag" in content, f"File {filename} must declare dag_id"

def test_all_dags_have_catchup_false():
    for filename in DAG_FILES:
        path = os.path.join(DAGS_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "catchup=False" in content, f"DAG in {filename} must specify catchup=False for production safety"
