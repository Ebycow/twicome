from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql

MYSQL_DIALECT = mysql.dialect()


@dataclass(frozen=True)
class ColumnSpec:
    type_: Any
    nullable: bool
    autoincrement: bool | None = None


@dataclass(frozen=True)
class IndexSpec:
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class ForeignKeySpec:
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]
    ondelete: str | None = None
    onupdate: str | None = None


@dataclass(frozen=True)
class TableSpec:
    columns: dict[str, ColumnSpec]
    primary_key: tuple[str, ...]
    indexes: dict[str, IndexSpec] = field(default_factory=dict)
    foreign_keys: dict[str, ForeignKeySpec] = field(default_factory=dict)


SCHEMA_SPEC = {
    "users": TableSpec(
        columns={
            "user_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False),
            "login": ColumnSpec(mysql.VARCHAR(64), nullable=False),
            "display_name": ColumnSpec(mysql.VARCHAR(128), nullable=True),
            "profile_image_url": ColumnSpec(mysql.VARCHAR(512), nullable=True),
            "platform": ColumnSpec(mysql.VARCHAR(32), nullable=False),
            "created_at": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
            "updated_at": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
        },
        primary_key=("user_id",),
        indexes={
            "uq_users_platform_login": IndexSpec(columns=("platform", "login"), unique=True),
            "idx_users_vod_fetch": IndexSpec(columns=("platform", "user_id")),
        },
    ),
    "vods": TableSpec(
        columns={
            "vod_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False),
            "owner_user_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False),
            "title": ColumnSpec(mysql.VARCHAR(512), nullable=False),
            "description": ColumnSpec(mysql.TEXT(), nullable=True),
            "created_at_utc": ColumnSpec(mysql.DATETIME(fsp=6), nullable=True),
            "length_seconds": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=True),
            "start_seconds": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=True),
            "end_seconds": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=True),
            "view_count": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=True),
            "game_name": ColumnSpec(mysql.VARCHAR(255), nullable=True),
            "platform": ColumnSpec(mysql.VARCHAR(32), nullable=False),
            "url": ColumnSpec(mysql.VARCHAR(512), nullable=True),
            "youtube_url": ColumnSpec(mysql.VARCHAR(512), nullable=True),
            "ingested_at": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
        },
        primary_key=("vod_id",),
        indexes={
            "idx_vods_owner": IndexSpec(columns=("owner_user_id",)),
        },
        foreign_keys={
            "fk_vods_owner": ForeignKeySpec(
                columns=("owner_user_id",),
                referred_table="users",
                referred_columns=("user_id",),
                ondelete="RESTRICT",
                onupdate="CASCADE",
            ),
        },
    ),
    "comments": TableSpec(
        columns={
            "comment_id": ColumnSpec(mysql.VARCHAR(128), nullable=False),
            "vod_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False),
            "offset_seconds": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=False),
            "comment_created_at_utc": ColumnSpec(mysql.DATETIME(fsp=6), nullable=True),
            "commenter_user_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=True),
            "commenter_login_snapshot": ColumnSpec(mysql.VARCHAR(64), nullable=True),
            "commenter_display_name_snapshot": ColumnSpec(mysql.VARCHAR(128), nullable=True),
            "body": ColumnSpec(mysql.TEXT(), nullable=False),
            "body_html": ColumnSpec(mysql.MEDIUMTEXT(), nullable=True),
            "body_html_version": ColumnSpec(mysql.SMALLINT(unsigned=True), nullable=False),
            "community_note_body": ColumnSpec(mysql.TEXT(), nullable=True),
            "community_note_created_at_utc": ColumnSpec(mysql.DATETIME(fsp=6), nullable=True),
            "community_note_updated_at_utc": ColumnSpec(mysql.DATETIME(fsp=6), nullable=True),
            "user_color": ColumnSpec(mysql.VARCHAR(16), nullable=True),
            "bits_spent": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=True),
            "raw_json": ColumnSpec(mysql.JSON(), nullable=True),
            "ingested_at": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
            "twicome_likes_count": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=False),
            "twicome_dislikes_count": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=False),
        },
        primary_key=("comment_id",),
        indexes={
            "idx_comments_vod_time": IndexSpec(columns=("vod_id", "offset_seconds")),
            "idx_comments_user_vod_time": IndexSpec(columns=("commenter_user_id", "vod_id", "offset_seconds")),
            "idx_comments_created_at": IndexSpec(columns=("comment_created_at_utc",)),
            "idx_comments_note_created_at": IndexSpec(columns=("community_note_created_at_utc",)),
            "idx_comments_user_created": IndexSpec(columns=("commenter_user_id", "comment_created_at_utc")),
            "idx_comments_vod_offset_user": IndexSpec(columns=("vod_id", "offset_seconds", "commenter_user_id")),
            "idx_comments_commenter_login_at": IndexSpec(
                columns=("commenter_login_snapshot", "comment_created_at_utc")
            ),
            "idx_comments_commenter_login_vod": IndexSpec(columns=("commenter_login_snapshot", "vod_id")),
            "idx_comments_user_vod_created": IndexSpec(
                columns=("commenter_user_id", "vod_id", "comment_created_at_utc")
            ),
            "idx_comments_user_created_sort": IndexSpec(
                columns=("commenter_user_id", "comment_created_at_utc", "vod_id", "offset_seconds")
            ),
        },
        foreign_keys={
            "fk_comments_commenter": ForeignKeySpec(
                columns=("commenter_user_id",),
                referred_table="users",
                referred_columns=("user_id",),
                ondelete="SET NULL",
                onupdate="CASCADE",
            ),
            "fk_comments_vod": ForeignKeySpec(
                columns=("vod_id",),
                referred_table="vods",
                referred_columns=("vod_id",),
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
        },
    ),
    "community_notes": TableSpec(
        columns={
            "note_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False, autoincrement=True),
            "comment_id": ColumnSpec(mysql.VARCHAR(128), nullable=False),
            "eligible": ColumnSpec(mysql.TINYINT(1), nullable=False),
            "status": ColumnSpec(
                mysql.ENUM("supported", "insufficient", "inconsistent", "not_applicable"),
                nullable=False,
            ),
            "note": ColumnSpec(mysql.TEXT(), nullable=False),
            "verifiability": ColumnSpec(mysql.TINYINT(unsigned=True), nullable=False),
            "harm_risk": ColumnSpec(mysql.TINYINT(unsigned=True), nullable=False),
            "exaggeration": ColumnSpec(mysql.TINYINT(unsigned=True), nullable=False),
            "evidence_gap": ColumnSpec(mysql.TINYINT(unsigned=True), nullable=False),
            "subjectivity": ColumnSpec(mysql.TINYINT(unsigned=True), nullable=False),
            "issues": ColumnSpec(mysql.JSON(), nullable=True),
            "ask": ColumnSpec(mysql.VARCHAR(255), nullable=False),
            "note_json": ColumnSpec(mysql.JSON(), nullable=False),
            "model": ColumnSpec(mysql.VARCHAR(64), nullable=True),
            "prompt_version": ColumnSpec(mysql.VARCHAR(32), nullable=True),
            "created_at_utc": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
            "updated_at_utc": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
        },
        primary_key=("note_id",),
        indexes={
            "uq_community_notes_comment": IndexSpec(columns=("comment_id",), unique=True),
            "idx_community_notes_status": IndexSpec(columns=("status",)),
            "idx_community_notes_harm": IndexSpec(columns=("harm_risk",)),
        },
        foreign_keys={
            "fk_community_notes_comment": ForeignKeySpec(
                columns=("comment_id",),
                referred_table="comments",
                referred_columns=("comment_id",),
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
        },
    ),
    "vod_ingest_markers": TableSpec(
        columns={
            "vod_id": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False),
            "source_filename": ColumnSpec(mysql.VARCHAR(255), nullable=False),
            "source_file_sha256": ColumnSpec(mysql.CHAR(64), nullable=False),
            "source_file_size": ColumnSpec(mysql.BIGINT(unsigned=True), nullable=False),
            "comments_ingested": ColumnSpec(mysql.INTEGER(unsigned=True), nullable=False),
            "completed_at": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
            "updated_at": ColumnSpec(mysql.DATETIME(fsp=6), nullable=False),
        },
        primary_key=("vod_id",),
        indexes={
            "idx_vod_ingest_markers_sha": IndexSpec(columns=("source_file_sha256",)),
        },
        foreign_keys={
            "fk_vod_ingest_markers_vod": ForeignKeySpec(
                columns=("vod_id",),
                referred_table="vods",
                referred_columns=("vod_id",),
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
        },
    ),
}


