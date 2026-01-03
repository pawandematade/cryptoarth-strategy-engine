"""
Legacy Trading Models (Phase-2 Migration)
SQLAlchemy models converted from legacy_digno/authenticate/models.py

These models support:
- Broker connections (BrokerModels)
- Positions (Position)
- Orders (OrderDetails)
- Copy Trading (copysignal)
- Strategy Portfolio (userStratergyPortfolio, highLowstratergy)
- Symbols (SymbolMaster)

NOTE: These models use the existing database schema from Django.
Field names and types match the original Django models exactly.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, DECIMAL, UniqueConstraint, Table
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from common.db import Base


# Association table for highLowstratergy.allowed_users (ManyToMany)
# Django table name: authenticate_highlowstratergy_allowed_users
authenticate_highlowstratergy_allowed_users = Table(
    'authenticate_highlowstratergy_allowed_users',
    Base.metadata,
    Column('highlowstratergy_id', Integer, ForeignKey('authenticate_highlowstratergy.id', ondelete='CASCADE'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
)


class SymbolMaster(Base):
    """
    Symbol master data (trading symbols metadata)
    Converted from legacy_digno/authenticate/models.py SymbolMaster
    """
    __tablename__ = "authenticate_symbolmaster"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    symbolid = Column(Integer, nullable=False)
    precision = Column(Integer, nullable=True)
    minimum_qty = Column(Integer, default=1, nullable=False)
    Type = Column(String(50), nullable=False)
    contract_value = Column(DECIMAL(20, 10), nullable=True)

    # Relationships

    def __repr__(self):
        return f"<SymbolMaster(id={self.id}, symbol={self.symbol}, symbolid={self.symbolid})>"


class Watchlist(Base):
    """
    User watchlist model (user's saved trading symbols)
    Converted from legacy_digno/authenticate/models.py Watchlist
    """
    __tablename__ = "authenticate_watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol_id = Column(Integer, ForeignKey("authenticate_symbolmaster.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="watchlists")
    symbol = relationship("SymbolMaster", back_populates="watchlists")

    # Unique constraint: user + symbol combination
    __table_args__ = (
        UniqueConstraint('user_id', 'symbol_id', name='unique_user_symbol_watchlist'),
    )

    def __repr__(self):
        return f"<Watchlist(id={self.id}, user_id={self.user_id}, symbol_id={self.symbol_id})>"


class BrokerModels(Base):
    """
    Broker connection models (stores encrypted API credentials)
    Converted from legacy_digno/authenticate/models.py BrokerModels
    """
    __tablename__ = "authenticate_brokermodels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker = Column(String(100), default="DeltaExchange", nullable=False)
    name = Column(String(100), nullable=True)
    api_key = Column(String(255), nullable=True)
    api_secret = Column(String(255), nullable=True)
    status = Column(Boolean, default=True, nullable=False)
    coindcx_id = Column(String(255), nullable=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="brokers")
    user_strategies = relationship("userStratergyPortfolio", back_populates="broker")
    broker_positions = relationship("Position", back_populates="broker")
    broker_trades = relationship("tradeDetails", back_populates="broker")
    broker_orders = relationship("OrderDetails", back_populates="broker")

    def __repr__(self):
        return f"<BrokerModels(id={self.id}, broker={self.broker}, name={self.name})>"


class highLowstratergy(Base):
    """
    Strategy model (legacy spelling preserved)
    Converted from legacy_digno/authenticate/models.py highLowstratergy
    """
    __tablename__ = "authenticate_highlowstratergy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner = Column(String(25), default="TRADEARTH", nullable=False)
    stratergy_code = Column(String(55), default="NA", nullable=False)
    name = Column(String(25), default="NA", nullable=False)
    full_name = Column(String(25), default="NA", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    stratergy_description = Column(String(500), default="NA", nullable=False)
    tag = Column(Text, nullable=True)  # JSONField in Django -> Text in SQLAlchemy (stores JSON as string)
    captial_requirement = Column(Text, default="NA", nullable=False)
    entry_time = Column(Text, default="NA", nullable=False)
    exit_time = Column(Text, default="NA", nullable=False)
    created_date = Column(Date, nullable=False)  # Application code must set date when creating records
    target = Column(Text, default="NA", nullable=False)
    sl = Column(Text, default="NA", nullable=False)
    risk = Column(String(25), default="Low", nullable=False)
    overallReturn = Column(DECIMAL(13, 3), default=0, nullable=False)
    strategy_allow = Column(String(25), default="All", nullable=False)
    symbol = Column(String(25), nullable=True)
    trading_type = Column(String(25), default="Automatic", nullable=False)

    # ManyToMany relationship
    allowed_users = relationship(
        "User",
        secondary="authenticate_highlowstratergy_allowed_users",
        back_populates="allowed_strategies"
    )

    # Relationships
    user_strategies = relationship("userStratergyPortfolio", back_populates="stratergy")
    signals = relationship("copysignal", back_populates="strategy")
    signal_masters = relationship("SignalMaster", back_populates="stratergy")

    def __repr__(self):
        return f"<highLowstratergy(id={self.id}, stratergy_code={self.stratergy_code}, name={self.name})>"


class userStratergyPortfolio(Base):
    """
    User strategy portfolio (user strategy deployments)
    Converted from legacy_digno/authenticate/models.py userStratergyPortfolio
    """
    __tablename__ = "authenticate_userstratergyportfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stratergy_id = Column(Integer, ForeignKey("authenticate_highlowstratergy.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, default=False, nullable=False)
    date = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    broker_id = Column(Integer, ForeignKey("authenticate_brokermodels.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    owner = relationship("User", back_populates="strategy_portfolios")
    stratergy = relationship("highLowstratergy", back_populates="user_strategies")
    broker = relationship("BrokerModels", back_populates="user_strategies")

    def __repr__(self):
        return f"<userStratergyPortfolio(id={self.id}, owner_id={self.owner_id}, stratergy_id={self.stratergy_id})>"


class Position(Base):
    """
    Position model (user trading positions)
    Converted from legacy_digno/authenticate/models.py Position
    """
    __tablename__ = "authenticate_position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(255), default="NA", nullable=False)
    symbol = Column(String(255), default="NA", nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    side = Column(String(255), default="NA", nullable=False)
    price = Column(DECIMAL(13, 3), default=0, nullable=False)
    quantity = Column(DECIMAL(13, 7), default=0, nullable=False)
    unique = Column(String(50), default="NA", nullable=False)
    leverage = Column(Integer, default=0, nullable=False)
    stratergy = Column(String(15), default="NA", nullable=False)
    date = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    stratergy_name = Column(String(25), default="NA", nullable=False)
    broker_id = Column(Integer, ForeignKey("authenticate_brokermodels.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    owner = relationship("User", back_populates="positions")
    broker = relationship("BrokerModels", back_populates="broker_positions")

    def __repr__(self):
        return f"<Position(id={self.id}, symbol={self.symbol}, side={self.side}, quantity={self.quantity})>"


class OrderDetails(Base):
    """
    Order details model (order history)
    Converted from legacy_digno/authenticate/models.py OrderDetails
    """
    __tablename__ = "authenticate_orderdetails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(35), default="NA", nullable=False)
    stratergy = Column(String(15), default="NA", nullable=False)
    buyprice = Column(DECIMAL(13, 3), default=0, nullable=False)
    sellprice = Column(DECIMAL(13, 3), default=0, nullable=False)
    buyquantity = Column(DECIMAL(13, 3), default=0, nullable=False)
    sellquantity = Column(DECIMAL(13, 3), default=0, nullable=False)
    side = Column(String(15), default="NA", nullable=False)
    orderid = Column(String(15), default="NA", nullable=False)
    date = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    status = Column(String(15), default="NA", nullable=False)
    profit = Column(DECIMAL(13, 3), default=0, nullable=False)
    stratergy_name = Column(String(25), default="NA", nullable=False)
    broker_id = Column(Integer, ForeignKey("authenticate_brokermodels.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    owner = relationship("User", back_populates="orders")
    broker = relationship("BrokerModels", back_populates="broker_orders")

    def __repr__(self):
        return f"<OrderDetails(id={self.id}, symbol={self.symbol}, orderid={self.orderid}, profit={self.profit})>"


class copysignal(Base):
    """
    Copy trading signal model
    Converted from legacy_digno/authenticate/models.py copysignal
    """
    __tablename__ = "authenticate_copysignal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(25), default="NA", nullable=False)
    symbolid = Column(Integer, default=0, nullable=False)
    side = Column(String(15), default="NA", nullable=False)
    target = Column(DECIMAL(13, 3), default=0, nullable=False)
    stoploss = Column(DECIMAL(13, 3), default=0, nullable=False)
    entry = Column(DECIMAL(13, 3), default=0, nullable=False)
    typeq = Column(String(15), default="NA", nullable=False)
    leverage = Column(Integer, default=0, nullable=False)
    capital = Column(DECIMAL(13, 2), default=0, nullable=False)
    strategy_id = Column(Integer, ForeignKey("authenticate_highlowstratergy.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    url = Column(String(105), default="NA", nullable=False)
    status = Column(String(45), default="NA", nullable=False)
    trailingpoints = Column(Integer, default=0, nullable=False)
    trailingprice = Column(DECIMAL(13, 3), default=0, nullable=False)
    is_trailing = Column(Boolean, default=False, nullable=False)

    # Relationships
    owner = relationship("User", back_populates="copysignals")
    strategy = relationship("highLowstratergy", back_populates="signals")

    def __repr__(self):
        return f"<copysignal(id={self.id}, symbol={self.symbol}, status={self.status})>"


# Additional models referenced but not in the 7 required (for completeness):
class tradeDetails(Base):
    """
    Trade details model (referenced by relationships)
    Converted from legacy_digno/authenticate/models.py tradeDetails
    """
    __tablename__ = "authenticate_tradedetails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(35), default="NA", nullable=False)
    price = Column(DECIMAL(13, 3), default=0, nullable=False)
    quantity = Column(DECIMAL(13, 3), default=0, nullable=False)
    side = Column(String(15), default="NA", nullable=False)
    unique = Column(String(50), default="NA", nullable=False)
    date = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    status = Column(String(15), default="NA", nullable=False)
    orderid = Column(String(35), default="NA", nullable=False)
    stratergy = Column(String(15), default="NA", nullable=False)
    margin = Column(DECIMAL(13, 3), default=0, nullable=False)
    remark = Column(String(85), default="NA", nullable=False)
    stratergy_name = Column(String(25), default="NA", nullable=False)
    broker_id = Column(Integer, ForeignKey("authenticate_brokermodels.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    owner = relationship("User", back_populates="trades")
    broker = relationship("BrokerModels", back_populates="broker_trades")

    def __repr__(self):
        return f"<tradeDetails(id={self.id}, symbol={self.symbol}, orderid={self.orderid})>"


class SignalMaster(Base):
    """
    Signal master model (referenced by relationships)
    Converted from legacy_digno/authenticate/models.py SignalMaster
    """
    __tablename__ = "authenticate_signalmaster"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stratergy_id = Column(Integer, ForeignKey("authenticate_highlowstratergy.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(25), default="NA", nullable=False)
    side = Column(String(25), default="NA", nullable=False)
    unique = Column(Integer, default=0, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    status = Column(String(25), default="NA", nullable=False)
    entry = Column(DECIMAL(13, 2), default=0, nullable=False)
    target = Column(DECIMAL(13, 2), default=0, nullable=False)
    stoploss = Column(DECIMAL(13, 2), default=0, nullable=False)
    leverage = Column(Integer, default=0, nullable=False)
    capital = Column(DECIMAL(13, 2), default=0, nullable=False)
    type = Column(String(25), default="NA", nullable=False)

    # Relationships
    stratergy = relationship("highLowstratergy", back_populates="signal_masters")

    def __repr__(self):
        return f"<SignalMaster(id={self.id}, symbol={self.symbol}, status={self.status})>"


class adminPosition(Base):
    """
    Admin position model (strategy admin positions)
    Converted from legacy_digno/authenticate/models.py adminPosition
    """
    __tablename__ = "authenticate_adminposition"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(255), default="NA", nullable=False)
    symbol = Column(String(255), default="NA", nullable=False)
    strategy_id = Column(Integer, ForeignKey("authenticate_highlowstratergy.id", ondelete="CASCADE"), nullable=False, index=True)
    side = Column(String(255), default="NA", nullable=False)
    leverage = Column(Integer, default=0, nullable=False)
    capital = Column(DECIMAL(13, 7), default=0, nullable=False)

    # Relationships
    strategy = relationship("highLowstratergy")

    def __repr__(self):
        return f"<adminPosition(id={self.id}, symbol={self.symbol}, strategy_id={self.strategy_id})>"


class customer_failorder(Base):
    """
    Customer failed order model (order failures)
    Converted from legacy_digno/authenticate/models.py customer_failorder
    """
    __tablename__ = "authenticate_customer_failorder"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    orderid = Column(String(35), default="NA", nullable=False)
    strategy = Column(String(35), default="NA", nullable=False)
    remarks = Column(String(105), default="NA", nullable=False)
    date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    owner = relationship("User", back_populates="failure_orders")

    def __repr__(self):
        return f"<customer_failorder(id={self.id}, owner_id={self.owner_id}, orderid={self.orderid})>"


class latencycheck(Base):
    """
    Latency check model (performance tracking)
    Converted from legacy_digno/authenticate/models.py latencycheck
    """
    __tablename__ = "authenticate_latencycheck"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    symbol = Column(String(45), default="NA", nullable=False)
    strategy_id = Column(Integer, ForeignKey("authenticate_highlowstratergy.id", ondelete="CASCADE"), nullable=False, index=True)
    time_start = Column(DateTime(timezone=True), nullable=False)
    time_end = Column(DateTime(timezone=True), nullable=False)
    time_taken = Column(Integer, default=0, nullable=False)
    user_count = Column(Integer, default=0, nullable=False)
    side = Column(String(45), default="NA", nullable=False)
    type = Column(String(45), default="NA", nullable=False)

    # Relationships
    strategy = relationship("highLowstratergy")

    def __repr__(self):
        return f"<latencycheck(id={self.id}, symbol={self.symbol}, time_taken={self.time_taken}ms)>"

