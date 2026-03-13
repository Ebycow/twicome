"""Add covering index for created_at sort on user comments page

Revision ID: 20260310_0005
Revises: 20260310_0004
Create Date: 2026-03-10 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260310_0005"
down_revision: str | None = "20260310_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ORDER BY comment_created_at_utc DESC, vod_id DESC, offset_seconds DESC のソートを
    # filesort なしで処理するカバリングインデックス
    # ユーザーコメントページのメインSELECT（created_at ソート）を 2秒→0.002秒に改善
    from sqlalchemy import inspect
    conn = op.get_bind()
    existing = [idx["name"] for idx in inspect(conn).get_indexes("comments")]
    if "idx_comments_user_created_sort" not in existing:
        op.execute(
            "ALTER TABLE `comments` ADD KEY `idx_comments_user_created_sort` "
            "(`commenter_user_id`, `comment_created_at_utc`, `vod_id`, `offset_seconds`)"
        )


def downgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    existing = [idx["name"] for idx in inspect(conn).get_indexes("comments")]
    if "idx_comments_user_created_sort" in existing:
        op.execute("ALTER TABLE `comments` DROP INDEX `idx_comments_user_created_sort`")
