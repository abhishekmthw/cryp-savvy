"""diagnostics v2: execution detail captured per trade

Adds the evidence needed to diagnose the strategy from real trades:
MAE/MFE excursion watermarks, the stop/take-profit as planned at entry
(so planned-vs-realized R:R is computable — trailing mutates the live
stop_loss), actual modeled fee/slippage per trade, the entry timestamp,
and the indicator sub-scores behind the entry decision.

All nullable/additive — trades booked before this migration keep NULLs and
diagnostics report those sections with reduced coverage.

Revision ID: 0006_diagnostics_v2
Revises: 0005_trade_diagnostics
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_diagnostics_v2"
down_revision: Union[str, None] = "0005_trade_diagnostics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # trades — per-trade execution detail written at close
    op.add_column("trades", sa.Column("entry_ts",            sa.Float(),        nullable=True))
    op.add_column("trades", sa.Column("planned_stop_loss",   sa.Numeric(20, 8), nullable=True))
    op.add_column("trades", sa.Column("planned_take_profit", sa.Numeric(20, 8), nullable=True))
    op.add_column("trades", sa.Column("mae_pct",             sa.Numeric(12, 4), nullable=True))
    op.add_column("trades", sa.Column("mfe_pct",             sa.Numeric(12, 4), nullable=True))
    op.add_column("trades", sa.Column("fee_usdt",            sa.Numeric(18, 6), nullable=True))
    op.add_column("trades", sa.Column("slippage_usdt",       sa.Numeric(18, 6), nullable=True))
    op.add_column("trades", sa.Column("scores",              sa.JSON(),         nullable=True))

    # positions — live watermarks + immutable planned stops + entry costs so
    # everything above survives a restart while the position is open
    op.add_column("positions", sa.Column("high_water",          sa.Numeric(20, 8), nullable=True))
    op.add_column("positions", sa.Column("low_water",           sa.Numeric(20, 8), nullable=True))
    op.add_column("positions", sa.Column("planned_stop_loss",   sa.Numeric(20, 8), nullable=True))
    op.add_column("positions", sa.Column("planned_take_profit", sa.Numeric(20, 8), nullable=True))
    op.add_column("positions", sa.Column("entry_fee_usdt",      sa.Numeric(18, 6), nullable=True))
    op.add_column("positions", sa.Column("entry_slippage_usdt", sa.Numeric(18, 6), nullable=True))
    op.add_column("positions", sa.Column("scores",              sa.JSON(),         nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "scores")
    op.drop_column("positions", "entry_slippage_usdt")
    op.drop_column("positions", "entry_fee_usdt")
    op.drop_column("positions", "planned_take_profit")
    op.drop_column("positions", "planned_stop_loss")
    op.drop_column("positions", "low_water")
    op.drop_column("positions", "high_water")

    op.drop_column("trades", "scores")
    op.drop_column("trades", "slippage_usdt")
    op.drop_column("trades", "fee_usdt")
    op.drop_column("trades", "mfe_pct")
    op.drop_column("trades", "mae_pct")
    op.drop_column("trades", "planned_take_profit")
    op.drop_column("trades", "planned_stop_loss")
    op.drop_column("trades", "entry_ts")
