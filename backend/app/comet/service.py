import asyncio
from typing import List
from app.comet.jobs import CometJob, NewsScraperJob, SentimentAnalyzerJob
from loguru import logger

class CometService:
    """
    Scheduler and Manager for Comet Jobs.
    """
    def __init__(self):
        self.jobs: List[CometJob] = []
        self.is_running = False

    def register_job(self, job: CometJob):
        self.jobs.append(job)
        logger.info(f"Registered Comet Job: {job.name}")

    async def start(self):
        """Start the scheduler loop."""
        self.is_running = True
        logger.info("Comet Service Started")
        
        # Register default jobs
        self.register_job(NewsScraperJob())
        self.register_job(SentimentAnalyzerJob())

        # Start job loops
        tasks = [self._run_job_loop(job) for job in self.jobs]
        await asyncio.gather(*tasks)

    async def stop(self):
        self.is_running = False
        logger.info("Comet Service Stopped")

    async def _run_job_loop(self, job: CometJob):
        while self.is_running:
            try:
                result = await job.run()
                logger.info(f"Job {job.name} completed. Result: {result}")
            except Exception as e:
                logger.error(f"Job {job.name} failed: {e}")
            
            await asyncio.sleep(job.interval_seconds)
