"""
SQLAlchemy ORM models for multi-tenant CrypSavvy.

PK convention: Clerk's `sub` claim (``user_xxx...``) is the canonical user ID
throughout. No internal numeric IDs are introduced.

Provider names used in ``UserCredential.provider``:
    'coindcx_key', 'coindcx_secret', 'telegram_bot_token', 'telegram_chat_id'
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
    LargeBinary, Numeric, String, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    clerk_user_id: Mapped[str] = mapped_column(String, primary_key=True)
    email:         Mapped[str | None] = mapped_column(String, nullable=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot_enabled:   Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mode:          Mapped[str]  = mapped_column(String, default="paper", nullable=False)  # 'paper' | 'live'

    # Wrapped DEK (envelope encryption outer layer)
    wrapped_dek:   Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dek_nonce:     Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kek_version:   Mapped[int]   = mapped_column(Integer, default=1, nullable=False)

    credentials: Mapped[list["UserCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    config:    Mapped["UserBotConfig | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False,
    )
    trades:    Mapped[list["Trade"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    positions: Mapped[list["Position"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )


class UserCredential(Base):
    __tablename__ = "user_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_credentials_user_provider"),
    )

    user_id:  Mapped[str] = mapped_column(
        ForeignKey("users.clerk_user_id", ondelete="CASCADE"), primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String, primary_key=True)

    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce:      Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    last4:       Mapped[str | None] = mapped_column(String(8), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid:       Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="credentials")


class UserBotConfig(Base):
    __tablename__ = "user_bot_config"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.clerk_user_id", ondelete="CASCADE"), primary_key=True,
    )

    initial_capital_inr:   Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    max_position_inr:      Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    max_open_positions:    Mapped[int]   = mapped_column(Integer, nullable=False)
    stop_loss_pct:         Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    take_profit_pct:       Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    trailing_stop_trigger: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    trailing_stop_offset:  Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    daily_loss_limit_inr:  Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    user: Mapped[User] = relationship(back_populates="config")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_user_ts", "user_id", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.clerk_user_id", ondelete="CASCADE"), nullable=False,
    )

    order_id:    Mapped[str | None] = mapped_column(String, nullable=True)
    symbol:      Mapped[str] = mapped_column(String, nullable=False)
    side:        Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price:  Mapped[float | None] = mapped_column(Float, nullable=True)
    qty:         Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_inr:  Mapped[float | None] = mapped_column(Float, nullable=True)
    proceeds:    Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl:         Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct:     Mapped[float | None] = mapped_column(Float, nullable=True)
    reason:      Mapped[str | None] = mapped_column(String, nullable=True)
    duration_s:  Mapped[float | None] = mapped_column(Float, nullable=True)
    ts:          Mapped[float] = mapped_column(Float, nullable=False)

    user: Mapped[User] = relationship(back_populates="trades")


class Position(Base):
    """
    Persists OPEN positions across bot restarts. Closed positions live in `trades`.
    """
    __tablename__ = "positions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.clerk_user_id", ondelete="CASCADE"), primary_key=True,
    )
    symbol:  Mapped[str] = mapped_column(String, primary_key=True)

    qty:           Mapped[float] = mapped_column(Float, nullable=False)
    entry_price:   Mapped[float] = mapped_column(Float, nullable=False)
    entry_time:    Mapped[float] = mapped_column(Float, nullable=False)
    amount_inr:    Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss:     Mapped[float] = mapped_column(Float, nullable=False)
    take_profit:   Mapped[float] = mapped_column(Float, nullable=False)
    trailing_high: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    order_id:      Mapped[str | None] = mapped_column(String, nullable=True)
    status:        Mapped[str] = mapped_column(String, default="open", nullable=False)  # 'pending'|'open'|'closing'

    user: Mapped[User] = relationship(back_populates="positions")
