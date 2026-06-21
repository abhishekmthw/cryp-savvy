"""capital-allocation feature: allocations + bucket_state tables, bucket columns

Revision ID: 0004_allocation
Revises: 0003_usdt_and_numeric
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_allocation"
down_revision: Union[str, None] = "0003_usdt_and_numeric"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allocations",
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("base_currency", sa.String(),
                  server_default=sa.text("'USDT'"), nullable=False),
        sa.Column("total_allocated", sa.Numeric(18, 2), nullable=False),
        sa.Column("day_budget", sa.Numeric(18, 2), nullable=False),
        sa.Column("long_budget", sa.Numeric(18, 2), nullable=False),
        sa.Column("allocate_all", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(),
                  server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "bucket_state",
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("bucket", sa.String(), primary_key=True),
        sa.Column("realized_pnl", sa.Numeric(18, 2),
                  server_default=sa.text("0"), nullable=False),
        sa.Column("peak_equity", sa.Numeric(18, 2),
                  server_default=sa.text("0"), nullable=False),
        sa.Column("drawdown_state", sa.String(),
                  server_default=sa.text("'normal'"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.add_column("positions", sa.Column("bucket", sa.String(),
                  server_default=sa.text("'day'"), nullable=False))
    op.add_column("orders", sa.Column("bucket", sa.String(),
                  server_default=sa.text("'day'"), nullable=False))


def downgrade() -> None:
    op.drop_column("orders", "bucket")
    op.drop_column("positions", "bucket")
    op.drop_table("bucket_state")
    op.drop_table("allocations")
