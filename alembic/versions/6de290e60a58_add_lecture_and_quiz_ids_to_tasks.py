"""add_lecture_and_quiz_ids_to_tasks

Revision ID: 6de290e60a58
Revises: fbe315984c02
Create Date: 2026-03-23 00:13:57.820051

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6de290e60a58'
down_revision: Union[str, Sequence[str], None] = 'fbe315984c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add only the minimum necessary columns to avoid unrelated casting errors."""
    # 1. 강의 ID 및 퀴즈 ID 컬럼 추가 (UUID 타입)
    op.add_column('ai_tasks', sa.Column('lecture_id', sa.UUID(), nullable=True))
    op.add_column('ai_tasks', sa.Column('quiz_id', sa.UUID(), nullable=True))
    
    # 2. 외래키(ForeignKey) 연결 제약 조건 추가
    op.create_foreign_key('fk_aitask_lecture', 'ai_tasks', 'lectures', ['lecture_id'], ['id'])
    op.create_foreign_key('fk_aitask_quiz', 'ai_tasks', 'quizzes', ['quiz_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_aitask_quiz', 'ai_tasks', type_='foreignkey')
    op.drop_constraint('fk_aitask_lecture', 'ai_tasks', type_='foreignkey')
    op.drop_column('ai_tasks', 'quiz_id')
    op.drop_column('ai_tasks', 'lecture_id')
