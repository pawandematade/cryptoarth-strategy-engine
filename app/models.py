"""
SQLAlchemy Database Models

NOTE: TEMP strategies (TEMP-xxx) are stateless and never touch the database.
Only explicitly saved strategies are persisted.
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey, Enum, Text, BigInteger, DECIMAL, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class StrategyStatus(enum.Enum):
    """Strategy status enum"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ExecutionStatus(str, enum.Enum):
    """Execution status enum - values must match DB ENUM values (lowercase)"""
    inactive = "inactive"
    active = "active"
    paused = "paused"
    stopped = "stopped"
    running = "running"
    completed = "completed"


class ExecutionMode(str, enum.Enum):
    """Execution mode enum - values must match DB ENUM values (lowercase)"""
    template = "template"
    paper = "paper"
    live = "live"


class User(Base):
    """
    Local snapshot of user data from auth backend.
    Auth backend is the source of truth.
    
    NOTE: TEMP strategies (TEMP-xxx) are stateless and never touch the database.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_user_id = Column(Integer, unique=True, nullable=False, index=True, comment="User ID from auth backend")
    source = Column(String(50), default="auth_backend", nullable=False)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(20), nullable=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    broker = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_vendor = Column(Boolean, default=False, nullable=False)
    timezone = Column(String(50), default="Asia/Kolkata", nullable=False)
    country = Column(String(100), default="India", nullable=False)
    raw_user_json = Column(JSON, nullable=True, comment="Full user data snapshot from auth backend")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    user_credits = relationship("UserCredits", back_populates="user", uselist=False, cascade="all, delete-orphan")
    credit_transactions = relationship("CreditTransaction", back_populates="user", cascade="all, delete-orphan")
    strategy_usage = relationship("StrategyUsage", back_populates="user", cascade="all, delete-orphan")
    payment_transactions = relationship("PaymentTransaction", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, external_user_id={self.external_user_id}, email={self.email})>"


class Strategy(Base):
    """
    Saved strategies (NOT TEMP strategies).
    
    TEMP strategies (TEMP-xxx) are NOT stored in this table.
    Only explicitly saved strategies are persisted.
    """
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_code = Column(String(50), unique=True, nullable=False, index=True, comment="Generated unique code (e.g., STRG-XXXX)")
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(StrategyStatus), nullable=False, default=StrategyStatus.DRAFT, index=True)
    created_by = Column(String(20), nullable=False, default="manual", index=True, comment="Source: 'ai' or 'manual'")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="strategies")
    versions = relationship("StrategyVersion", back_populates="strategy", cascade="all, delete-orphan", order_by="StrategyVersion.version")

    def __repr__(self):
        # CRITICAL: status is stored as string, not Enum object
        # Do NOT call .value on status - it will crash if status is already a string
        return f"<Strategy(id={self.id}, strategy_code={self.strategy_code}, name={self.name}, status={self.status})>"


class StrategyVersion(Base):
    """
    Strategy versions.
    
    Each strategy edit creates a new version.
    Version numbers start from 1 and increment.
    """
    __tablename__ = "strategy_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    strategy_payload = Column(JSON, nullable=False, comment="Full strategy JSON payload")
    backtest_snapshot = Column(JSON, nullable=True, comment="Optional backtest snapshot JSON")
    created_by = Column(String(20), nullable=False, index=True, comment="Source: 'ai' for AI-generated, 'manual' for user-edited")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    strategy = relationship("Strategy", back_populates="versions")

    __table_args__ = (
        {"comment": "Strategy versions. Each edit creates a new version."}
    )

    def __repr__(self):
        return f"<StrategyVersion(id={self.id}, strategy_id={self.strategy_id}, version={self.version})>"


class StrategyExecution(Base):
    """
    Strategy execution records.
    
    Tracks strategy runs with execution mode (template/paper/live).
    Each execution represents one strategy run session.
    """
    __tablename__ = "strategy_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False, comment="Version number from strategy_versions")
    strategy_name = Column(String(255), nullable=False, comment="Strategy name snapshot")
    strategy_code = Column(String(50), nullable=False, index=True, comment="Strategy code snapshot")
    execution_mode = Column(
        Enum(ExecutionMode, native_enum=False),
        nullable=False,
        default=ExecutionMode.paper,
        index=True,
        comment="Execution mode: template, paper, or live"
    )
    run_source = Column(String(30), nullable=False, default='live', index=True, comment="Source: template, paper, live, ai_backtest, manual_backtest")
    status = Column(
        Enum(ExecutionStatus, native_enum=False),
        nullable=False,
        default=ExecutionStatus.running,
        index=True
    )
    trades = Column(Integer, nullable=False, default=0, comment="Total number of trades executed")
    pnl = Column(String(50), nullable=False, default="0.0", comment="Total PnL as string (supports large numbers)")
    activated_at = Column(DateTime(timezone=True), nullable=True, comment="UTC timestamp when activated")
    deactivated_at = Column(DateTime(timezone=True), nullable=True, comment="UTC timestamp when deactivated")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    strategy = relationship("Strategy", backref="executions")
    paper_trades = relationship("PaperTrade", back_populates="execution", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Strategy execution records. Tracks runs with execution mode."}
    )

    def __repr__(self):
        status_val = self.status.value if hasattr(self.status, 'value') else str(self.status)
        return f"<StrategyExecution(id={self.id}, strategy_id={self.strategy_id}, execution_mode={self.execution_mode.value if hasattr(self.execution_mode, 'value') else self.execution_mode}, status={status_val})>"


class PaperTrade(Base):
    """
    Paper trade records.
    
    Tracks virtual trades for paper trading mode.
    Each trade represents a BUY or SELL signal execution.
    """
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(Integer, ForeignKey("strategy_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, comment="Trading symbol (e.g., BTCUSD)")
    side = Column(String(10), nullable=False, comment="BUY or SELL")
    lot_size = Column(String(50), nullable=False, comment="Lot size as string (supports large numbers)")
    contract_value = Column(String(50), nullable=False, comment="Contract value as string")
    entry_price = Column(String(50), nullable=True, comment="Entry price as string")
    exit_price = Column(String(50), nullable=True, comment="Exit price as string (null for open positions)")
    leverage = Column(Integer, nullable=False, comment="Leverage used")
    usable_capital = Column(String(50), nullable=False, comment="Usable capital as string")
    margin_used = Column(String(50), nullable=False, comment="Margin used as string")
    pnl = Column(String(50), nullable=False, default="0.0", comment="Trade PnL as string")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    execution = relationship("StrategyExecution", back_populates="paper_trades")

    __table_args__ = (
        {"comment": "Paper trade records. Tracks virtual trades for paper trading."}
    )

    def __repr__(self):
        return f"<PaperTrade(id={self.id}, execution_id={self.execution_id}, symbol={self.symbol}, side={self.side}, pnl={self.pnl})>"


class CreditConfig(Base):
    """
    Global credit rules and costs for all actions.
    All credit costs are DB-driven (no hardcoding).
    """
    __tablename__ = "credit_config"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    action_key = Column(String(50), unique=True, nullable=False, index=True, comment="Action identifier (e.g., ai_strategy_generate)")
    credit_cost = Column(Integer, nullable=False, comment="Credit cost for this action")
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        {"comment": "Global credit rules and costs for all actions"}
    )

    def __repr__(self):
        return f"<CreditConfig(id={self.id}, action_key={self.action_key}, credit_cost={self.credit_cost}, is_active={self.is_active})>"


class UserCredits(Base):
    """
    User credit wallet - tracks total and used credits.
    One record per user.
    """
    __tablename__ = "user_credits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    total_credits = Column(Integer, default=0, nullable=False, comment="Total credits available")
    used_credits = Column(Integer, default=0, nullable=False, comment="Total credits used")
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="user_credits")

    __table_args__ = (
        {"comment": "User credit wallet - tracks total and used credits"}
    )

    @property
    def available_credits(self):
        """Calculate available credits"""
        return max(0, self.total_credits - self.used_credits)

    def __repr__(self):
        return f"<UserCredits(id={self.id}, user_id={self.user_id}, total={self.total_credits}, used={self.used_credits}, available={self.available_credits})>"


class CreditTransaction(Base):
    """
    Audit log for all credit transactions.
    Tracks all credit debits and credits.
    """
    __tablename__ = "credit_transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mobile = Column(String(20), nullable=False, index=True, comment="Mobile number in 91XXXXXXXXXX format")
    type = Column(Enum('debit', 'credit', name='credit_transaction_type'), nullable=False, index=True)
    credits = Column(Integer, nullable=False, comment="Credit amount")
    reason = Column(String(100), nullable=True, comment="Reason for transaction")
    reference_id = Column(String(100), nullable=True, index=True, comment="Reference ID (e.g., payment_id, strategy_code)")
    original_transaction_id = Column(BigInteger, ForeignKey("credit_transactions.id", ondelete="SET NULL"), nullable=True, index=True, comment="ID of original transaction if this is a correction")
    admin_name = Column(String(100), nullable=True, comment="Admin name who created this transaction (for corrections)")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="credit_transactions")
    original_transaction = relationship("CreditTransaction", remote_side=[id], backref="corrections")

    __table_args__ = (
        {"comment": "Audit log for all credit transactions"}
    )

    def __repr__(self):
        return f"<CreditTransaction(id={self.id}, user_id={self.user_id}, type={self.type}, credits={self.credits}, reason={self.reason})>"


class StrategyUsage(Base):
    """
    Tracks usage count per strategy per action (for free limits).
    Used to implement "first 3 backtests free" logic.
    """
    __tablename__ = "strategy_usage"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_code = Column(String(50), nullable=False, index=True, comment="Strategy code (e.g., STRG-XXXX)")
    action_key = Column(String(50), nullable=False, index=True, comment="Action identifier (e.g., backtest)")
    usage_count = Column(Integer, default=0, nullable=False, comment="Number of times this action was performed")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="strategy_usage")

    __table_args__ = (
        UniqueConstraint('user_id', 'strategy_code', 'action_key', name='unique_user_strategy_action'),
        {"comment": "Tracks usage count per strategy per action (for free limits)"}
    )

    def __repr__(self):
        return f"<StrategyUsage(id={self.id}, user_id={self.user_id}, strategy_code={self.strategy_code}, action_key={self.action_key}, usage_count={self.usage_count})>"


class PaymentTransaction(Base):
    """
    Payment transactions from Razorpay.
    Tracks all payment attempts and successes.
    """
    __tablename__ = "payment_transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(20), default='razorpay', nullable=False, comment="Payment provider")
    amount = Column(DECIMAL(10, 2), nullable=False, comment="Payment amount in INR")
    credits_added = Column(Integer, nullable=False, comment="Credits added to user wallet")
    status = Column(Enum('created', 'success', 'failed', name='payment_status'), default='created', nullable=False, index=True)
    gateway_order_id = Column(String(100), nullable=True, index=True, comment="Razorpay order ID")
    gateway_payment_id = Column(String(100), nullable=True, index=True, comment="Razorpay payment ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="payment_transactions")

    __table_args__ = (
        {"comment": "Payment transactions from Razorpay"}
    )

    def __repr__(self):
        return f"<PaymentTransaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, credits_added={self.credits_added}, status={self.status})>"
