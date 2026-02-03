from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models.trading_mode import TradingSession, TradingModeSwitch, TradingMode
from app.db.models.strategy import Strategy
from datetime import datetime

router = APIRouter()

class ModeSwitchRequest(BaseModel):
    strategy_id: int
    to_mode: TradingMode
    reason: Optional[str] = None

class SessionResponse(BaseModel):
    id: int
    strategy_id: int
    mode: TradingMode
    is_active: bool
    started_at: datetime
    initial_capital: float
    current_capital: float
    total_trades: int
    total_pnl: float
    
    class Config:
        from_attributes = True

@router.get("/mode/{strategy_id}")
async def get_current_mode(strategy_id: int, db: Session = Depends(get_db)):
    """Get current trading mode for a strategy"""
    # Get active session
    session = db.query(TradingSession).filter(
        TradingSession.strategy_id == strategy_id,
        TradingSession.is_active == True
    ).first()
    
    if not session:
        # Create default paper trading session
        session = TradingSession(
            strategy_id=strategy_id,
            mode=TradingMode.PAPER,
            is_active=True,
            started_by="system"
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    
    return {
        "strategy_id": strategy_id,
        "mode": session.mode,
        "session": SessionResponse.from_orm(session)
    }

@router.post("/switch")
async def switch_mode(request: ModeSwitchRequest, db: Session = Depends(get_db)):
    """Switch trading mode (paper <-> live)"""
    # Verify strategy exists
    strategy = db.query(Strategy).filter(Strategy.id == request.strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Get current active session
    current_session = db.query(TradingSession).filter(
        TradingSession.strategy_id == request.strategy_id,
        TradingSession.is_active == True
    ).first()
    
    current_mode = current_session.mode if current_session else TradingMode.PAPER
    
    # Check if already in requested mode
    if current_mode == request.to_mode:
        raise HTTPException(status_code=400, detail=f"Already in {request.to_mode} mode")
    
    # Switching to LIVE requires approval
    requires_approval = request.to_mode == TradingMode.LIVE
    
    # Create mode switch record
    mode_switch = TradingModeSwitch(
        strategy_id=request.strategy_id,
        from_mode=current_mode,
        to_mode=request.to_mode,
        switched_by="system",  # TODO: Get from auth context
        reason=request.reason,
        requires_approval=requires_approval,
        approved=not requires_approval  # Auto-approve paper mode
    )
    db.add(mode_switch)
    
    # If switching to paper (no approval needed) or approval not required
    if not requires_approval:
        # End current session
        if current_session:
            current_session.is_active = False
            current_session.ended_at = datetime.now()
        
        # Create new session
        new_session = TradingSession(
            strategy_id=request.strategy_id,
            mode=request.to_mode,
            is_active=True,
            started_by="system"
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        
        return {
            "success": True,
            "message": f"Switched to {request.to_mode} mode",
            "session": SessionResponse.from_orm(new_session)
        }
    else:
        db.commit()
        return {
            "success": False,
            "message": "Switch to LIVE mode requires approval",
            "requires_approval": True,
            "switch_id": mode_switch.id
        }

@router.post("/approve-switch/{switch_id}")
async def approve_mode_switch(switch_id: int, db: Session = Depends(get_db)):
    """Approve a mode switch to LIVE trading"""
    mode_switch = db.query(TradingModeSwitch).filter(
        TradingModeSwitch.id == switch_id
    ).first()
    
    if not mode_switch:
        raise HTTPException(status_code=404, detail="Mode switch not found")
    
    if mode_switch.approved:
        raise HTTPException(status_code=400, detail="Already approved")
    
    # Approve the switch
    mode_switch.approved = True
    mode_switch.approved_by = "system"  # TODO: Get from auth context
    mode_switch.approved_at = datetime.now()
    
    # End current session
    current_session = db.query(TradingSession).filter(
        TradingSession.strategy_id == mode_switch.strategy_id,
        TradingSession.is_active == True
    ).first()
    
    if current_session:
        current_session.is_active = False
        current_session.ended_at = datetime.now()
    
    # Create new LIVE session
    new_session = TradingSession(
        strategy_id=mode_switch.strategy_id,
        mode=mode_switch.to_mode,
        is_active=True,
        started_by=mode_switch.switched_by
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    return {
        "success": True,
        "message": "Switched to LIVE mode",
        "session": SessionResponse.from_orm(new_session)
    }

@router.get("/history/{strategy_id}")
async def get_mode_history(strategy_id: int, db: Session = Depends(get_db)):
    """Get mode switch history for a strategy"""
    switches = db.query(TradingModeSwitch).filter(
        TradingModeSwitch.strategy_id == strategy_id
    ).order_by(TradingModeSwitch.switched_at.desc()).all()
    
    return switches

@router.get("/sessions/{strategy_id}")
async def get_sessions(strategy_id: int, db: Session = Depends(get_db)):
    """Get all trading sessions for a strategy"""
    sessions = db.query(TradingSession).filter(
        TradingSession.strategy_id == strategy_id
    ).order_by(TradingSession.started_at.desc()).all()
    
    return [SessionResponse.from_orm(s) for s in sessions]