def _normalize_sql(value: Any) -> str:
    return " ".join(str(value).replace("\n", " ").lower().split())


def _normalize_type(type_: Any) -> str:
    if hasattr(type_, "compile"):
        return _normalize_sql(type_.compile(dialect=MYSQL_DIALECT))
    return _normalize_sql(type_)


def _normalize_autoincrement(value: Any) -> bool:
    return value not in (None, False, "", "ignore_fk")


def _load_index_specs(inspector: Any, table_name: str) -> dict[str, IndexSpec]:
    indexes: dict[str, IndexSpec] = {}

    for raw in inspector.get_indexes(table_name):
        name = raw.get("name")
        columns = tuple(raw.get("column_names") or ())
        if name and columns and all(columns):
            indexes[name] = IndexSpec(columns=columns, unique=bool(raw.get("unique", False)))

    for raw in inspector.get_unique_constraints(table_name):
        name = raw.get("name")
        columns = tuple(raw.get("column_names") or ())
        if name and columns:
            indexes[name] = IndexSpec(columns=columns, unique=True)

    return indexes


def _load_foreign_key_specs(inspector: Any, table_name: str) -> dict[str, ForeignKeySpec]:
    foreign_keys: dict[str, ForeignKeySpec] = {}

    for raw in inspector.get_foreign_keys(table_name):
        name = raw.get("name")
        if not name:
            continue
        options = raw.get("options") or {}
        foreign_keys[name] = ForeignKeySpec(
            columns=tuple(raw.get("constrained_columns") or ()),
            referred_table=raw.get("referred_table") or "",
            referred_columns=tuple(raw.get("referred_columns") or ()),
            ondelete=options.get("ondelete"),
            onupdate=options.get("onupdate"),
        )

    return foreign_keys


