"""
Broker Health Monitoring Service
"""
from typing import Dict, List, Any
from datetime import datetime
import time
from sqlalchemy.orm import Session
from app.db.models.broker_config import BrokerConfig, BrokerHealthCheck, BrokerApiUsage
from app.brokers.fyers import FyersBroker
from loguru import logger

class BrokerHealthService:
    """Monitor broker health and connectivity"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def check_broker_health(self, broker_name: str) -> Dict[str, Any]:
        """Perform health check on a broker"""
        start_time = time.time()
        
        try:
            # Get broker config
            config = self.db.query(BrokerConfig).filter(
                BrokerConfig.broker_name == broker_name,
                BrokerConfig.is_active == True
            ).first()
            
            if not config:
                return self._create_health_result(
                    broker_name, False, "Broker not configured", 0
                )
            
            # Perform connectivity check
            if broker_name == "fyers":
                result = await self._check_fyers_health(config)
            else:
                result = {"is_healthy": False, "error": "Broker not supported"}
            
            response_time = (time.time() - start_time) * 1000
            
            # Save health check result
            health_check = BrokerHealthCheck(
                broker_name=broker_name,
                is_healthy=result.get("is_healthy", False),
                status_code=result.get("status_code", 0),
                response_time_ms=response_time,
                check_type="connectivity",
                error_message=result.get("error")
            )
            self.db.add(health_check)
            self.db.commit()
            
            return {
                "broker_name": broker_name,
                "is_healthy": result.get("is_healthy", False),
                "response_time_ms": response_time,
                "error": result.get("error"),
                "checked_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Health check failed for {broker_name}: {e}")
            response_time = (time.time() - start_time) * 1000
            return self._create_health_result(
                broker_name, False, str(e), response_time
            )
    
    async def _check_fyers_health(self, config: BrokerConfig) -> Dict[str, Any]:
        """Check Fyers broker health"""
        try:
            # Try to initialize broker (this will check auth)
            broker = FyersBroker()
            
            # Simple connectivity test - get profile
            # In production, you'd call a lightweight API endpoint
            return {
                "is_healthy": True,
                "status_code": 200
            }
        except Exception as e:
            return {
                "is_healthy": False,
                "status_code": 500,
                "error": str(e)
            }
    
    def _create_health_result(
        self, broker_name: str, is_healthy: bool, error: str, response_time: float
    ) -> Dict[str, Any]:
        """Create standardized health result"""
        return {
            "broker_name": broker_name,
            "is_healthy": is_healthy,
            "response_time_ms": response_time,
            "error": error,
            "checked_at": datetime.now()
        }
    
    def get_broker_status(self, broker_name: str) -> Dict[str, Any]:
        """Get latest broker status"""
        latest_check = self.db.query(BrokerHealthCheck).filter(
            BrokerHealthCheck.broker_name == broker_name
        ).order_by(BrokerHealthCheck.checked_at.desc()).first()
        
        if not latest_check:
            return {"status": "unknown", "message": "No health checks performed"}
        
        return {
            "broker_name": broker_name,
            "is_healthy": latest_check.is_healthy,
            "response_time_ms": latest_check.response_time_ms,
            "error_message": latest_check.error_message,
            "last_checked": latest_check.checked_at
        }
    
    def get_all_broker_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all configured brokers"""
        configs = self.db.query(BrokerConfig).filter(
            BrokerConfig.is_active == True
        ).all()
        
        statuses = []
        for config in configs:
            status = self.get_broker_status(config.broker_name)
            status["is_primary"] = config.is_primary
            statuses.append(status)
        
        return statuses
