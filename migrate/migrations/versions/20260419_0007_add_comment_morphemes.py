"""Add comment_morphemes table

Revision ID: 20260419_0007
Revises: 20260310_0006
Create Date: 2026-04-19 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260419_0007"
down_revision: str | None = "20260310_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS `comment_morphemes` (
            `comment_id` varchar(128) NOT NULL,
            `mode`       char(1)      NOT NULL DEFAULT 'C'
                         COMMENT 'SudachiPy 分割モード: A=最小, B=中間, C=最大',
            `tokens`     json         NOT NULL
                         COMMENT '[{surface, reading, pos, pos_detail, base_form, normalized_form}, ...]',
            `analyzed_at` datetime(6) NOT NULL,
            PRIMARY KEY (`comment_id`, `mode`),
            CONSTRAINT `fk_comment_morphemes_comment`
                FOREIGN KEY (`comment_id`) REFERENCES `comments` (`comment_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `comment_morphemes`")
