"""
Add Fyers broker configuration to database
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models.broker_config import BrokerConfig
from app.core.config import settings

DATABASE_URL = "sqlite:///./keepgaining.db"

def add_fyers_broker():
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Check if Fyers broker already exists
        existing = session.query(BrokerConfig).filter(
            BrokerConfig.broker_name == "fyers"
        ).first()
        
        if existing:
            print("Fyers broker already configured!")
            print(f"  - Active: {existing.is_active}")
            print(f"  - Primary: {existing.is_primary}")
            return
        
        # Create Fyers broker config
        fyers_config = BrokerConfig(
            broker_name="fyers",
            is_active=True,
            is_primary=True,
            api_key=settings.FYERS_CLIENT_ID,
            api_secret=settings.FYERS_SECRET_KEY,
            user_id=settings.FYERS_USER_ID,
            config={
                "redirect_uri": settings.FYERS_REDIRECT_URI,
                "pin": settings.FYERS_PIN,
                "totp_key": settings.FYERS_TOTP_KEY
            }
        )
        
        session.add(fyers_config)
        session.commit()
        
        print("✅ Fyers broker configured successfully!")
        print(f"  - Broker: fyers")
        print(f"  - User ID: {settings.FYERS_USER_ID}")
        print(f"  - Status: Active & Primary")
        print("\nBroker status page will now show connection health!")
        
        session.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    add_fyers_broker()
