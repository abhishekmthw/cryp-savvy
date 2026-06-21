"""orders table (idempotent order intent log)

Adds the ``orders`` table written before every exchange call (status=pending)
and reconciled to filled/failed/unconfirmed afterwards. The primary key is a
client-generated UUID used as the idempotency key.

Revision ID: 0002_orders
Revises: 0001_multi_tenant_initial
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_orders"
down_revision: Union[str, None] = "0001_multi_tenant_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.String(), primary_key=True),  # client_order_id (UUID4)
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(),
                  server_default=sa.text("'pending'"), nullable=False),
        sa.Column("quote_currency", sa.String(),
                  server_default=sa.text("'USDT'"), nullable=False),
        sa.Column("requested_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("requested_qty", sa.Numeric(30, 12), nullable=True),
        sa.Column("requested_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("fill_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("fill_qty", sa.Numeric(30, 12), nullable=True),
        sa.Column("exchange_order_id", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_orders_user_created", "orders", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_user_created", table_name="orders")
    op.drop_table("orders")
