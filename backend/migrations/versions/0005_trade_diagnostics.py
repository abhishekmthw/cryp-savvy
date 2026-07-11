"""trade diagnostics: entry-attribution columns on trades + positions

Records which capital bucket, sub-strategy, market regime, and composite
conviction score opened each position, and carries them to the trades row on
close. All nullable/additive — trades booked before this migration keep NULLs
and are simply excluded from the by-bucket/strategy/regime breakdowns.

Revision ID: 0005_trade_diagnostics
Revises: 0004_allocation
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_trade_diagnostics"
down_revision: Union[str, None] = "0004_allocation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("bucket", sa.String(), nullable=True))
    op.add_column("trades", sa.Column("strategy", sa.String(), nullable=True))
    op.add_column("trades", sa.Column("regime", sa.String(), nullable=True))
    op.add_column("trades", sa.Column("entry_score", sa.Numeric(6, 2), nullable=True))

    op.add_column("positions", sa.Column("strategy", sa.String(), nullable=True))
    op.add_column("positions", sa.Column("regime", sa.String(), nullable=True))
    op.add_column("positions", sa.Column("entry_score", sa.Numeric(6, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "entry_score")
    op.drop_column("positions", "regime")
    op.drop_column("positions", "strategy")

    op.drop_column("trades", "entry_score")
    op.drop_column("trades", "regime")
    op.drop_column("trades", "strategy")
    op.drop_column("trades", "bucket")
