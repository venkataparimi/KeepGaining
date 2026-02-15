from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.historical_data_service import HistoricalDataService

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_historical_data(
    symbol: str = Query(..., description="Instrument symbol (e.g., RELIANCE, NIFTY)"),
    instrument_type: Optional[str] = Query(None, description="Instrument type (EQUITY, OPTION, FUTURE, INDEX)"),
    time_frame: str = Query("1m", description="Time frame (1m, 3m, 5m, 15m, 30m, 1h, 1d)"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    indicators: Optional[List[str]] = Query(None, description="List of indicators to calculate (sma, ema, rsi, etc.)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch historical candle data with optional indicators.
    """
    service = HistoricalDataService(db)
    
    # Map API instrument types to DB instrument types
    if instrument_type == 'FUTURE':
        instrument_type = 'FUTURES'
    elif instrument_type == 'OPTION':
        # Options are CE or PE in DB, so we can't filter strictly by 'OPTION'
        # unless we change service to handle list. For now, let's ignore type for options
        # and rely on symbol uniqueness, or just don't filter.
        instrument_type = None 
    
    # Default date range if not provided (last 1 day)
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=1)
        
    try:
        data = await service.get_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            time_frame=time_frame,
            instrument_type=instrument_type,
            indicators=indicators
        )
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
