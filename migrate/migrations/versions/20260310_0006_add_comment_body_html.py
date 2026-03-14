"""Persist pre-rendered body_html on comments

Revision ID: 20260310_0006
Revises: 20260310_0005
Create Date: 2026-03-10 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260310_0006"
down_revision: str | None = "20260310_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    existing = {col["name"] for col in inspect(conn).get_columns("comments")}

    if "body_html" not in existing:
        op.execute("ALTER TABLE `comments` ADD COLUMN `body_html` MEDIUMTEXT NULL AFTER `body`")

    if "body_html_version" not in existing:
        op.execute(
            "ALTER TABLE `comments` "
            "ADD COLUMN `body_html_version` SMALLINT UNSIGNED NOT NULL DEFAULT 1 AFTER `body_html`"
        )


def downgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    existing = {col["name"] for col in inspect(conn).get_columns("comments")}

    if "body_html_version" in existing:
        op.execute("ALTER TABLE `comments` DROP COLUMN `body_html_version`")

    if "body_html" in existing:
        op.execute("ALTER TABLE `comments` DROP COLUMN `body_html`")
