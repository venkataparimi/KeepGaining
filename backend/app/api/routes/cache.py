"""
Cache Management API Routes
KeepGaining Trading Platform

Provides endpoints for Redis cache management and monitoring.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from app.services.redis_cache import get_cache, CacheConfig, initialize_cache


router = APIRouter(prefix="/cache", tags=["cache"])


class CacheStats(BaseModel):
    """Cache statistics."""
    connected: bool
    backend: str
    keys_count: int
    prefix: str


class CacheSetRequest(BaseModel):
    """Request to set cache value."""
    key: str
    value: Any
    ttl: Optional[int] = 3600


class CacheKeyResponse(BaseModel):
    """Response with cache key info."""
    key: str
    exists: bool
    value: Optional[Any] = None
    ttl: int = -2


@router.get("/stats", response_model=CacheStats)
async def get_cache_stats():
    """Get cache statistics."""
    cache = get_cache()
    keys = await cache.keys("*")
    
    return CacheStats(
        connected=cache.is_connected,
        backend="redis" if cache.is_connected else "local",
        keys_count=len(keys),
        prefix=cache.config.prefix,
    )


@router.get("/health")
async def cache_health():
    """Check cache health."""
    cache = get_cache()
    
    # Try a simple operation
    test_key = "_health_check"
    await cache.set(test_key, {"status": "ok"}, ttl=60)
    value = await cache.get(test_key)
    await cache.delete(test_key)
    
    return {
        "status": "healthy" if value else "degraded",
        "connected": cache.is_connected,
        "backend": "redis" if cache.is_connected else "local",
    }


@router.get("/keys")
async def list_keys(
    pattern: str = Query(default="*", description="Key pattern to match"),
) -> List[str]:
    """List cache keys matching pattern."""
    cache = get_cache()
    return await cache.keys(pattern)


@router.get("/get/{key}")
async def get_cache_value(key: str) -> CacheKeyResponse:
    """Get value for a cache key."""
    cache = get_cache()
    
    exists = await cache.exists(key)
    value = await cache.get(key) if exists else None
    ttl = await cache.ttl(key)
    
    return CacheKeyResponse(
        key=key,
        exists=exists,
        value=value,
        ttl=ttl,
    )


@router.post("/set")
async def set_cache_value(request: CacheSetRequest) -> Dict[str, Any]:
    """Set a cache value."""
    cache = get_cache()
    
    success = await cache.set(request.key, request.value, ttl=request.ttl)
    
    return {
        "success": success,
        "key": request.key,
        "ttl": request.ttl,
    }


@router.delete("/delete/{key}")
async def delete_cache_key(key: str) -> Dict[str, bool]:
    """Delete a cache key."""
    cache = get_cache()
    
    existed = await cache.exists(key)
    await cache.delete(key)
    
    return {
        "deleted": existed,
        "key": key,
    }


@router.post("/clear")
async def clear_cache(
    pattern: str = Query(default="*", description="Key pattern to clear"),
) -> Dict[str, int]:
    """Clear cache keys matching pattern."""
    cache = get_cache()
    
    count = await cache.clear(pattern)
    
    return {
        "cleared": count,
        "pattern": pattern,
    }


@router.post("/connect")
async def connect_cache(
    host: str = Query(default="localhost"),
    port: int = Query(default=6379),
    db: int = Query(default=0),
    password: Optional[str] = Query(default=None),
):
    """Connect or reconnect to Redis."""
    config = CacheConfig(
        host=host,
        port=port,
        db=db,
        password=password,
    )
    
    cache = await initialize_cache(config)
    
    return {
        "connected": cache.is_connected,
        "backend": "redis" if cache.is_connected else "local",
        "host": host,
        "port": port,
    }


# =========================================================================
# Market Data Caching
# =========================================================================

@router.post("/market/{symbol}")
async def cache_market_data(
    symbol: str,
    data: Dict[str, Any],
    ttl: int = Query(default=60, description="TTL in seconds"),
):
    """Cache market data for a symbol."""
    cache = get_cache()
    
    key = f"market:{symbol}"
    await cache.set(key, data, ttl=ttl)
    
    return {"cached": True, "symbol": symbol, "ttl": ttl}


@router.get("/market/{symbol}")
async def get_cached_market_data(symbol: str) -> Optional[Dict[str, Any]]:
    """Get cached market data for a symbol."""
    cache = get_cache()
    
    key = f"market:{symbol}"
    data = await cache.get(key)
    
    if not data:
        raise HTTPException(status_code=404, detail=f"No cached data for {symbol}")
    
    return data


# =========================================================================
# Session Management
# =========================================================================

@router.post("/session/{session_id}")
async def create_session(
    session_id: str,
    data: Dict[str, Any],
    ttl: int = Query(default=86400, description="Session TTL (default 24h)"),
):
    """Create or update a session."""
    cache = get_cache()
    
    key = f"session:{session_id}"
    await cache.set(key, data, ttl=ttl)
    
    return {"created": True, "session_id": session_id}


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get session data."""
    cache = get_cache()
    
    key = f"session:{session_id}"
    data = await cache.get(key)
    
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return data


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    cache = get_cache()
    
    key = f"session:{session_id}"
    existed = await cache.exists(key)
    await cache.delete(key)
    
    return {"deleted": existed}


# =========================================================================
# Pub/Sub endpoints
# =========================================================================

@router.post("/publish/{channel}")
async def publish_message(channel: str, message: Dict[str, Any]):
    """Publish a message to a channel."""
    cache = get_cache()
    
    if not cache.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Redis not connected - pub/sub requires Redis",
        )
    
    count = await cache.publish(channel, message)
    
    return {
        "published": True,
        "channel": channel,
        "subscribers": count,
    }
