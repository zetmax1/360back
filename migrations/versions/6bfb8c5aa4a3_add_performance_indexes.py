"""add_performance_indexes

Revision ID: 6bfb8c5aa4a3
Revises: 819660dfe612
Create Date: 2026-06-10 09:25:27.734388
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6bfb8c5aa4a3'
down_revision: Union[str, None] = '819660dfe612'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Need to commit the transaction block started by Alembic to run CONCURRENTLY
    op.execute("COMMIT")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tour_slug ON tours(slug) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tour_published ON tours(is_published) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scene_tour_id ON scenes(tour_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scene_tour_order ON scenes(tour_id, order_index)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_link_from_scene ON scene_links(from_scene_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_link_to_scene ON scene_links(to_scene_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_upload_status ON image_uploads(upload_status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tour_slug")
    op.execute("DROP INDEX IF EXISTS idx_tour_published")
    op.execute("DROP INDEX IF EXISTS idx_scene_tour_id")
    op.execute("DROP INDEX IF EXISTS idx_scene_tour_order")
    op.execute("DROP INDEX IF EXISTS idx_link_from_scene")
    op.execute("DROP INDEX IF EXISTS idx_link_to_scene")
    op.execute("DROP INDEX IF EXISTS idx_upload_status")
