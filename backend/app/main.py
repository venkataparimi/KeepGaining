"""
KeepGaining Trading Platform - FastAPI Application
Main entry point with proper lifecycle management.

Service Architecture:
    DataOrchestrator (coordinates data sources)
        ↓
    FyersWebSocket / UpstoxBatch (data ingestion)
        ↓
    CandleBuilder (tick → candle aggregation)
        ↓
    IndicatorService (technical indicators)
        ↓
    StrategyEngine (signal generation)
        ↓
    RiskManager (pre-trade validation)
        ↓
    PositionManager (position tracking)
        ↓
    OrderManager (order execution)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.events import get_event_bus, shutdown_event_bus, EventType, SystemEvent
from app.db.session import DatabaseService
from app.api import api_router
from app.api.docs import openapi_config, tags_metadata

# Service imports
from app.services.candle_builder import CandleBuilderService
from app.services.indicator_service import IndicatorService
from app.services.strategy_engine import StrategyEngine, create_strategy_engine
from app.services.risk_manager import RiskManager, create_risk_manager
from app.services.position_manager import PositionManager, create_position_manager
from app.services.order_manager import OrderManager, create_order_manager
from app.services.data_orchestrator import DataFeedOrchestrator, create_data_orchestrator


# =============================================================================
# Global Service Registry
# =============================================================================

class ServiceRegistry:
    """Registry for all trading services."""
    
    def __init__(self):
        self.candle_builder: Optional[CandleBuilderService] = None
        self.indicator_service: Optional[IndicatorService] = None
        self.strategy_engine: Optional[StrategyEngine] = None
        self.risk_manager: Optional[RiskManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.order_manager: Optional[OrderManager] = None
        self.data_orchestrator: Optional[DataFeedOrchestrator] = None
        self._initialized = False
    
    async def initialize(self, event_bus) -> None:
        """Initialize all services with proper dependencies."""
        if self._initialized:
            return
        
        logger.info("Initializing trading services...")
        
        # Create services in dependency order
        # Note: Services get event_bus via get_event_bus() in their start() method
        self.candle_builder = CandleBuilderService()  # Uses default timeframes
        self.indicator_service = IndicatorService()   # Uses default timeframes
        self.strategy_engine = create_strategy_engine(event_bus)
        self.risk_manager = create_risk_manager(event_bus)
        self.position_manager = create_position_manager(event_bus)
        self.order_manager = create_order_manager(event_bus, paper_trading=True)
        self.data_orchestrator = create_data_orchestrator(event_bus)
        
        self._initialized = True
        logger.info("✓ Trading services initialized")
    
    async def start_all(self) -> None:
        """Start all trading services."""
        if not self._initialized:
            raise RuntimeError("Services not initialized")
        
        logger.info("Starting trading services...")
        
        # Start in dependency order
        await self.candle_builder.start()
        await self.indicator_service.start()
        await self.strategy_engine.start()
        await self.risk_manager.start()
        await self.position_manager.start()
        await self.order_manager.start()
        await self.data_orchestrator.start()
        
        logger.info("✓ All trading services started")
    
    async def stop_all(self) -> None:
        """Stop all trading services gracefully."""
        logger.info("Stopping trading services...")
        
        # Stop in reverse order
        if self.data_orchestrator:
            await self.data_orchestrator.stop()
        if self.order_manager:
            await self.order_manager.stop()
        if self.position_manager:
            await self.position_manager.stop()
        if self.risk_manager:
            await self.risk_manager.stop()
        if self.strategy_engine:
            await self.strategy_engine.stop()
        if self.indicator_service:
            await self.indicator_service.stop()
        if self.candle_builder:
            await self.candle_builder.stop()
        
        logger.info("✓ All trading services stopped")
    
    def get_status(self) -> dict:
        """Get status of all services."""
        return {
            "initialized": self._initialized,
            "services": {
                "candle_builder": self.candle_builder is not None,
                "indicator_service": self.indicator_service is not None,
                "strategy_engine": self.strategy_engine is not None,
                "risk_manager": self.risk_manager is not None,
                "position_manager": self.position_manager is not None,
                "order_manager": self.order_manager is not None,
                "data_orchestrator": self.data_orchestrator is not None,
            }
        }


# Global service registry instance
services = ServiceRegistry()


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # -------------------------------------------------------------------------
    # Startup
    # -------------------------------------------------------------------------
    setup_logging()
    logger.info("=" * 60)
    logger.info("Starting KeepGaining Trading Platform...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info("=" * 60)
    
    # Initialize database
    try:
        db_service = DatabaseService()
        is_healthy = await db_service.health_check()
        if is_healthy:
            logger.info("✓ Database connection established")
        else:
            logger.warning("⚠ Database connection failed - some features may be unavailable")
    except Exception as e:
        logger.error(f"✗ Database initialization error: {e}")
    
    # Initialize event bus
    event_bus = None
    try:
        event_bus = await get_event_bus()
        logger.info("✓ Event bus connected to Redis")
        
        # Publish startup event
        await event_bus.publish(SystemEvent(
            event_type=EventType.SYSTEM_STARTUP,
            component="api",
            status="STARTED",
            details={
                "version": settings.APP_VERSION,
                "environment": settings.ENVIRONMENT,
            }
        ))
    except Exception as e:
        logger.warning(f"⚠ Event bus initialization failed: {e}")
        logger.warning("Running without event bus - some features may be limited")
    
    # Initialize trading services (if event bus available)
    if event_bus:
        try:
            await services.initialize(event_bus)
            
            # Auto-start services in non-production or if explicitly enabled
            if settings.ENVIRONMENT != "production" or settings.get("AUTO_START_SERVICES", False):
                await services.start_all()
                logger.info("✓ Trading services auto-started")
            else:
                logger.info("Trading services initialized (manual start required)")
        except Exception as e:
            logger.error(f"✗ Trading services initialization failed: {e}")
    
    logger.info("-" * 60)
    logger.info("KeepGaining API ready to accept requests")
    logger.info("-" * 60)
    
    yield
    
    # -------------------------------------------------------------------------
    # Shutdown
    # -------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("Shutting down KeepGaining Trading Platform...")
    
    # Stop trading services first
    try:
        await services.stop_all()
        logger.info("✓ Trading services stopped")
    except Exception as e:
        logger.error(f"Error stopping trading services: {e}")
    
    # Publish shutdown event
    try:
        event_bus = await get_event_bus()
        await event_bus.publish(SystemEvent(
            event_type=EventType.SYSTEM_SHUTDOWN,
            component="api",
            status="STOPPING",
        ))
    except Exception:
        pass  # Ignore errors during shutdown
    
    # Disconnect event bus
    try:
        await shutdown_event_bus()
        logger.info("✓ Event bus disconnected")
    except Exception as e:
        logger.error(f"Error disconnecting event bus: {e}")
    
    # Close database connections
    try:
        db_service = DatabaseService()
        await db_service.close()
        logger.info("✓ Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")
    
    logger.info("KeepGaining API shutdown complete")
    logger.info("=" * 60)


# =============================================================================
# Application Factory
# =============================================================================

def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """
    application = FastAPI(
        title=openapi_config["title"],
        version=openapi_config["version"],
        description=openapi_config["description"],
        contact=openapi_config["contact"],
        license_info=openapi_config["license_info"],
        openapi_tags=openapi_config["openapi_tags"],
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )
    
    # CORS Configuration
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost",
        "http://127.0.0.1:3000",
    ]
    
    # Add production origins if configured
    if settings.ALLOWED_ORIGINS:
        origins.extend(settings.ALLOWED_ORIGINS)
    
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    application.include_router(api_router, prefix="/api")
    
    return application


