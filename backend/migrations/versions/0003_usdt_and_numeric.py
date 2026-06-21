"""USDT migration: rename *_inr columns to *_usdt and widen money columns to Numeric

- user_bot_config: rename the three INR money columns (already Numeric).
- trades / positions: rename amount_inr -> amount_usdt and convert all money
  columns from Float to exact Numeric (price/qty/amount/pnl).

Revision ID: 0003_usdt_and_numeric
Revises: 0002_orders
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_usdt_and_numeric"
down_revision: Union[str, None] = "0002_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, Numeric type) for Float -> Numeric conversions
_PRICE = sa.Numeric(20, 8)
_QTY = sa.Numeric(30, 12)
_AMT = sa.Numeric(18, 2)
_PCT = sa.Numeric(12, 4)


def upgrade() -> None:
    # ── user_bot_config: rename only (already Numeric) ───────────────────────
    op.alter_column("user_bot_config", "initial_capital_inr",
                    new_column_name="initial_capital_usdt")
    op.alter_column("user_bot_config", "max_position_inr",
                    new_column_name="max_position_usdt")
    op.alter_column("user_bot_config", "daily_loss_limit_inr",
                    new_column_name="daily_loss_limit_usdt")

    # ── trades: widen money cols, then rename amount ─────────────────────────
    for col, typ in [("entry_price", _PRICE), ("exit_price", _PRICE),
                     ("qty", _QTY), ("amount_inr", _AMT), ("proceeds", _AMT),
                     ("pnl", _AMT), ("pnl_pct", _PCT)]:
        op.alter_column("trades", col, type_=typ,
                        postgresql_using=f"{col}::numeric")
    op.alter_column("trades", "amount_inr", new_column_name="amount_usdt")

    # ── positions: widen money cols, then rename amount ──────────────────────
    for col, typ in [("qty", _QTY), ("entry_price", _PRICE), ("amount_inr", _AMT),
                     ("stop_loss", _PRICE), ("take_profit", _PRICE),
                     ("trailing_high", _PRICE)]:
        op.alter_column("positions", col, type_=typ,
                        postgresql_using=f"{col}::numeric")
    op.alter_column("positions", "amount_inr", new_column_name="amount_usdt")


def downgrade() -> None:
    op.alter_column("positions", "amount_usdt", new_column_name="amount_inr")
    for col in ["qty", "entry_price", "amount_inr", "stop_loss", "take_profit",
                "trailing_high"]:
        op.alter_column("positions", col, type_=sa.Float(),
                        postgresql_using=f"{col}::double precision")

    op.alter_column("trades", "amount_usdt", new_column_name="amount_inr")
    for col in ["entry_price", "exit_price", "qty", "amount_inr", "proceeds",
                "pnl", "pnl_pct"]:
        op.alter_column("trades", col, type_=sa.Float(),
                        postgresql_using=f"{col}::double precision")

    op.alter_column("user_bot_config", "daily_loss_limit_usdt",
                    new_column_name="daily_loss_limit_inr")
    op.alter_column("user_bot_config", "max_position_usdt",
                    new_column_name="max_position_inr")
    op.alter_column("user_bot_config", "initial_capital_usdt",
                    new_column_name="initial_capital_inr")
