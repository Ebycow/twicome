"""Add covering index on (commenter_user_id, vod_id, comment_created_at_utc) for vod_options query

Revision ID: 20260310_0004
Revises: 20260227_0003
Create Date: 2026-03-10 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260310_0004"
down_revision: str | None = "20260227_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # commenter_user_id でのGROUP BY vod_id + MAX(comment_created_at_utc) をカバリングインデックスで高速化
    # vod_options クエリ（ユーザーコメントページのVODドロップダウン）の2秒→0.04秒改善
    # 既に手動で追加済みの場合はスキップ
    from sqlalchemy import inspect
    conn = op.get_bind()
    existing = [idx["name"] for idx in inspect(conn).get_indexes("comments")]
    if "idx_comments_user_vod_created" not in existing:
        op.execute(
            "ALTER TABLE `comments` ADD KEY `idx_comments_user_vod_created` "
            "(`commenter_user_id`, `vod_id`, `comment_created_at_utc`)"
        )


def downgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    existing = [idx["name"] for idx in inspect(conn).get_indexes("comments")]
    if "idx_comments_user_vod_created" in existing:
        op.execute("ALTER TABLE `comments` DROP INDEX `idx_comments_user_vod_created`")
