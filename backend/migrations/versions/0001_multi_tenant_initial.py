"""multi-tenant initial schema

Revision ID: 0001_multi_tenant_initial
Revises:
Create Date: 2026-05-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_multi_tenant_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("clerk_user_id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("bot_enabled", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False),
        sa.Column("mode", sa.String(),
                  server_default=sa.text("'paper'"), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("dek_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("kek_version", sa.Integer(),
                  server_default=sa.text("1"), nullable=False),
    )

    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("provider", sa.String(), primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("last4", sa.String(length=8), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_bot_config",
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("initial_capital_inr", sa.Numeric(14, 2), nullable=False),
        sa.Column("max_position_inr", sa.Numeric(14, 2), nullable=False),
        sa.Column("max_open_positions", sa.Integer(), nullable=False),
        sa.Column("stop_loss_pct", sa.Numeric(6, 4), nullable=False),
        sa.Column("take_profit_pct", sa.Numeric(6, 4), nullable=False),
        sa.Column("trailing_stop_trigger", sa.Numeric(6, 4), nullable=False),
        sa.Column("trailing_stop_offset", sa.Numeric(6, 4), nullable=False),
        sa.Column("daily_loss_limit_inr", sa.Numeric(14, 2), nullable=False),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("amount_inr", sa.Float(), nullable=True),
        sa.Column("proceeds", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("ts", sa.Float(), nullable=False),
    )
    op.create_index("ix_trades_user_ts", "trades", ["user_id", "ts"])

    op.create_table(
        "positions",
        sa.Column("user_id", sa.String(),
                  sa.ForeignKey("users.clerk_user_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("entry_time", sa.Float(), nullable=False),
        sa.Column("amount_inr", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("trailing_high", sa.Float(),
                  server_default=sa.text("0"), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(),
                  server_default=sa.text("'open'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_index("ix_trades_user_ts", table_name="trades")
    op.drop_table("trades")
    op.drop_table("user_bot_config")
    op.drop_table("user_credentials")
    op.drop_table("users")
