#!/usr/bin/env python3
# Main entry point for the core WebSocket-based Queue API
import os
import asyncio
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from utils.logger import logger

import sys
import os

# Add parent directory to path to find core module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.routes import init_routes, start_redis_listener
from core.redis_service import RedisService
from core.connections import ConnectionManager

logger.info("IT WORKS")

# Background task for stale job cleanup
async def stale_job_cleanup_task():
    """Periodically check for and clean up stale jobs"""
    # Run cleanup every 5 minutes (300 seconds)
    cleanup_interval = int(os.environ.get("JOB_CLEANUP_INTERVAL", 300))
    # Max heartbeat age - default 10 minutes (600 seconds)
    max_heartbeat_age = int(os.environ.get("MAX_WORKER_HEARTBEAT_AGE", 600))
    
    while True:
        try:
            # Wait first to allow system to stabilize on startup
            await asyncio.sleep(cleanup_interval)
            
            # Run cleanup
            redis_service = RedisService()
            redis_service.cleanup_stale_jobs(max_heartbeat_age)
            
        except Exception:
            # Continue running even if there's an error
            pass

# FastAPI startup and shutdown event handling
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background tasks
    cleanup_task = asyncio.create_task(stale_job_cleanup_task())
    
    # Create Redis service and connection manager instances
    redis_service = RedisService()
    connection_manager = ConnectionManager()
    
    # Initialize WebSocket routes with explicit instances
    init_routes(app, redis_service=redis_service, connection_manager=connection_manager)
    
    # Start Redis pub/sub listener
    await start_redis_listener()
    
    yield
    
    # Shutdown tasks
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    # Close Redis connections
    redis_service = RedisService()
    await redis_service.close_async()

# Initialize FastAPI with lifespan manager
app = FastAPI(title="WebSocket Queue API", lifespan=lifespan)

@app.get("/")
def read_root():
    """Root endpoint for health check"""
    return {"status": "ok", "message": "WebSocket Queue API is running"}

# Run the application
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
