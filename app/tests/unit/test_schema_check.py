import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

from sqlalchemy.dialects import mysql


def _load_check_schema_module():
    candidate_paths = [
        Path("/migrate/check_schema.py"),
        Path(__file__).resolve().parents[3] / "migrate" / "check_schema.py",
    ]
    module_path = next(path for path in candidate_paths if path.exists())
    spec = importlib.util.spec_from_file_location("twicome_check_schema_unit", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeInspector:
    def __init__(self, tables):
        self._tables = tables

    def get_table_names(self):
        return list(self._tables)

    def get_columns(self, table_name):
        return deepcopy(self._tables[table_name]["columns"])

    def get_pk_constraint(self, table_name):
        return deepcopy(self._tables[table_name]["pk"])

    def get_indexes(self, table_name):
        return deepcopy(self._tables[table_name]["indexes"])

    def get_unique_constraints(self, table_name):
        return deepcopy(self._tables[table_name]["unique_constraints"])

    def get_foreign_keys(self, table_name):
        return deepcopy(self._tables[table_name]["foreign_keys"])


def _build_reflected_schema(schema_spec):
    tables = {}

    for table_name, table_spec in schema_spec.items():
        columns = []
        for column_name, column_spec in table_spec.columns.items():
            columns.append(
                {
                    "name": column_name,
                    "type": column_spec.type_,
                    "nullable": column_spec.nullable,
                    "autoincrement": "auto" if column_spec.autoincrement else False,
                }
            )

        indexes = []
        unique_constraints = []
        for index_name, index_spec in table_spec.indexes.items():
            payload = {
                "name": index_name,
                "column_names": list(index_spec.columns),
            }
            if index_spec.unique:
                unique_constraints.append(payload)
            else:
                indexes.append({**payload, "unique": False})

        foreign_keys = []
        for fk_name, fk_spec in table_spec.foreign_keys.items():
            foreign_keys.append(
                {
                    "name": fk_name,
                    "constrained_columns": list(fk_spec.columns),
                    "referred_table": fk_spec.referred_table,
                    "referred_columns": list(fk_spec.referred_columns),
                    "options": {
                        "ondelete": fk_spec.ondelete,
                        "onupdate": fk_spec.onupdate,
                    },
                }
            )

        tables[table_name] = {
            "columns": columns,
            "pk": {"constrained_columns": list(table_spec.primary_key)},
            "indexes": indexes,
            "unique_constraints": unique_constraints,
            "foreign_keys": foreign_keys,
        }

    return tables


def test_validate_schema_accepts_expected_schema():
    check_schema = _load_check_schema_module()
    inspector = FakeInspector(_build_reflected_schema(check_schema.SCHEMA_SPEC))

    assert check_schema.validate_schema(inspector) == []


def test_validate_schema_reports_missing_details():
    check_schema = _load_check_schema_module()
    tables = _build_reflected_schema(check_schema.SCHEMA_SPEC)

    tables.pop("vod_ingest_markers")
    tables["comments"]["columns"] = [
        column for column in tables["comments"]["columns"] if column["name"] != "body_html_version"
    ]
    for column in tables["community_notes"]["columns"]:
        if column["name"] == "status":
            column["type"] = mysql.VARCHAR(32)
        if column["name"] == "note_id":
            column["autoincrement"] = False
    for index in tables["comments"]["indexes"]:
        if index["name"] == "idx_comments_user_created_sort":
            index["column_names"] = ["commenter_user_id", "comment_created_at_utc"]
    for foreign_key in tables["comments"]["foreign_keys"]:
        if foreign_key["name"] == "fk_comments_vod":
            foreign_key["options"]["ondelete"] = "RESTRICT"

    errors = check_schema.validate_schema(FakeInspector(tables))

    assert "Missing tables: vod_ingest_markers" in errors
    assert "comments: missing columns: body_html_version" in errors
    assert any("community_notes.status: type mismatch" in error for error in errors)
    assert any("community_notes.note_id: autoincrement mismatch" in error for error in errors)
    assert any("comments.idx_comments_user_created_sort: columns mismatch" in error for error in errors)
    assert any("comments.fk_comments_vod: ondelete mismatch" in error for error in errors)