def _validate_table(inspector: Any, table_name: str, spec: TableSpec) -> list[str]:
    errors: list[str] = []

    columns = {column["name"]: column for column in inspector.get_columns(table_name)}
    missing_columns = sorted(set(spec.columns) - set(columns))
    if missing_columns:
        errors.append(f"{table_name}: missing columns: {', '.join(missing_columns)}")

    for column_name, column_spec in spec.columns.items():
        actual = columns.get(column_name)
        if actual is None:
            continue

        actual_type = _normalize_type(actual["type"])
        expected_type = _normalize_type(column_spec.type_)
        if actual_type != expected_type:
            errors.append(f"{table_name}.{column_name}: type mismatch: expected {expected_type}, got {actual_type}")

        actual_nullable = bool(actual.get("nullable"))
        if actual_nullable != column_spec.nullable:
            errors.append(
                f"{table_name}.{column_name}: nullable mismatch: expected {column_spec.nullable}, got {actual_nullable}"
            )

        if column_spec.autoincrement is not None:
            actual_autoincrement = _normalize_autoincrement(actual.get("autoincrement"))
            if actual_autoincrement != column_spec.autoincrement:
                errors.append(
                    f"{table_name}.{column_name}: autoincrement mismatch: "
                    f"expected {column_spec.autoincrement}, got {actual_autoincrement}"
                )

    pk_columns = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
    if pk_columns != spec.primary_key:
        errors.append(f"{table_name}: primary key mismatch: expected {spec.primary_key}, got {pk_columns}")

    indexes = _load_index_specs(inspector, table_name)
    for index_name, index_spec in spec.indexes.items():
        actual = indexes.get(index_name)
        if actual is None:
            errors.append(f"{table_name}: missing index: {index_name}")
            continue
        if actual.columns != index_spec.columns:
            errors.append(
                f"{table_name}.{index_name}: columns mismatch: expected {index_spec.columns}, got {actual.columns}"
            )
        if actual.unique != index_spec.unique:
            errors.append(
                f"{table_name}.{index_name}: unique mismatch: expected {index_spec.unique}, got {actual.unique}"
            )

    foreign_keys = _load_foreign_key_specs(inspector, table_name)
    for fk_name, fk_spec in spec.foreign_keys.items():
        actual = foreign_keys.get(fk_name)
        if actual is None:
            errors.append(f"{table_name}: missing foreign key: {fk_name}")
            continue

        if actual.columns != fk_spec.columns:
            errors.append(f"{table_name}.{fk_name}: columns mismatch: expected {fk_spec.columns}, got {actual.columns}")
        if actual.referred_table != fk_spec.referred_table:
            errors.append(
                f"{table_name}.{fk_name}: referred table mismatch: "
                f"expected {fk_spec.referred_table}, got {actual.referred_table}"
            )
        if actual.referred_columns != fk_spec.referred_columns:
            errors.append(
                f"{table_name}.{fk_name}: referred columns mismatch: "
                f"expected {fk_spec.referred_columns}, got {actual.referred_columns}"
            )

        actual_ondelete = _normalize_sql(actual.ondelete) if actual.ondelete is not None else None
        expected_ondelete = _normalize_sql(fk_spec.ondelete) if fk_spec.ondelete is not None else None
        if actual_ondelete != expected_ondelete:
            errors.append(
                f"{table_name}.{fk_name}: ondelete mismatch: expected {expected_ondelete}, got {actual_ondelete}"
            )

        actual_onupdate = _normalize_sql(actual.onupdate) if actual.onupdate is not None else None
        expected_onupdate = _normalize_sql(fk_spec.onupdate) if fk_spec.onupdate is not None else None
        if actual_onupdate != expected_onupdate:
            errors.append(
                f"{table_name}.{fk_name}: onupdate mismatch: expected {expected_onupdate}, got {actual_onupdate}"
            )

    return errors


def validate_schema(inspector: Any) -> list[str]:
    tables = set(inspector.get_table_names())
    errors: list[str] = []

    missing_tables = sorted(set(SCHEMA_SPEC) - tables)
    if missing_tables:
        errors.append(f"Missing tables: {', '.join(missing_tables)}")

    for table_name in sorted(set(SCHEMA_SPEC) & tables):
        errors.extend(_validate_table(inspector, table_name, SCHEMA_SPEC[table_name]))

    return errors


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1

    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        errors = validate_schema(inspect(conn))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("Schema check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
