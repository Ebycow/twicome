import importlib.util
import sys
from pathlib import Path

from sqlalchemy import inspect


def _load_check_schema_module():
    candidate_paths = [
        Path("/migrate/check_schema.py"),
        Path(__file__).resolve().parents[3] / "migrate" / "check_schema.py",
    ]
    module_path = next(path for path in candidate_paths if path.exists())
    spec = importlib.util.spec_from_file_location("twicome_check_schema_integration", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_schema_matches_migrated_database(db_engine):
    check_schema = _load_check_schema_module()

    with db_engine.connect() as conn:
        errors = check_schema.validate_schema(inspect(conn))

    assert errors == []
