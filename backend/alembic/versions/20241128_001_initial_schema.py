"""Initial schema - Complete HLD data model

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-11-28

Complete database schema based on HIGH_LEVEL_DESIGN.md including:
- Master tables (instruments, equities, futures, options, sectors, indices)
- Time-series tables (candles, indicators, option greeks, option chain)
- Broker integration tables (symbol mapping, config, rate limits)
- Calendar tables (expiry, holidays, lot sizes, F&O bans)
- Trading tables (strategies, orders, trades, positions)
- Audit tables (signal log, order log)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20241128_001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================================================
    # EXTENSION SETUP
    # ========================================================================
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')  # For text search
    
    # Note: TimescaleDB extension should be enabled at database level
    # op.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')

    # ========================================================================
    # 1. MASTER TABLES
    # ========================================================================
    
    # 1.1 Instrument Master
    op.create_table(
        'instrument_master',
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), primary_key=True, 
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('trading_symbol', sa.String(50), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False),  # NSE, BSE, NFO, BFO, MCX
        sa.Column('segment', sa.String(20), nullable=False),   # EQ, FO, CD, COM
        sa.Column('instrument_type', sa.String(20), nullable=False),  # EQUITY, INDEX, FUTURE, OPTION
        sa.Column('underlying', sa.String(50)),  # For derivatives
        sa.Column('isin', sa.String(12)),
        sa.Column('lot_size', sa.Integer, default=1),
        sa.Column('tick_size', sa.Numeric(10, 4), default=0.05),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.UniqueConstraint('trading_symbol', 'exchange', name='uq_instrument_symbol_exchange'),
        sa.Index('idx_instrument_type', 'instrument_type'),
        sa.Index('idx_instrument_underlying', 'underlying'),
        sa.Index('idx_instrument_active', 'is_active'),
    )
    
    # 1.2 Equity Master
    op.create_table(
        'equity_master',
        sa.Column('equity_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('company_name', sa.String(200), nullable=False),
        sa.Column('industry', sa.String(100)),
        sa.Column('sector', sa.String(100)),
        sa.Column('face_value', sa.Numeric(10, 2)),
        sa.Column('is_fno', sa.Boolean, default=False),
        sa.Column('fno_lot_size', sa.Integer),
        sa.Column('market_cap_category', sa.String(20)),  # LARGE, MID, SMALL
        sa.Column('listing_date', sa.Date),
        sa.Column('is_index_constituent', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.Index('idx_equity_fno', 'is_fno'),
        sa.Index('idx_equity_sector', 'sector'),
    )
    
    # 1.3 Future Master
    op.create_table(
        'future_master',
        sa.Column('future_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('underlying_instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id')),
        sa.Column('expiry_date', sa.Date, nullable=False),
        sa.Column('lot_size', sa.Integer, nullable=False),
        sa.Column('contract_type', sa.String(10)),  # CURRENT, NEXT, FAR
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_future_expiry', 'expiry_date'),
        sa.Index('idx_future_underlying', 'underlying_instrument_id'),
    )
    
    # 1.4 Option Master
    op.create_table(
        'option_master',
        sa.Column('option_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('underlying_instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id')),
        sa.Column('strike_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('option_type', sa.String(2), nullable=False),  # CE, PE
        sa.Column('expiry_date', sa.Date, nullable=False),
        sa.Column('expiry_type', sa.String(10)),  # WEEKLY, MONTHLY
        sa.Column('lot_size', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_option_strike', 'strike_price'),
        sa.Index('idx_option_expiry', 'expiry_date'),
        sa.Index('idx_option_type', 'option_type'),
        sa.Index('idx_option_underlying', 'underlying_instrument_id'),
        sa.Index('idx_option_composite', 'underlying_instrument_id', 'strike_price', 'option_type', 'expiry_date'),
    )
    
    # 1.5 Sector Master
    op.create_table(
        'sector_master',
        sa.Column('sector_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('sector_name', sa.String(100), unique=True, nullable=False),
        sa.Column('sector_code', sa.String(20), unique=True),
        sa.Column('description', sa.Text),
        sa.Column('parent_sector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sector_master.sector_id')),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # 1.6 Index Constituents
    op.create_table(
        'index_constituents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('index_instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('constituent_instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('weight', sa.Numeric(8, 4)),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date),  # NULL = current constituent
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_constituent_index', 'index_instrument_id'),
        sa.Index('idx_constituent_stock', 'constituent_instrument_id'),
        sa.Index('idx_constituent_effective', 'effective_date'),
    )

    # ========================================================================
    # 2. TIME-SERIES TABLES
    # ========================================================================
    
    # 2.1 Candle Data
    op.create_table(
        'candle_data',
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('timeframe', sa.String(5), nullable=False),  # 1m, 5m, 15m, 1h, 1d
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('open', sa.Numeric(12, 2), nullable=False),
        sa.Column('high', sa.Numeric(12, 2), nullable=False),
        sa.Column('low', sa.Numeric(12, 2), nullable=False),
        sa.Column('close', sa.Numeric(12, 2), nullable=False),
        sa.Column('volume', sa.BigInteger, nullable=False),
        sa.Column('oi', sa.BigInteger),  # Open Interest for derivatives
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint('instrument_id', 'timeframe', 'timestamp'),
        sa.Index('idx_candle_time', 'timestamp'),
        sa.Index('idx_candle_instrument_time', 'instrument_id', 'timestamp'),
    )
    
    # 2.2 Indicator Data
    op.create_table(
        'indicator_data',
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('timeframe', sa.String(5), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        
        # Moving Averages
        sa.Column('sma_9', sa.Numeric(12, 4)),
        sa.Column('sma_20', sa.Numeric(12, 4)),
        sa.Column('sma_50', sa.Numeric(12, 4)),
        sa.Column('sma_200', sa.Numeric(12, 4)),
        sa.Column('ema_9', sa.Numeric(12, 4)),
        sa.Column('ema_21', sa.Numeric(12, 4)),
        sa.Column('ema_50', sa.Numeric(12, 4)),
        sa.Column('ema_200', sa.Numeric(12, 4)),
        
        # Volume Weighted MAs
        sa.Column('vwap', sa.Numeric(12, 4)),
        sa.Column('vwma_20', sa.Numeric(12, 4)),
        sa.Column('vwma_22', sa.Numeric(12, 4)),  # Custom fast VWMA (Fibonacci-based)
        sa.Column('vwma_31', sa.Numeric(12, 4)),  # Custom slow VWMA (Fibonacci-based)
        
        # Momentum Indicators
        sa.Column('rsi_14', sa.Numeric(8, 4)),
        sa.Column('macd', sa.Numeric(12, 4)),
        sa.Column('macd_signal', sa.Numeric(12, 4)),
        sa.Column('macd_histogram', sa.Numeric(12, 4)),
        sa.Column('stoch_k', sa.Numeric(8, 4)),
        sa.Column('stoch_d', sa.Numeric(8, 4)),
        sa.Column('cci', sa.Numeric(12, 4)),
        sa.Column('williams_r', sa.Numeric(8, 4)),
        
        # Volatility
        sa.Column('atr_14', sa.Numeric(12, 4)),
        sa.Column('bb_upper', sa.Numeric(12, 4)),
        sa.Column('bb_middle', sa.Numeric(12, 4)),
        sa.Column('bb_lower', sa.Numeric(12, 4)),
        
        # Trend
        sa.Column('adx', sa.Numeric(8, 4)),
        sa.Column('plus_di', sa.Numeric(8, 4)),
        sa.Column('minus_di', sa.Numeric(8, 4)),
        sa.Column('supertrend', sa.Numeric(12, 4)),
        sa.Column('supertrend_direction', sa.SmallInteger),  # 1=up, -1=down
        
        # Pivot Points (Classic)
        sa.Column('pivot_point', sa.Numeric(12, 4)),
        sa.Column('pivot_r1', sa.Numeric(12, 4)),
        sa.Column('pivot_r2', sa.Numeric(12, 4)),
        sa.Column('pivot_r3', sa.Numeric(12, 4)),
        sa.Column('pivot_s1', sa.Numeric(12, 4)),
        sa.Column('pivot_s2', sa.Numeric(12, 4)),
        sa.Column('pivot_s3', sa.Numeric(12, 4)),
        
        # Camarilla Pivot Points
        sa.Column('cam_r4', sa.Numeric(12, 4)),
        sa.Column('cam_r3', sa.Numeric(12, 4)),
        sa.Column('cam_r2', sa.Numeric(12, 4)),
        sa.Column('cam_r1', sa.Numeric(12, 4)),
        sa.Column('cam_s1', sa.Numeric(12, 4)),
        sa.Column('cam_s2', sa.Numeric(12, 4)),
        sa.Column('cam_s3', sa.Numeric(12, 4)),
        sa.Column('cam_s4', sa.Numeric(12, 4)),
        
        # Volume Analysis
        sa.Column('obv', sa.BigInteger),
        sa.Column('volume_sma_20', sa.BigInteger),
        sa.Column('volume_ratio', sa.Numeric(8, 4)),  # current/avg volume
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint('instrument_id', 'timeframe', 'timestamp'),
        sa.Index('idx_indicator_time', 'timestamp'),
    )
    
    # 2.3 Option Greeks
    op.create_table(
        'option_greeks',
        sa.Column('option_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('option_master.option_id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('underlying_price', sa.Numeric(12, 2)),
        sa.Column('option_price', sa.Numeric(12, 2)),
        sa.Column('iv', sa.Numeric(8, 4)),  # Implied Volatility
        sa.Column('delta', sa.Numeric(8, 6)),
        sa.Column('gamma', sa.Numeric(8, 6)),
        sa.Column('theta', sa.Numeric(8, 6)),
        sa.Column('vega', sa.Numeric(8, 6)),
        sa.Column('rho', sa.Numeric(8, 6)),
        sa.Column('oi', sa.BigInteger),
        sa.Column('volume', sa.BigInteger),
        sa.Column('bid', sa.Numeric(12, 2)),
        sa.Column('ask', sa.Numeric(12, 2)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint('option_id', 'timestamp'),
        sa.Index('idx_greeks_time', 'timestamp'),
    )
    
    # 2.4 Option Chain Snapshot
    op.create_table(
        'option_chain_snapshot',
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('underlying_instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('expiry_date', sa.Date, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('underlying_price', sa.Numeric(12, 2)),
        sa.Column('chain_data', postgresql.JSONB),  # Full chain as JSON
        sa.Column('pcr_oi', sa.Numeric(8, 4)),  # Put-Call Ratio (OI)
        sa.Column('pcr_volume', sa.Numeric(8, 4)),  # Put-Call Ratio (Volume)
        sa.Column('max_pain', sa.Numeric(12, 2)),
        sa.Column('iv_skew', sa.Numeric(8, 4)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_chain_underlying', 'underlying_instrument_id'),
        sa.Index('idx_chain_expiry', 'expiry_date'),
        sa.Index('idx_chain_time', 'timestamp'),
    )

    # ========================================================================
    # 3. BROKER INTEGRATION TABLES
    # ========================================================================
    
    # 3.1 Broker Symbol Mapping
    op.create_table(
        'broker_symbol_mapping',
        sa.Column('mapping_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        sa.Column('broker_name', sa.String(20), nullable=False),  # FYERS, UPSTOX, ZERODHA
        sa.Column('broker_symbol', sa.String(100), nullable=False),
        sa.Column('broker_token', sa.String(50)),  # Broker-specific token/ID
        sa.Column('exchange_code', sa.String(10)),  # Broker's exchange code
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.UniqueConstraint('broker_name', 'broker_symbol', name='uq_broker_symbol'),
        sa.Index('idx_mapping_instrument', 'instrument_id'),
        sa.Index('idx_mapping_broker', 'broker_name'),
        sa.Index('idx_mapping_broker_token', 'broker_name', 'broker_token'),
    )
    
    # 3.2 Broker Config
    op.create_table(
        'broker_config',
        sa.Column('config_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('broker_name', sa.String(20), unique=True, nullable=False),
        sa.Column('display_name', sa.String(50)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_primary_data', sa.Boolean, default=False),  # Primary for market data
        sa.Column('is_primary_trading', sa.Boolean, default=False),  # Primary for trading
        
        # API Configuration
        sa.Column('api_key', sa.String(255)),
        sa.Column('api_secret', sa.String(255)),
        sa.Column('user_id', sa.String(50)),
        sa.Column('redirect_uri', sa.String(255)),
        sa.Column('totp_secret', sa.String(100)),  # For auto-login
        
        # Rate Limits
        sa.Column('rate_limit_per_second', sa.Integer, default=10),
        sa.Column('rate_limit_per_minute', sa.Integer, default=200),
        sa.Column('rate_limit_per_day', sa.Integer, default=10000),
        
        # Capabilities
        sa.Column('supports_websocket', sa.Boolean, default=True),
        sa.Column('supports_historical', sa.Boolean, default=True),
        sa.Column('supports_options', sa.Boolean, default=True),
        sa.Column('max_websocket_symbols', sa.Integer, default=100),
        
        # Connection Settings
        sa.Column('settings', postgresql.JSONB),  # Additional broker-specific settings
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # 3.3 Rate Limit Tracker
    op.create_table(
        'rate_limit_tracker',
        sa.Column('tracker_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('broker_name', sa.String(20), nullable=False),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_type', sa.String(10), nullable=False),  # SECOND, MINUTE, DAY
        sa.Column('request_count', sa.Integer, default=0),
        sa.Column('last_request_at', sa.DateTime(timezone=True)),
        
        sa.Index('idx_rate_broker_endpoint', 'broker_name', 'endpoint'),
        sa.Index('idx_rate_window', 'window_start'),
    )

    # ========================================================================
    # 4. CALENDAR TABLES
    # ========================================================================
    
    # 4.1 Expiry Calendar
    op.create_table(
        'expiry_calendar',
        sa.Column('expiry_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('underlying', sa.String(50), nullable=False),  # NIFTY, BANKNIFTY, RELIANCE
        sa.Column('expiry_date', sa.Date, nullable=False),
        sa.Column('expiry_type', sa.String(10), nullable=False),  # WEEKLY, MONTHLY
        sa.Column('segment', sa.String(10), nullable=False),  # NFO, BFO, MCX
        sa.Column('is_trading_day', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.UniqueConstraint('underlying', 'expiry_date', 'segment', name='uq_expiry'),
        sa.Index('idx_expiry_date', 'expiry_date'),
        sa.Index('idx_expiry_underlying', 'underlying'),
    )
    
    # 4.2 Holiday Calendar
    op.create_table(
        'holiday_calendar',
        sa.Column('holiday_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False),  # NSE, BSE, MCX
        sa.Column('holiday_name', sa.String(100)),
        sa.Column('holiday_type', sa.String(20)),  # FULL, MORNING, EVENING
        sa.Column('segments_affected', postgresql.ARRAY(sa.String)),  # ['EQ', 'FO', 'CD']
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.UniqueConstraint('date', 'exchange', name='uq_holiday'),
        sa.Index('idx_holiday_date', 'date'),
        sa.Index('idx_holiday_exchange', 'exchange'),
    )
    
    # 4.3 Lot Size History
    op.create_table(
        'lot_size_history',
        sa.Column('history_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('underlying', sa.String(50), nullable=False),
        sa.Column('lot_size', sa.Integer, nullable=False),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date),  # NULL = current lot size
        sa.Column('segment', sa.String(10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_lot_underlying', 'underlying'),
        sa.Index('idx_lot_effective', 'effective_date'),
    )
    
    # 4.4 F&O Ban List
    op.create_table(
        'fo_ban_list',
        sa.Column('ban_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('underlying', sa.String(50), nullable=False),
        sa.Column('ban_date', sa.Date, nullable=False),
        sa.Column('mwpl_percentage', sa.Numeric(6, 2)),  # Market-wide position limit %
        sa.Column('is_banned', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.UniqueConstraint('underlying', 'ban_date', name='uq_ban'),
        sa.Index('idx_ban_date', 'ban_date'),
        sa.Index('idx_ban_underlying', 'underlying'),
    )
    
    # 4.5 Master Data Refresh Log
    op.create_table(
        'master_data_refresh_log',
        sa.Column('log_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('data_type', sa.String(50), nullable=False),  # SYMBOL_MASTER, EXPIRY, HOLIDAY, LOT_SIZE
        sa.Column('source', sa.String(20), nullable=False),  # FYERS, UPSTOX, NSE
        sa.Column('status', sa.String(20), nullable=False),  # SUCCESS, FAILED, PARTIAL
        sa.Column('records_processed', sa.Integer, default=0),
        sa.Column('records_added', sa.Integer, default=0),
        sa.Column('records_updated', sa.Integer, default=0),
        sa.Column('error_message', sa.Text),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_refresh_type', 'data_type'),
        sa.Index('idx_refresh_status', 'status'),
        sa.Index('idx_refresh_time', 'started_at'),
    )

    # ========================================================================
    # 5. STRATEGY & TRADING TABLES
    # ========================================================================
    
    # 5.1 Strategy Config
    op.create_table(
        'strategy_config',
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_name', sa.String(100), unique=True, nullable=False),
        sa.Column('strategy_type', sa.String(50), nullable=False),  # INTRADAY, SWING, POSITIONAL
        sa.Column('description', sa.Text),
        sa.Column('version', sa.String(20), default='1.0.0'),
        
        # Trading Parameters
        sa.Column('instruments', postgresql.JSONB),  # List of allowed instruments
        sa.Column('timeframes', postgresql.JSONB),  # ['1m', '5m', '15m']
        sa.Column('entry_time_start', sa.Time),
        sa.Column('entry_time_end', sa.Time),
        sa.Column('exit_time', sa.Time),  # Force exit time
        
        # Risk Parameters
        sa.Column('max_positions', sa.Integer, default=5),
        sa.Column('position_size_type', sa.String(20), default='FIXED'),  # FIXED, PERCENT, RISK_BASED
        sa.Column('position_size_value', sa.Numeric(18, 4)),
        sa.Column('default_sl_percent', sa.Numeric(5, 2)),
        sa.Column('default_target_percent', sa.Numeric(5, 2)),
        sa.Column('max_loss_per_day', sa.Numeric(18, 2)),
        sa.Column('max_loss_per_trade', sa.Numeric(18, 2)),
        sa.Column('trailing_sl_enabled', sa.Boolean, default=False),
        sa.Column('trailing_sl_percent', sa.Numeric(5, 2)),
        
        # Execution Settings
        sa.Column('order_type', sa.String(20), default='MARKET'),  # MARKET, LIMIT
        sa.Column('product_type', sa.String(20), default='INTRADAY'),  # INTRADAY, DELIVERY, MARGIN
        
        # Status
        sa.Column('is_active', sa.Boolean, default=False),
        sa.Column('is_paper_trading', sa.Boolean, default=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.Index('idx_strategy_active', 'is_active'),
        sa.Index('idx_strategy_type', 'strategy_type'),
    )
    
    # 5.2 Strategy Definition (Logic/Conditions)
    op.create_table(
        'strategy_definition',
        sa.Column('definition_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('strategy_config.strategy_id'), nullable=False),
        sa.Column('version', sa.Integer, default=1, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        
        # Trading Parameters
        sa.Column('instrument_types', postgresql.JSONB),  # ["INDEX_OPTION", "STOCK_OPTION"]
        sa.Column('allowed_instruments', postgresql.JSONB),  # Specific instruments or "ALL"
        sa.Column('timeframes', postgresql.JSONB, nullable=False),  # ["5m", "15m"]
        sa.Column('trading_sessions', postgresql.JSONB),  # Market hour restrictions
        
        # Entry Conditions (structured JSON for UI editing)
        sa.Column('entry_conditions', postgresql.JSONB, nullable=False),
        sa.Column('entry_logic', sa.Text),  # Human-readable logic
        
        # Exit Conditions
        sa.Column('exit_conditions', postgresql.JSONB, nullable=False),
        sa.Column('exit_logic', sa.Text),
        
        # Risk Parameters (can override strategy_config)
        sa.Column('default_sl_percent', sa.Numeric(5, 2)),
        sa.Column('default_target_percent', sa.Numeric(5, 2)),
        sa.Column('max_positions', sa.Integer),
        sa.Column('position_size_type', sa.String(20)),  # FIXED, PERCENT_CAPITAL, RISK_BASED
        sa.Column('position_size_value', sa.Numeric(18, 4)),
        
        # Metadata
        sa.Column('tags', postgresql.JSONB),
        sa.Column('is_active', sa.Boolean, default=False),
        sa.Column('backtested', sa.Boolean, default=False),
        sa.Column('backtest_results', postgresql.JSONB),
        sa.Column('created_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.Index('idx_definition_strategy', 'strategy_id'),
        sa.Index('idx_definition_active', 'is_active'),
    )
    
    # 5.3 Orders
    op.create_table(
        'orders',
        sa.Column('order_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('strategy_config.strategy_id')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        
        # Order Details
        sa.Column('order_type', sa.String(20), nullable=False),  # MARKET, LIMIT, SL, SL-M
        sa.Column('side', sa.String(4), nullable=False),  # BUY, SELL
        sa.Column('product_type', sa.String(20), nullable=False),  # INTRADAY, DELIVERY, MARGIN
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('price', sa.Numeric(12, 2)),  # For limit orders
        sa.Column('trigger_price', sa.Numeric(12, 2)),  # For SL orders
        
        # Broker Details
        sa.Column('broker_name', sa.String(20)),
        sa.Column('broker_order_id', sa.String(50)),
        sa.Column('exchange_order_id', sa.String(50)),
        
        # Status
        sa.Column('status', sa.String(20), nullable=False, default='PENDING'),
        # PENDING, PLACED, OPEN, PARTIAL, FILLED, CANCELLED, REJECTED
        sa.Column('filled_quantity', sa.Integer, default=0),
        sa.Column('average_price', sa.Numeric(12, 2)),
        sa.Column('rejection_reason', sa.Text),
        
        # Timestamps
        sa.Column('placed_at', sa.DateTime(timezone=True)),
        sa.Column('filled_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.Index('idx_order_strategy', 'strategy_id'),
        sa.Index('idx_order_instrument', 'instrument_id'),
        sa.Index('idx_order_status', 'status'),
        sa.Index('idx_order_broker', 'broker_name', 'broker_order_id'),
        sa.Index('idx_order_created', 'created_at'),
    )
    
    # 5.4 Trades
    op.create_table(
        'trades',
        sa.Column('trade_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('order_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('orders.order_id'), nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('strategy_config.strategy_id')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        
        # Trade Details
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('price', sa.Numeric(12, 2), nullable=False),
        
        # Broker Details
        sa.Column('broker_name', sa.String(20)),
        sa.Column('broker_trade_id', sa.String(50)),
        sa.Column('exchange_trade_id', sa.String(50)),
        
        # Timestamps
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_trade_order', 'order_id'),
        sa.Index('idx_trade_strategy', 'strategy_id'),
        sa.Index('idx_trade_instrument', 'instrument_id'),
        sa.Index('idx_trade_executed', 'executed_at'),
    )
    
    # 5.5 Positions
    op.create_table(
        'positions',
        sa.Column('position_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('strategy_config.strategy_id')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        
        # Position Details
        sa.Column('side', sa.String(5), nullable=False),  # LONG, SHORT
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('average_entry_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('current_price', sa.Numeric(12, 2)),
        
        # Risk Management
        sa.Column('stop_loss', sa.Numeric(12, 2)),
        sa.Column('target', sa.Numeric(12, 2)),
        sa.Column('trailing_sl', sa.Numeric(12, 2)),
        
        # P&L
        sa.Column('unrealized_pnl', sa.Numeric(18, 2)),
        sa.Column('realized_pnl', sa.Numeric(18, 2), default=0),
        
        # Status
        sa.Column('status', sa.String(20), nullable=False, default='OPEN'),  # OPEN, CLOSED
        
        # Timestamps
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.Index('idx_position_strategy', 'strategy_id'),
        sa.Index('idx_position_instrument', 'instrument_id'),
        sa.Index('idx_position_status', 'status'),
        sa.Index('idx_position_opened', 'opened_at'),
    )

    # ========================================================================
    # 6. AUDIT & LOGGING TABLES
    # ========================================================================
    
    # 6.1 Signal Log
    op.create_table(
        'signal_log',
        sa.Column('signal_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('strategy_config.strategy_id')),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instrument_master.instrument_id'), nullable=False),
        
        # Signal Details
        sa.Column('signal_type', sa.String(20), nullable=False),  # ENTRY_LONG, ENTRY_SHORT, EXIT
        sa.Column('signal_strength', sa.Numeric(5, 2)),  # 0-100
        sa.Column('timeframe', sa.String(5)),
        sa.Column('conditions_met', postgresql.JSONB),  # Which conditions triggered
        sa.Column('indicator_values', postgresql.JSONB),  # Snapshot of indicator values
        
        # Market Context
        sa.Column('market_price', sa.Numeric(12, 2)),
        sa.Column('bid', sa.Numeric(12, 2)),
        sa.Column('ask', sa.Numeric(12, 2)),
        
        # Execution
        sa.Column('was_executed', sa.Boolean, default=False),
        sa.Column('execution_reason', sa.Text),  # Why it was/wasn't executed
        sa.Column('order_id', postgresql.UUID(as_uuid=True)),
        
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_signal_strategy', 'strategy_id'),
        sa.Index('idx_signal_instrument', 'instrument_id'),
        sa.Index('idx_signal_type', 'signal_type'),
        sa.Index('idx_signal_time', 'generated_at'),
    )
    
    # 6.2 Order Log (Audit Trail)
    op.create_table(
        'order_log',
        sa.Column('log_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('order_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('orders.order_id'), nullable=False),
        
        # State Change
        sa.Column('previous_status', sa.String(20)),
        sa.Column('new_status', sa.String(20), nullable=False),
        sa.Column('change_reason', sa.Text),
        
        # Broker Response
        sa.Column('broker_response', postgresql.JSONB),
        
        # Metadata
        sa.Column('changed_by', sa.String(50)),  # SYSTEM, BROKER, USER
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_orderlog_order', 'order_id'),
        sa.Index('idx_orderlog_time', 'created_at'),
    )
    
    # 6.3 System Event Log
    op.create_table(
        'system_event_log',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('event_type', sa.String(50), nullable=False),
        # STARTUP, SHUTDOWN, ERROR, WARNING, BROKER_CONNECT, BROKER_DISCONNECT, etc.
        sa.Column('event_source', sa.String(100)),  # Component that generated the event
        sa.Column('severity', sa.String(20), default='INFO'),  # DEBUG, INFO, WARNING, ERROR, CRITICAL
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('details', postgresql.JSONB),  # Additional structured data
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.Index('idx_event_type', 'event_type'),
        sa.Index('idx_event_severity', 'severity'),
        sa.Index('idx_event_time', 'created_at'),
    )

    # ========================================================================
    # 7. DAILY AGGREGATION TABLE (for performance tracking)
    # ========================================================================
    
    op.create_table(
        'daily_pnl',
        sa.Column('pnl_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('strategy_config.strategy_id')),
        
        # P&L Summary
        sa.Column('gross_pnl', sa.Numeric(18, 2), default=0),
        sa.Column('brokerage', sa.Numeric(18, 2), default=0),
        sa.Column('taxes', sa.Numeric(18, 2), default=0),
        sa.Column('net_pnl', sa.Numeric(18, 2), default=0),
        
        # Trade Statistics
        sa.Column('total_trades', sa.Integer, default=0),
        sa.Column('winning_trades', sa.Integer, default=0),
        sa.Column('losing_trades', sa.Integer, default=0),
        sa.Column('max_drawdown', sa.Numeric(18, 2)),
        sa.Column('max_profit', sa.Numeric(18, 2)),
        
        # Capital
        sa.Column('opening_capital', sa.Numeric(18, 2)),
        sa.Column('closing_capital', sa.Numeric(18, 2)),
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        sa.UniqueConstraint('date', 'strategy_id', name='uq_daily_pnl'),
        sa.Index('idx_pnl_date', 'date'),
        sa.Index('idx_pnl_strategy', 'strategy_id'),
    )


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('daily_pnl')
    op.drop_table('system_event_log')
    op.drop_table('order_log')
    op.drop_table('signal_log')
    op.drop_table('positions')
    op.drop_table('trades')
    op.drop_table('orders')
    op.drop_table('strategy_definition')
    op.drop_table('strategy_config')
    op.drop_table('master_data_refresh_log')
    op.drop_table('fo_ban_list')
    op.drop_table('lot_size_history')
    op.drop_table('holiday_calendar')
    op.drop_table('expiry_calendar')
    op.drop_table('rate_limit_tracker')
    op.drop_table('broker_config')
    op.drop_table('broker_symbol_mapping')
    op.drop_table('option_chain_snapshot')
    op.drop_table('option_greeks')
    op.drop_table('indicator_data')
    op.drop_table('candle_data')
    op.drop_table('index_constituents')
    op.drop_table('sector_master')
    op.drop_table('option_master')
    op.drop_table('future_master')
    op.drop_table('equity_master')
    op.drop_table('instrument_master')
    
    # Drop extensions
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
