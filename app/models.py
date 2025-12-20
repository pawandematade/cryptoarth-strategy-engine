"""
SQLAlchemy Database Models

NOTE: TEMP strategies (TEMP-xxx) are stateless and never touch the database.
Only explicitly saved strategies are persisted.
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey, Enum, Text
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


class ExecutionStatus(enum.Enum):
    """Execution status enum"""
    INACTIVE = "inactive"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="strategies")
    versions = relationship("StrategyVersion", back_populates="strategy", cascade="all, delete-orphan", order_by="StrategyVersion.version")

    def __repr__(self):
        return f"<Strategy(id={self.id}, strategy_code={self.strategy_code}, name={self.name}, status={self.status.value})>"


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
    Strategy execution activation records.
    
    Tracks which version of a strategy is currently active for execution.
    Only one ACTIVE execution per strategy_id is allowed.
    """
    __tablename__ = "strategy_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False, comment="Version number from strategy_versions")
    status = Column(Enum(ExecutionStatus), nullable=False, default=ExecutionStatus.INACTIVE, index=True)
    activated_at = Column(DateTime(timezone=True), nullable=True, comment="UTC timestamp when activated")
    deactivated_at = Column(DateTime(timezone=True), nullable=True, comment="UTC timestamp when deactivated")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    strategy = relationship("Strategy", backref="executions")

    __table_args__ = (
        {"comment": "Strategy execution activation. Only one ACTIVE execution per strategy_id allowed."}
    )

    def __repr__(self):
        return f"<StrategyExecution(id={self.id}, strategy_id={self.strategy_id}, strategy_version={self.strategy_version}, status={self.status.value})>"
