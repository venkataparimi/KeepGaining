import asyncio
from app.comet.service import CometService
from loguru import logger

async def verify_comet_flow():
    logger.info("Verifying Comet Service...")
    
    # 1. Instantiate Service
    service = CometService()
    
    # 2. Start Service (Run for a short duration)
    # We run it as a background task and cancel it after 3 seconds
    task = asyncio.create_task(service.start())
    
    logger.info("Service started, waiting for jobs to run...")
    await asyncio.sleep(3)
    
    # 3. Stop Service
    await service.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
        
    logger.info("Comet Service Verification Complete")

if __name__ == "__main__":
    asyncio.run(verify_comet_flow())
