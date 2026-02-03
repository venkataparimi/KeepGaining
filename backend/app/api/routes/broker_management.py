from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models.broker_config import BrokerConfig
from app.services.broker_health import BrokerHealthService

router = APIRouter()

class BrokerConfigCreate(BaseModel):
    broker_name: str
    api_key: str
    api_secret: str
    user_id: str
    is_primary: bool = False

@router.get("/brokers")
async def list_brokers(db: Session = Depends(get_db)):
    """List all configured brokers"""
    brokers = db.query(BrokerConfig).all()
    return brokers

@router.post("/brokers")
async def create_broker_config(
    config: BrokerConfigCreate,
    db: Session = Depends(get_db)
):
    """Create broker configuration"""
    # If setting as primary, unset other primaries
    if config.is_primary:
        db.query(BrokerConfig).update({"is_primary": False})
    
    broker = BrokerConfig(
        broker_name=config.broker_name,
        api_key=config.api_key,
        api_secret=config.api_secret,
        user_id=config.user_id,
        is_primary=config.is_primary,
        is_active=True
    )
    db.add(broker)
    db.commit()
    db.refresh(broker)
    
    return broker

@router.get("/brokers/{broker_id}/health")
async def check_broker_health(
    broker_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Check broker health"""
    broker = db.query(BrokerConfig).filter(BrokerConfig.id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
    
    health_service = BrokerHealthService(db)
    result = await health_service.check_broker_health(broker.broker_name)
    
    return result

@router.get("/brokers/status")
async def get_all_broker_statuses(db: Session = Depends(get_db)):
    """Get status of all brokers"""
    health_service = BrokerHealthService(db)
    statuses = health_service.get_all_broker_statuses()
    
    return statuses

@router.put("/brokers/{broker_id}/primary")
async def set_primary_broker(broker_id: int, db: Session = Depends(get_db)):
    """Set a broker as primary"""
    # Unset all primaries
    db.query(BrokerConfig).update({"is_primary": False})
    
    # Set this one as primary
    broker = db.query(BrokerConfig).filter(BrokerConfig.id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
    
    broker.is_primary = True
    db.commit()
    
    return broker

@router.delete("/brokers/{broker_id}")
async def delete_broker(broker_id: int, db: Session = Depends(get_db)):
    """Delete broker configuration"""
    broker = db.query(BrokerConfig).filter(BrokerConfig.id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
    
    db.delete(broker)
    db.commit()
    
    return {"message": "Broker deleted"}