# Create application instance
app = create_application()


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint for load balancers and monitoring.
    """
    health_status = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }
    
    # Check database health
    try:
        db_service = DatabaseService()
        db_healthy = await db_service.health_check()
        health_status["database"] = "connected" if db_healthy else "disconnected"
    except Exception:
        health_status["database"] = "error"
    
    # Check Redis health
    try:
        event_bus = await get_event_bus()
        if event_bus._redis:
            await event_bus._redis.ping()
            health_status["redis"] = "connected"
        else:
            health_status["redis"] = "disconnected"
    except Exception:
        health_status["redis"] = "error"
    
    # Check trading services
    health_status["services"] = services.get_status()
    
    # Determine overall status
    if health_status.get("database") == "error" or health_status.get("redis") == "error":
        health_status["status"] = "degraded"
    
    return health_status


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "message": "Welcome to KeepGaining Trading Platform API",
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "Disabled in production",
        "health": "/health",
    }


@app.get("/info")
async def info():
    """
    Application information endpoint.
    """
    return {
        "name": "KeepGaining Trading Platform",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "features": {
            "options_trading": True,
            "multi_broker": True,
            "event_driven": True,
            "realtime_data": True,
        },
        "supported_exchanges": ["NSE", "NFO"],
        "supported_brokers": ["FYERS", "UPSTOX"],
    }


# =============================================================================
# Trading Service Control Endpoints
# =============================================================================

@app.post("/services/start")
async def start_services():
    """Start all trading services."""
    try:
        if not services._initialized:
            event_bus = await get_event_bus()
            await services.initialize(event_bus)
        
        await services.start_all()
        return {"status": "success", "message": "All trading services started"}
    except Exception as e:
        logger.error(f"Failed to start services: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/services/stop")
async def stop_services():
    """Stop all trading services."""
    try:
        await services.stop_all()
        return {"status": "success", "message": "All trading services stopped"}
    except Exception as e:
        logger.error(f"Failed to stop services: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/services/status")
async def get_services_status():
    """Get status of all trading services."""
    status = services.get_status()
    
    # Add detailed stats if services are running
    if services.strategy_engine:
        status["strategy_engine_stats"] = services.strategy_engine.get_stats()
    
    if services.risk_manager:
        status["risk_report"] = services.risk_manager.get_daily_report()
    
    if services.position_manager:
        status["portfolio"] = services.position_manager.get_portfolio_summary()
    
    if services.order_manager:
        status["orders"] = services.order_manager.get_order_summary()
    
    if services.data_orchestrator:
        status["data_feeds"] = services.data_orchestrator.get_data_source_status()
        status["subscriptions"] = services.data_orchestrator.get_subscription_summary()
    
    return status
