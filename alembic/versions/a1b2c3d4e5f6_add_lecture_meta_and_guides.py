"""Add lecture metadata columns and guides table

Revision ID: a1b2c3d4e5f6
Revises: 6de290e60a58
Create Date: 2026-03-31 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6de290e60a58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lectures', sa.Column('week', sa.Integer(), nullable=True))
    op.add_column('lectures', sa.Column('subject', sa.String(), nullable=True))
    op.add_column('lectures', sa.Column('instructor', sa.String(), nullable=True))
    op.add_column('lectures', sa.Column('session', sa.String(), nullable=True))
    op.add_column('lectures', sa.Column('date', sa.Date(), nullable=True))

    op.create_table(
        'guides',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lecture_id', sa.UUID(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('key_summaries', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('review_checklist', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('concept_map', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['lecture_id'], ['lectures.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lecture_id'),
    )


def downgrade() -> None:
    op.drop_table('guides')
    op.drop_column('lectures', 'date')
    op.drop_column('lectures', 'session')
    op.drop_column('lectures', 'instructor')
    op.drop_column('lectures', 'subject')
    op.drop_column('lectures', 'week')
