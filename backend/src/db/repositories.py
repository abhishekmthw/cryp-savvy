"""
User-scoped query helpers. The single seam where every "find X for user Y"
query lives, so the multi-tenant invariant (data is filtered by user_id)
is enforced in one place.

Functions take an explicit ``Session`` rather than opening one — callers
control the transaction boundary via ``session_scope()``.
"""

from __future__ import annotations

import time
from typing import Iterable, Optional

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.db.models import Position, Trade, User, UserBotConfig, UserCredential
from src.security.crypto import CredentialVault


# ── Users ────────────────────────────────────────────────────────────────────

def get_user_or_create(
    db: Session,
    *,
    clerk_user_id: str,
    email: str | None,
    vault: CredentialVault,
) -> User:
    """
    Lazy upsert called by the auth dependency. If the user is new, generate a
    fresh wrapped DEK and a default UserBotConfig from settings.py.
    """
    user = db.get(User, clerk_user_id)
    if user is not None:
        # Update email if Clerk says it changed
        if email and user.email != email:
            user.email = email
        return user

    _, wrapped = vault.new_user_dek()
    user = User(
        clerk_user_id=clerk_user_id,
        email=email,
        bot_enabled=False,
        mode="paper",
        wrapped_dek=wrapped.wrapped_dek,
        dek_nonce=wrapped.dek_nonce,
        kek_version=wrapped.kek_version,
    )
    db.add(user)

    db.add(UserBotConfig(
        user_id=clerk_user_id,
        initial_capital_inr=settings.INITIAL_CAPITAL_INR,
        max_position_inr=settings.MAX_POSITION_INR,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
        stop_loss_pct=settings.STOP_LOSS_PCT,
        take_profit_pct=settings.TAKE_PROFIT_PCT,
        trailing_stop_trigger=settings.TRAILING_STOP_TRIGGER,
        trailing_stop_offset=settings.TRAILING_STOP_OFFSET,
        daily_loss_limit_inr=settings.DAILY_LOSS_LIMIT_INR,
    ))

    db.flush()
    return user


def list_users_with_bot_enabled(db: Session) -> list[User]:
    return list(db.execute(select(User).where(User.bot_enabled.is_(True))).scalars())


# ── Credentials ──────────────────────────────────────────────────────────────

def upsert_credential(
    db: Session,
    *,
    user_id: str,
    provider: str,
    ciphertext: bytes,
    nonce: bytes,
    last4: str,
    valid: bool,
    verified_at: Optional[float] = None,
) -> None:
    stmt = pg_insert(UserCredential).values(
        user_id=user_id,
        provider=provider,
        ciphertext=ciphertext,
        nonce=nonce,
        last4=last4,
        valid=valid,
        verified_at=__epoch_to_dt(verified_at) if verified_at else None,
    ).on_conflict_do_update(
        index_elements=[UserCredential.user_id, UserCredential.provider],
        set_={
            "ciphertext":  ciphertext,
            "nonce":       nonce,
            "last4":       last4,
            "valid":       valid,
            "verified_at": __epoch_to_dt(verified_at) if verified_at else None,
        },
    )
    db.execute(stmt)


def delete_credential(db: Session, *, user_id: str, provider: str) -> None:
    db.query(UserCredential).filter_by(user_id=user_id, provider=provider).delete()


def get_credentials(db: Session, user_id: str) -> list[UserCredential]:
    return list(db.execute(
        select(UserCredential).where(UserCredential.user_id == user_id)
    ).scalars())


def get_credential(db: Session, user_id: str, provider: str) -> UserCredential | None:
    return db.get(UserCredential, (user_id, provider))


# ── Trades ───────────────────────────────────────────────────────────────────

def record_trade(db: Session, *, user_id: str, trade: dict) -> None:
    db.add(Trade(
        user_id=user_id,
        order_id=trade.get("order_id"),
        symbol=trade.get("symbol"),
        side="sell",
        entry_price=trade.get("entry_price"),
        exit_price=trade.get("exit_price"),
        qty=trade.get("qty"),
        amount_inr=trade.get("amount_inr"),
        proceeds=trade.get("proceeds"),
        pnl=trade.get("pnl"),
        pnl_pct=trade.get("pnl_pct"),
        reason=trade.get("reason"),
        duration_s=trade.get("duration_s"),
        ts=time.time(),
    ))


def trades_for_user(db: Session, user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = db.execute(
        select(Trade)
        .where(Trade.user_id == user_id)
        .order_by(desc(Trade.ts))
        .limit(limit).offset(offset)
    ).scalars()
    return [{
        "symbol":      t.symbol,
        "side":        t.side,
        "entry_price": t.entry_price,
        "exit_price":  t.exit_price,
        "pnl":         t.pnl,
        "pnl_pct":     t.pnl_pct,
        "reason":      t.reason,
        "ts":          t.ts,
    } for t in rows]


def trade_stats(db: Session, user_id: str) -> dict:
    trades = list(db.execute(
        select(Trade.pnl, Trade.pnl_pct).where(Trade.user_id == user_id)
    ))
    total = len(trades)
    if total == 0:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "total_pnl": 0.0,
            "avg_pnl_pct": 0.0, "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
        }
    pnls = [(p or 0) for p, _ in trades]
    pcts = [(pp or 0) for _, pp in trades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    return {
        "total_trades":    total,
        "wins":            wins,
        "losses":          losses,
        "win_rate":        round(wins / total * 100, 1),
        "total_pnl":       round(sum(pnls), 2),
        "avg_pnl_pct":     round(sum(pcts) / total, 2),
        "best_trade_pct":  round(max(pcts), 2),
        "worst_trade_pct": round(min(pcts), 2),
    }


def pnl_history_for_user(db: Session, user_id: str, initial_capital: float) -> list[dict]:
    rows = list(db.execute(
        select(Trade.ts, Trade.pnl)
        .where(Trade.user_id == user_id)
        .order_by(Trade.ts.asc())
    ))
    running = float(initial_capital)
    history = [{"ts": rows[0][0] if rows else time.time(), "value": round(running, 2)}]
    for ts, pnl in rows:
        running += (pnl or 0)
        history.append({"ts": ts, "value": round(running, 2)})
    return history


# ── Positions (open) ─────────────────────────────────────────────────────────

def upsert_position(db: Session, user_id: str, p: dict) -> None:
    stmt = pg_insert(Position).values(user_id=user_id, **p).on_conflict_do_update(
        index_elements=[Position.user_id, Position.symbol],
        set_={k: v for k, v in p.items() if k != "symbol"},
    )
    db.execute(stmt)


def delete_position(db: Session, user_id: str, symbol: str) -> None:
    db.query(Position).filter_by(user_id=user_id, symbol=symbol).delete()


def positions_for_user(db: Session, user_id: str) -> list[Position]:
    return list(db.execute(
        select(Position).where(Position.user_id == user_id)
    ).scalars())


# ── Bot config ───────────────────────────────────────────────────────────────

def get_bot_config(db: Session, user_id: str) -> UserBotConfig | None:
    return db.get(UserBotConfig, user_id)


# ── Internal ─────────────────────────────────────────────────────────────────

def __epoch_to_dt(epoch: float):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc)
