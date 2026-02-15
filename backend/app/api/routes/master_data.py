from typing import List, Optional
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models.instrument import InstrumentMaster, OptionMaster, FutureMaster

router = APIRouter()

@router.get("/symbols", response_model=List[str])
async def get_symbols(
    instrument_type: str = Query(..., description="Instrument type (EQUITY, INDEX, FUTURE, OPTION)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of symbols. 
    For EQUITY/INDEX, returns the symbols themselves.
    For FUTURE/OPTION, returns the UNDERLYING symbols that have derivatives.
    """
    instrument_type = instrument_type.upper()
    
    if instrument_type in ['EQUITY', 'INDEX']:
        query = select(distinct(InstrumentMaster.trading_symbol)).where(
            InstrumentMaster.instrument_type == instrument_type
        ).order_by(InstrumentMaster.trading_symbol)
        
    elif instrument_type == 'OPTION':
        # Join OptionMaster with InstrumentMaster to get underlying symbol
        query = select(distinct(InstrumentMaster.trading_symbol)).join(
            OptionMaster, InstrumentMaster.instrument_id == OptionMaster.underlying_instrument_id
        ).order_by(InstrumentMaster.trading_symbol)
        
    elif instrument_type == 'FUTURE':
        # Join FutureMaster with InstrumentMaster to get underlying symbol
        query = select(distinct(InstrumentMaster.trading_symbol)).join(
            FutureMaster, InstrumentMaster.instrument_id == FutureMaster.underlying_instrument_id
        ).order_by(InstrumentMaster.trading_symbol)
        
    else:
        raise HTTPException(status_code=400, detail="Invalid instrument type")

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/expiries", response_model=List[date])
async def get_expiries(
    underlying: str = Query(..., description="Underlying symbol (e.g. NIFTY)"),
    instrument_type: str = Query(..., description="Instrument type (FUTURE, OPTION)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get distinct expiry dates for a given underlying and instrument type.
    """
    instrument_type = instrument_type.upper()
    
    # First get the underlying instrument ID
    underlying_query = select(InstrumentMaster.instrument_id).where(
        InstrumentMaster.trading_symbol == underlying
    )
    result = await db.execute(underlying_query)
    underlying_id = result.scalar_one_or_none()
    
    if not underlying_id:
        raise HTTPException(status_code=404, detail="Underlying instrument not found")
        
    if instrument_type == 'OPTION':
        query = select(distinct(OptionMaster.expiry_date)).where(
            OptionMaster.underlying_instrument_id == underlying_id
        ).order_by(OptionMaster.expiry_date)
        
    elif instrument_type == 'FUTURE':
        query = select(distinct(FutureMaster.expiry_date)).where(
            FutureMaster.underlying_instrument_id == underlying_id
        ).order_by(FutureMaster.expiry_date)
        
    else:
        raise HTTPException(status_code=400, detail="Invalid instrument type for expiries")

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/option-chain", response_model=List[dict])
async def get_option_chain(
    underlying: str = Query(..., description="Underlying symbol (e.g. NIFTY)"),
    expiry_date: date = Query(..., description="Expiry date"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get available options (Chain) for a specific underlying and expiry.
    Returns list of { strike, type, symbol }.
    """
    # First get the underlying instrument ID
    underlying_query = select(InstrumentMaster.instrument_id).where(
        InstrumentMaster.trading_symbol == underlying
    )
    result = await db.execute(underlying_query)
    underlying_id = result.scalar_one_or_none()
    
    if not underlying_id:
        raise HTTPException(status_code=404, detail="Underlying instrument not found")

    # Query OptionMaster joined with InstrumentMaster to get the option's trading symbol
    query = select(
        OptionMaster.strike_price,
        OptionMaster.option_type,
        InstrumentMaster.trading_symbol
    ).join(
        InstrumentMaster, OptionMaster.instrument_id == InstrumentMaster.instrument_id
    ).where(
        and_(
            OptionMaster.underlying_instrument_id == underlying_id,
            OptionMaster.expiry_date == expiry_date
        )
    ).order_by(OptionMaster.strike_price, OptionMaster.option_type)

    result = await db.execute(query)
    rows = result.all()
    
    def format_strike(price):
        f = float(price)
        if f.is_integer():
            return int(f)
        return f

    return [
        {
            "strike_price": format_strike(row.strike_price),
            "option_type": row.option_type,
            "symbol": row.trading_symbol
        }
        for row in rows
    ]


@router.get("/futures-contract")
async def get_futures_contract(
    underlying: str = Query(..., description="Underlying symbol (e.g., NIFTY 50)"),
    expiry_date: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the trading symbol for a Future contract given underlying and expiry.
    """
    try:
        # Cast expiry_date string to date object
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        
        # 1. Start with InstrumentMaster to find the Future via relationship or direct join
        # Since we just fixed linkage, we can join FutureMaster on underlying_instrument_id
        
        # Find underlying instrument ID first
        u_stmt = select(InstrumentMaster.instrument_id).where(InstrumentMaster.trading_symbol == underlying)
        underlying_id = await db.scalar(u_stmt)
        
        if not underlying_id:
             raise HTTPException(status_code=404, detail="Underlying instrument not found")

        # Find FutureMaster entry
        fm_stmt = select(InstrumentMaster.trading_symbol).join(
            FutureMaster, InstrumentMaster.instrument_id == FutureMaster.instrument_id
        ).where(
            FutureMaster.underlying_instrument_id == underlying_id,
            FutureMaster.expiry_date == expiry,
            InstrumentMaster.is_active == True
        )
        
        trading_symbol = await db.scalar(fm_stmt)
        
        if not trading_symbol:
            raise HTTPException(status_code=404, detail="Future contract not found")
            
        return {"trading_symbol": trading_symbol}

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        print(f"Error fetching future contract: {e}")
        raise HTTPException(status_code=500, detail=str(e))
