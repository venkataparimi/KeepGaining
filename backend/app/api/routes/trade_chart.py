"""
Trade Chart API Routes
KeepGaining Trading Platform

Provides chart data with:
- OHLCV candle data
- Technical indicators
- Trade entry/exit markers
- Support/resistance levels
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel

from app.db.session import get_db

router = APIRouter()


class CandleData(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class TradeMarker(BaseModel):
    timestamp: str
    type: str  # "entry" or "exit"
    side: str  # "BUY" or "SELL"
    price: float
    quantity: int
    pnl: Optional[float] = None
    strategy: Optional[str] = None


class IndicatorData(BaseModel):
    name: str
    type: str  # "line", "histogram", "band"
    values: List[Dict[str, Any]]
    color: Optional[str] = None
    overlay: bool = True  # If True, plot on price chart


class ChartDataResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: List[CandleData]
    trades: List[TradeMarker]
    indicators: List[IndicatorData]


@router.get("/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    timeframe: str = Query("1D", description="Timeframe: 1m, 5m, 15m, 1H, 1D"),
    days: int = Query(90, description="Number of days of data"),
    indicators: str = Query("ema_21,ema_50,rsi_14", description="Comma-separated indicator list"),
    include_trades: bool = Query(True, description="Include trade markers"),
    db: Session = Depends(get_db)
) -> ChartDataResponse:
    """
    Get chart data for a symbol with indicators and trade markers.
    """
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Map timeframe to database interval
    timeframe_map = {
        "1m": "1 minute",
        "5m": "5 minutes",
        "15m": "15 minutes",
        "1H": "1 hour",
        "1D": "1 day",
    }
    
    db_interval = timeframe_map.get(timeframe, "1 day")
    
    # Get candle data from candle_data table
    candle_query = text("""
        SELECT 
            timestamp,
            open,
            high,
            low,
            close,
            volume
        FROM candle_data cd
        JOIN instruments i ON cd.instrument_id = i.id
        WHERE i.tradingsymbol = :symbol
        AND cd.timestamp >= :start_date
        AND cd.timestamp <= :end_date
        ORDER BY timestamp ASC
        LIMIT 5000
    """)
    
    result = db.execute(candle_query, {
        "symbol": symbol.upper(),
        "start_date": start_date,
        "end_date": end_date,
    })
    
    candles = []
    for row in result:
        candles.append(CandleData(
            timestamp=row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=int(row.volume),
        ))
    
    # If no candles from DB, return mock data for demo
    if not candles:
        candles = _generate_mock_candles(symbol, days, timeframe)
    
    # Get trade markers
    trades = []
    if include_trades:
        trades = await _get_trade_markers(db, symbol, start_date, end_date)
    
    # Get indicator data
    indicator_list = [ind.strip() for ind in indicators.split(",") if ind.strip()]
    indicator_data = _calculate_indicators(candles, indicator_list)
    
    return ChartDataResponse(
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=candles,
        trades=trades,
        indicators=indicator_data,
    )


async def _get_trade_markers(
    db: Session,
    symbol: str,
    start_date: datetime,
    end_date: datetime
) -> List[TradeMarker]:
    """Get trade entry/exit markers for a symbol."""
    
    # Query positions/trades for this symbol
    trade_query = text("""
        SELECT 
            p.opened_at as entry_time,
            p.closed_at as exit_time,
            p.side,
            p.entry_price,
            p.exit_price,
            p.quantity,
            p.realized_pnl,
            s.name as strategy_name
        FROM positions p
        LEFT JOIN strategies s ON p.strategy_id = s.id
        JOIN instruments i ON p.instrument_id = i.id
        WHERE i.tradingsymbol = :symbol
        AND (p.opened_at >= :start_date OR p.closed_at >= :start_date)
        AND (p.opened_at <= :end_date OR p.closed_at <= :end_date)
        ORDER BY p.opened_at ASC
    """)
    
    result = db.execute(trade_query, {
        "symbol": symbol.upper(),
        "start_date": start_date,
        "end_date": end_date,
    })
    
    markers = []
    for row in result:
        # Entry marker
        if row.opened_at:
            markers.append(TradeMarker(
                timestamp=row.opened_at.isoformat() if hasattr(row.opened_at, 'isoformat') else str(row.opened_at),
                type="entry",
                side=row.side or "BUY",
                price=float(row.entry_price or 0),
                quantity=int(row.quantity or 0),
                pnl=None,
                strategy=row.strategy_name,
            ))
        
        # Exit marker
        if row.closed_at and row.exit_price:
            markers.append(TradeMarker(
                timestamp=row.closed_at.isoformat() if hasattr(row.closed_at, 'isoformat') else str(row.closed_at),
                type="exit",
                side="SELL" if row.side == "BUY" else "BUY",
                price=float(row.exit_price),
                quantity=int(row.quantity or 0),
                pnl=float(row.realized_pnl or 0),
                strategy=row.strategy_name,
            ))
    
    return markers


def _calculate_indicators(
    candles: List[CandleData],
    indicator_list: List[str]
) -> List[IndicatorData]:
    """Calculate technical indicators from candle data."""
    if not candles:
        return []
    
    # Convert to lists for calculation
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]
    timestamps = [c.timestamp for c in candles]
    
    indicators = []
    
    for ind_name in indicator_list:
        ind_lower = ind_name.lower()
        
        # EMA indicators
        if ind_lower.startswith("ema_"):
            period = int(ind_lower.split("_")[1])
            ema_values = _calculate_ema(closes, period)
            
            color_map = {
                21: "#22c55e",  # Green
                50: "#3b82f6",  # Blue
                100: "#f59e0b",  # Orange
                200: "#ef4444",  # Red
            }
            
            indicators.append(IndicatorData(
                name=f"EMA {period}",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": ema_values[i]}
                    for i in range(len(ema_values)) if ema_values[i] is not None
                ],
                color=color_map.get(period, "#8b5cf6"),
                overlay=True,
            ))
        
        # SMA indicators
        elif ind_lower.startswith("sma_"):
            period = int(ind_lower.split("_")[1])
            sma_values = _calculate_sma(closes, period)
            
            indicators.append(IndicatorData(
                name=f"SMA {period}",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": sma_values[i]}
                    for i in range(len(sma_values)) if sma_values[i] is not None
                ],
                color="#6366f1",
                overlay=True,
            ))
        
        # RSI
        elif ind_lower.startswith("rsi"):
            period = 14
            if "_" in ind_lower:
                period = int(ind_lower.split("_")[1])
            
            rsi_values = _calculate_rsi(closes, period)
            
            indicators.append(IndicatorData(
                name=f"RSI {period}",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": rsi_values[i]}
                    for i in range(len(rsi_values)) if rsi_values[i] is not None
                ],
                color="#a855f7",
                overlay=False,  # Separate panel
            ))
        
        # VWAP
        elif ind_lower == "vwap":
            vwap_values = _calculate_vwap(closes, volumes, highs, lows)
            
            indicators.append(IndicatorData(
                name="VWAP",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": vwap_values[i]}
                    for i in range(len(vwap_values)) if vwap_values[i] is not None
                ],
                color="#06b6d4",
                overlay=True,
            ))
        
        # Bollinger Bands
        elif ind_lower.startswith("bb"):
            period = 20
            std_dev = 2.0
            
            bb = _calculate_bollinger_bands(closes, period, std_dev)
            
            # Upper band
            indicators.append(IndicatorData(
                name="BB Upper",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": bb["upper"][i]}
                    for i in range(len(bb["upper"])) if bb["upper"][i] is not None
                ],
                color="#94a3b8",
                overlay=True,
            ))
            
            # Middle (SMA)
            indicators.append(IndicatorData(
                name="BB Middle",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": bb["middle"][i]}
                    for i in range(len(bb["middle"])) if bb["middle"][i] is not None
                ],
                color="#64748b",
                overlay=True,
            ))
            
            # Lower band
            indicators.append(IndicatorData(
                name="BB Lower",
                type="line",
                values=[
                    {"timestamp": timestamps[i], "value": bb["lower"][i]}
                    for i in range(len(bb["lower"])) if bb["lower"][i] is not None
                ],
                color="#94a3b8",
                overlay=True,
            ))
        
        # Volume
        elif ind_lower == "volume":
            indicators.append(IndicatorData(
                name="Volume",
                type="histogram",
                values=[
                    {
                        "timestamp": timestamps[i],
                        "value": volumes[i],
                        "color": "#22c55e" if closes[i] >= (closes[i-1] if i > 0 else closes[i]) else "#ef4444"
                    }
                    for i in range(len(volumes))
                ],
                color="#64748b",
                overlay=False,
            ))
    
    return indicators


def _calculate_ema(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Exponential Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    
    multiplier = 2 / (period + 1)
    ema = [None] * (period - 1)
    
    # First EMA is SMA
    ema.append(sum(data[:period]) / period)
    
    for i in range(period, len(data)):
        ema.append((data[i] - ema[-1]) * multiplier + ema[-1])
    
    return ema


def _calculate_sma(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Simple Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    
    sma = [None] * (period - 1)
    
    for i in range(period - 1, len(data)):
        sma.append(sum(data[i - period + 1:i + 1]) / period)
    
    return sma


def _calculate_rsi(data: List[float], period: int = 14) -> List[Optional[float]]:
    """Calculate Relative Strength Index."""
    if len(data) < period + 1:
        return [None] * len(data)
    
    # Calculate price changes
    changes = [data[i] - data[i-1] for i in range(1, len(data))]
    
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]
    
    rsi = [None] * period
    
    # First RSI calculation
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rsi.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100 - (100 / (1 + rs)))
    
    # Subsequent RSI calculations
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
    
    return rsi


def _calculate_vwap(
    closes: List[float],
    volumes: List[int],
    highs: List[float],
    lows: List[float]
) -> List[Optional[float]]:
    """Calculate Volume Weighted Average Price."""
    if not closes or not volumes:
        return [None] * len(closes)
    
    typical_prices = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    
    cumulative_tpv = 0
    cumulative_volume = 0
    vwap = []
    
    for i in range(len(closes)):
        cumulative_tpv += typical_prices[i] * volumes[i]
        cumulative_volume += volumes[i]
        
        if cumulative_volume > 0:
            vwap.append(cumulative_tpv / cumulative_volume)
        else:
            vwap.append(None)
    
    return vwap


def _calculate_bollinger_bands(
    data: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, List[Optional[float]]]:
    """Calculate Bollinger Bands."""
    if len(data) < period:
        return {
            "upper": [None] * len(data),
            "middle": [None] * len(data),
            "lower": [None] * len(data),
        }
    
    middle = _calculate_sma(data, period)
    upper = [None] * len(data)
    lower = [None] * len(data)
    
    for i in range(period - 1, len(data)):
        window = data[i - period + 1:i + 1]
        std = (sum((x - middle[i]) ** 2 for x in window) / period) ** 0.5
        upper[i] = middle[i] + (std_dev * std)
        lower[i] = middle[i] - (std_dev * std)
    
    return {"upper": upper, "middle": middle, "lower": lower}


def _generate_mock_candles(symbol: str, days: int, timeframe: str) -> List[CandleData]:
    """Generate mock candle data for demo purposes."""
    import random
    
    candles = []
    base_price = 100.0 + random.random() * 900  # Random base between 100-1000
    
    # Determine number of candles based on timeframe
    candles_per_day = {
        "1m": 375,  # 6.25 hours * 60
        "5m": 75,
        "15m": 25,
        "1H": 7,
        "1D": 1,
    }
    
    total_candles = days * candles_per_day.get(timeframe, 1)
    total_candles = min(total_candles, 1000)  # Limit
    
    current_price = base_price
    current_time = datetime.now() - timedelta(days=days)
    
    time_delta = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1H": timedelta(hours=1),
        "1D": timedelta(days=1),
    }
    
    delta = time_delta.get(timeframe, timedelta(days=1))
    
    for _ in range(total_candles):
        # Random walk
        change = (random.random() - 0.5) * 0.02 * current_price
        
        open_price = current_price
        close_price = current_price + change
        high_price = max(open_price, close_price) + abs(change) * random.random()
        low_price = min(open_price, close_price) - abs(change) * random.random()
        volume = int(random.random() * 1000000 + 100000)
        
        candles.append(CandleData(
            timestamp=current_time.isoformat(),
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=volume,
        ))
        
        current_price = close_price
        current_time += delta
    
    return candles
