"""
Create database tables using SQLite (simpler setup)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from app.db.base import Base

# Import all models
from app.db.models.strategy import Strategy, StrategyVersion, StrategyParameter, StrategyTest
from app.db.models.deployment import Deployment, DeploymentApproval, DeploymentHistory
from app.db.models.trading_mode import TradingSession, TradingModeSwitch
from app.db.models.broker_config import BrokerConfig, BrokerHealthCheck, BrokerApiUsage

# Use SQLite for simplicity
DATABASE_URL = "sqlite:///./keepgaining.db"

def create_tables():
    try:
        print(f"Using database: {DATABASE_URL}")
        engine = create_engine(DATABASE_URL, echo=False)
        
        print("Creating tables...")
        Base.metadata.create_all(bind=engine)
        
        print("\nSuccess! Tables created:")
        for table in Base.metadata.sorted_tables:
            print(f"  - {table.name}")
        
        print("\nDatabase ready for Phase 8!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_tables()
