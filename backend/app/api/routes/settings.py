from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.db.session import get_db
from app.db.models.settings import SystemSettings, RiskSettings, NotificationSettings

router = APIRouter()


# ============ Pydantic Schemas ============

class RiskSettingsUpdate(BaseModel):
    max_capital_per_trade: Optional[float] = None
    max_capital_per_day: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_loss_per_trade: Optional[float] = None
    max_loss_per_day: Optional[float] = None
    max_drawdown_percent: Optional[float] = None
    default_position_size_percent: Optional[float] = None
    default_stop_loss_percent: Optional[float] = None
    default_take_profit_percent: Optional[float] = None
    allow_overnight_positions: Optional[bool] = None
    allow_options_trading: Optional[bool] = None
    allow_futures_trading: Optional[bool] = None


class NotificationSettingsUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    email_address: Optional[str] = None
    email_on_trade: Optional[bool] = None
    email_on_error: Optional[bool] = None
    email_daily_summary: Optional[bool] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    push_enabled: Optional[bool] = None


class SystemSettingUpdate(BaseModel):
    key: str
    value: str
    category: Optional[str] = "general"
    description: Optional[str] = None


# ============ Risk Settings ============

@router.get("/risk")
async def get_risk_settings(db: Session = Depends(get_db)):
    """Get current risk management settings"""
    settings = db.query(RiskSettings).first()
    
    if not settings:
        # Create default settings
        settings = RiskSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return {
        "max_capital_per_trade": settings.max_capital_per_trade,
        "max_capital_per_day": settings.max_capital_per_day,
        "max_open_positions": settings.max_open_positions,
        "max_loss_per_trade": settings.max_loss_per_trade,
        "max_loss_per_day": settings.max_loss_per_day,
        "max_drawdown_percent": settings.max_drawdown_percent,
        "default_position_size_percent": settings.default_position_size_percent,
        "default_stop_loss_percent": settings.default_stop_loss_percent,
        "default_take_profit_percent": settings.default_take_profit_percent,
        "allow_overnight_positions": settings.allow_overnight_positions,
        "allow_options_trading": settings.allow_options_trading,
        "allow_futures_trading": settings.allow_futures_trading,
        "updated_at": settings.updated_at
    }


@router.put("/risk")
async def update_risk_settings(
    update: RiskSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update risk management settings"""
    settings = db.query(RiskSettings).first()
    
    if not settings:
        settings = RiskSettings()
        db.add(settings)
    
    # Update only provided fields
    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, value)
    
    db.commit()
    db.refresh(settings)
    
    return {"message": "Risk settings updated", "settings": settings}


# ============ Notification Settings ============

@router.get("/notifications")
async def get_notification_settings(db: Session = Depends(get_db)):
    """Get notification settings"""
    settings = db.query(NotificationSettings).first()
    
    if not settings:
        settings = NotificationSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return {
        "email_enabled": settings.email_enabled,
        "email_address": settings.email_address,
        "email_on_trade": settings.email_on_trade,
        "email_on_error": settings.email_on_error,
        "email_daily_summary": settings.email_daily_summary,
        "webhook_enabled": settings.webhook_enabled,
        "webhook_url": settings.webhook_url,
        "push_enabled": settings.push_enabled,
        "updated_at": settings.updated_at
    }


@router.put("/notifications")
async def update_notification_settings(
    update: NotificationSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update notification settings"""
    settings = db.query(NotificationSettings).first()
    
    if not settings:
        settings = NotificationSettings()
        db.add(settings)
    
    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, value)
    
    db.commit()
    db.refresh(settings)
    
    return {"message": "Notification settings updated", "settings": settings}


# ============ System Settings (Key-Value) ============

@router.get("/system")
async def get_system_settings(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get system settings, optionally filtered by category"""
    query = db.query(SystemSettings)
    
    if category:
        query = query.filter(SystemSettings.category == category)
    
    settings = query.all()
    
    # Convert to dict
    result = {}
    for s in settings:
        if s.value_type == "number":
            result[s.key] = float(s.value) if s.value else 0
        elif s.value_type == "boolean":
            result[s.key] = s.value.lower() == "true" if s.value else False
        else:
            result[s.key] = s.value
    
    return result


@router.put("/system")
async def update_system_setting(
    setting: SystemSettingUpdate,
    db: Session = Depends(get_db)
):
    """Update or create a system setting"""
    existing = db.query(SystemSettings).filter(
        SystemSettings.key == setting.key
    ).first()
    
    if existing:
        existing.value = setting.value
        if setting.category:
            existing.category = setting.category
        if setting.description:
            existing.description = setting.description
    else:
        new_setting = SystemSettings(
            key=setting.key,
            value=setting.value,
            category=setting.category or "general",
            description=setting.description
        )
        db.add(new_setting)
    
    db.commit()
    
    return {"message": f"Setting '{setting.key}' updated"}


# ============ Get All Settings ============

@router.get("/all")
async def get_all_settings(db: Session = Depends(get_db)):
    """Get all settings in one call"""
    # Risk settings
    risk = db.query(RiskSettings).first()
    if not risk:
        risk = RiskSettings()
        db.add(risk)
    
    # Notification settings
    notif = db.query(NotificationSettings).first()
    if not notif:
        notif = NotificationSettings()
        db.add(notif)
    
    db.commit()
    
    return {
        "risk": {
            "max_capital_per_trade": risk.max_capital_per_trade,
            "max_capital_per_day": risk.max_capital_per_day,
            "max_open_positions": risk.max_open_positions,
            "max_loss_per_trade": risk.max_loss_per_trade,
            "max_loss_per_day": risk.max_loss_per_day,
            "max_drawdown_percent": risk.max_drawdown_percent,
            "default_position_size_percent": risk.default_position_size_percent,
            "default_stop_loss_percent": risk.default_stop_loss_percent,
            "default_take_profit_percent": risk.default_take_profit_percent,
            "allow_overnight_positions": risk.allow_overnight_positions,
            "allow_options_trading": risk.allow_options_trading,
            "allow_futures_trading": risk.allow_futures_trading,
        },
        "notifications": {
            "email_enabled": notif.email_enabled,
            "email_address": notif.email_address,
            "email_on_trade": notif.email_on_trade,
            "email_on_error": notif.email_on_error,
            "email_daily_summary": notif.email_daily_summary,
            "webhook_enabled": notif.webhook_enabled,
            "webhook_url": notif.webhook_url,
            "push_enabled": notif.push_enabled,
        }
    }
