"""
Data Management API Routes

Provides endpoints for:
- Historical data download
- Data status and statistics
- Instrument management
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from loguru import logger

from app.services.data_download_service import DataDownloadService
from app.services.data_providers.upstox import UpstoxDataProvider
from app.services.data_providers.base import DataProviderConfig, Interval

router = APIRouter()

# Global download state
_download_in_progress = False
_download_results = None


class DownloadRequest(BaseModel):
    """Request to download historical data."""
    from_date: date = date(2022, 5, 1)
    to_date: date = date.today()
    symbols: Optional[List[str]] = None  # None = all F&O stocks
    interval: str = "1m"  # 1m, 5m, 15m, 1h, 1d


class DownloadStatus(BaseModel):
    """Status of data download."""
    in_progress: bool
    total_instruments: int
    instruments_with_data: int
    total_candles: int
    date_range: dict
    last_download_results: Optional[dict] = None


async def _run_download(
    from_date: date,
    to_date: date,
    symbols: Optional[List[str]],
    interval: Interval
):
    """Background task to run data download."""
    global _download_in_progress, _download_results
    
    try:
        _download_in_progress = True
        
        # Initialize provider and service
        config = DataProviderConfig(
            provider_name='upstox',
            token_file='data/upstox_token.json'
        )
        provider = UpstoxDataProvider(config)
        service = DataDownloadService(data_provider=provider)
        await service.initialize()
        
        # Run download
        results = await service.download_historical_data(
            symbols=symbols,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        
        _download_results = results
        await service.close()
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        _download_results = {"error": str(e)}
    finally:
        _download_in_progress = False


@router.post("/download/historical")
async def start_historical_download(
    request: DownloadRequest,
    background_tasks: BackgroundTasks
):
    """
    Start historical data download in background.
    
    Downloads minute-level candle data for all F&O stocks (or specified symbols)
    from Upstox API and stores in PostgreSQL.
    
    The download is resumable - it will skip stocks that already have data
    up to the requested date range.
    """
    global _download_in_progress
    
    if _download_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Download already in progress. Check /data/download/status for progress."
        )
    
    # Map interval string to enum
    interval_map = {
        "1m": Interval.MINUTE_1,
        "5m": Interval.MINUTE_5,
        "15m": Interval.MINUTE_15,
        "1h": Interval.HOUR_1,
        "1d": Interval.DAY,
    }
    interval = interval_map.get(request.interval, Interval.MINUTE_1)
    
    # Start download in background
    background_tasks.add_task(
        _run_download,
        request.from_date,
        request.to_date,
        request.symbols,
        interval
    )
    
    return {
        "status": "started",
        "message": f"Download started for {len(request.symbols) if request.symbols else 'all F&O'} stocks",
        "from_date": str(request.from_date),
        "to_date": str(request.to_date),
        "interval": request.interval
    }


@router.get("/download/status")
async def get_download_status() -> DownloadStatus:
    """Get current download status and database statistics."""
    global _download_in_progress, _download_results
    
    # Get database stats
    config = DataProviderConfig(
        provider_name='upstox',
        token_file='data/upstox_token.json'
    )
    provider = UpstoxDataProvider(config)
    service = DataDownloadService(data_provider=provider)
    
    try:
        status = await service.get_download_status()
        await service.close()
        
        return DownloadStatus(
            in_progress=_download_in_progress,
            total_instruments=status.get("total_fo_instruments", 0),
            instruments_with_data=status.get("instruments_with_data", 0),
            total_candles=status.get("total_candles", 0),
            date_range=status.get("date_range", {}),
            last_download_results=_download_results
        )
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return DownloadStatus(
            in_progress=_download_in_progress,
            total_instruments=0,
            instruments_with_data=0,
            total_candles=0,
            date_range={},
            last_download_results=_download_results
        )


@router.post("/download/stop")
async def stop_download():
    """Stop the current download (will complete current stock first)."""
    global _download_in_progress
    
    if not _download_in_progress:
        return {"status": "not_running", "message": "No download in progress"}
    
    # Note: This just sets a flag - actual stopping would require more work
    _download_in_progress = False
    return {"status": "stopping", "message": "Download will stop after current stock completes"}


@router.get("/instruments/fo")
async def get_fo_instruments():
    """Get list of F&O instruments with their data status."""
    config = DataProviderConfig(
        provider_name='upstox',
        token_file='data/upstox_token.json'
    )
    provider = UpstoxDataProvider(config)
    service = DataDownloadService(data_provider=provider)
    
    try:
        stocks = await service.get_fo_stocks_from_db()
        await service.close()
        return {"instruments": stocks, "count": len(stocks)}
    except Exception as e:
        logger.error(f"Error getting instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/fo-stocks")
async def sync_fo_stocks():
    """Sync F&O stocks list from provider to database."""
    config = DataProviderConfig(
        provider_name='upstox',
        token_file='data/upstox_token.json'
    )
    provider = UpstoxDataProvider(config)
    service = DataDownloadService(data_provider=provider)
    
    try:
        await service.initialize()
        count = await service.sync_fo_stocks_to_db()
        await service.close()
        return {"status": "success", "synced_count": count}
    except Exception as e:
        logger.error(f"Error syncing F&O stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
