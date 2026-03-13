"""Add index on commenter_login_snapshot for user search stats

Revision ID: 20260227_0003
Revises: 20260225_0002
Create Date: 2026-02-27 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260227_0003"
down_revision: str | None = "20260225_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # commenter_login_snapshot でのGROUP BY + MAX(comment_created_at_utc) を高速化
    op.execute(
        "ALTER TABLE `comments` ADD KEY `idx_comments_commenter_login_at` "
        "(`commenter_login_snapshot`, `comment_created_at_utc`)"
    )
    # commenter_login_snapshot + vod_id でのGROUP_CONCAT集計を高速化
    op.execute(
        "ALTER TABLE `comments` ADD KEY `idx_comments_commenter_login_vod` "
        "(`commenter_login_snapshot`, `vod_id`)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `comments` DROP INDEX `idx_comments_commenter_login_at`")
    op.execute("ALTER TABLE `comments` DROP INDEX `idx_comments_commenter_login_vod`")
