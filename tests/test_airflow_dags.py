import ast
import os
import pytest

_host_dags = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orchestration", "dags")
_container_dags = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dags")
DAGS_DIR = _host_dags if os.path.exists(_host_dags) else _container_dags

DAG_FILES = [
    "cpi_master_dag.py",
    "cpi_maintenance_dag.py",
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
    with open(path, encoding="utf-8") as f:
        source = f.read()
    # Must parse without SyntaxError
    parsed = ast.parse(source, filename=filename)
    assert parsed is not None

@pytest.mark.parametrize("filename", DAG_FILES)
def test_dag_contains_dag_declaration(filename):
    path = os.path.join(DAGS_DIR, filename)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "DAG(" in content or "@dag" in content, f"File {filename} does not contain a DAG declaration"
    assert "dag_id=" in content or "@dag" in content, f"File {filename} must declare dag_id"

def test_all_dags_have_catchup_false():
    for filename in DAG_FILES:
        path = os.path.join(DAGS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "catchup=False" in content, f"DAG in {filename} must specify catchup=False for production safety"


def test_dag_jinja_templates_compile():
    """Validates that all Jinja template expressions in DAG files compile without TemplateSyntaxError."""
    import re
    import jinja2
    import pendulum

    env = jinja2.Environment()
    for filename in DAG_FILES:
        path = os.path.join(DAGS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Match Jinja {{ (dag_run... or other Jinja tags, excluding f-string {{'ds' escapes
        matches = re.findall(r"\{\{\s*\([^\}]+\)\s*\}\}", content, re.DOTALL)
        for expr in matches:
            try:
                env.parse(expr)
                t = env.from_string(expr)
                rendered = t.render(
                    dag_run=None,
                    ds="2026-09-05",
                    data_interval_end=pendulum.now("Asia/Phnom_Penh"),
                )
                assert rendered is not None
            except Exception as exc:
                pytest.fail(f"Jinja template failed in {filename} on expression {expr!r}: {exc}")
