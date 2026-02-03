"""
Redis Cache Service
KeepGaining Trading Platform

Provides Redis-based caching for:
- Market data caching
- Session management
- Rate limiting
- Real-time event pub/sub
"""

import json
from typing import Any, Dict, List, Optional, Callable
from datetime import timedelta
from functools import wraps
import asyncio
from loguru import logger

# Optional Redis dependency
try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None


class CacheConfig:
    """Redis cache configuration."""
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        prefix: str = "keepgaining:",
        default_ttl: int = 3600,  # 1 hour
        max_connections: int = 10,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.max_connections = max_connections


class RedisCache:
    """
    Redis cache service for high-performance caching.
    
    Features:
    - Automatic JSON serialization/deserialization
    - Key prefixing to avoid collisions
    - TTL management
    - Pub/Sub support for real-time events
    - Graceful fallback when Redis is unavailable
    """
    
    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self._client: Optional[Redis] = None
        self._pubsub = None
        self._connected = False
        self._local_cache: Dict[str, Any] = {}  # Fallback cache
        
    async def connect(self) -> bool:
        """Connect to Redis server."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis package not installed, using local cache fallback")
            return False
        
        try:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=True,
                max_connections=self.config.max_connections,
            )
            
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using local cache fallback.")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("Disconnected from Redis")
    
    def _key(self, key: str) -> str:
        """Get prefixed key."""
        return f"{self.config.prefix}{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                value = await self._client.get(full_key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.error(f"Redis GET error: {e}")
        
        # Fallback to local cache
        return self._local_cache.get(full_key)
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in cache with optional TTL."""
        full_key = self._key(key)
        ttl = ttl or self.config.default_ttl
        
        try:
            serialized = json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize value for key {key}: {e}")
            return False
        
        if self._connected and self._client:
            try:
                await self._client.setex(full_key, ttl, serialized)
                return True
            except Exception as e:
                logger.error(f"Redis SET error: {e}")
        
        # Fallback to local cache (without TTL support)
        self._local_cache[full_key] = value
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                await self._client.delete(full_key)
            except Exception as e:
                logger.error(f"Redis DELETE error: {e}")
        
        self._local_cache.pop(full_key, None)
        return True
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                return await self._client.exists(full_key) > 0
            except Exception as e:
                logger.error(f"Redis EXISTS error: {e}")
        
        return full_key in self._local_cache
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on existing key."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                return await self._client.expire(full_key, ttl)
            except Exception as e:
                logger.error(f"Redis EXPIRE error: {e}")
        
        return False
    
    async def ttl(self, key: str) -> int:
        """Get TTL of a key (-1 if no TTL, -2 if not exists)."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                return await self._client.ttl(full_key)
            except Exception as e:
                logger.error(f"Redis TTL error: {e}")
        
        return -2 if full_key not in self._local_cache else -1
    
    # =========================================================================
    # Hash operations for structured data
    # =========================================================================
    
    async def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                serialized = json.dumps(value, default=str)
                await self._client.hset(full_key, field, serialized)
                return True
            except Exception as e:
                logger.error(f"Redis HSET error: {e}")
        
        # Fallback
        if full_key not in self._local_cache:
            self._local_cache[full_key] = {}
        self._local_cache[full_key][field] = value
        return True
    
    async def hget(self, key: str, field: str) -> Optional[Any]:
        """Get hash field."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                value = await self._client.hget(full_key, field)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.error(f"Redis HGET error: {e}")
        
        # Fallback
        return self._local_cache.get(full_key, {}).get(field)
    
    async def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                data = await self._client.hgetall(full_key)
                return {k: json.loads(v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"Redis HGETALL error: {e}")
        
        return self._local_cache.get(full_key, {})
    
    # =========================================================================
    # List operations for queues/history
    # =========================================================================
    
    async def lpush(self, key: str, *values: Any) -> int:
        """Push values to left of list."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                serialized = [json.dumps(v, default=str) for v in values]
                return await self._client.lpush(full_key, *serialized)
            except Exception as e:
                logger.error(f"Redis LPUSH error: {e}")
        
        # Fallback
        if full_key not in self._local_cache:
            self._local_cache[full_key] = []
        self._local_cache[full_key] = list(values) + self._local_cache[full_key]
        return len(self._local_cache[full_key])
    
    async def lrange(self, key: str, start: int, end: int) -> List[Any]:
        """Get list range."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                data = await self._client.lrange(full_key, start, end)
                return [json.loads(v) for v in data]
            except Exception as e:
                logger.error(f"Redis LRANGE error: {e}")
        
        # Fallback
        cache_list = self._local_cache.get(full_key, [])
        if end == -1:
            return cache_list[start:]
        return cache_list[start:end + 1]
    
    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim list to specified range."""
        full_key = self._key(key)
        
        if self._connected and self._client:
            try:
                await self._client.ltrim(full_key, start, end)
                return True
            except Exception as e:
                logger.error(f"Redis LTRIM error: {e}")
        
        # Fallback
        if full_key in self._local_cache:
            self._local_cache[full_key] = self._local_cache[full_key][start:end + 1]
        return True
    
    # =========================================================================
    # Pub/Sub for real-time events
    # =========================================================================
    
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel."""
        if self._connected and self._client:
            try:
                serialized = json.dumps(message, default=str)
                return await self._client.publish(self._key(channel), serialized)
            except Exception as e:
                logger.error(f"Redis PUBLISH error: {e}")
        return 0
    
    async def subscribe(self, *channels: str) -> Any:
        """Subscribe to channels."""
        if self._connected and self._client:
            try:
                self._pubsub = self._client.pubsub()
                prefixed = [self._key(ch) for ch in channels]
                await self._pubsub.subscribe(*prefixed)
                return self._pubsub
            except Exception as e:
                logger.error(f"Redis SUBSCRIBE error: {e}")
        return None
    
    async def listen(self) -> Optional[Dict[str, Any]]:
        """Listen for pub/sub messages."""
        if self._pubsub:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    return {
                        'channel': message['channel'].replace(self.config.prefix, ''),
                        'data': json.loads(message['data']),
                    }
            except Exception as e:
                logger.error(f"Redis LISTEN error: {e}")
        return None
    
    # =========================================================================
    # Utility methods
    # =========================================================================
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        if self._connected and self._client:
            try:
                full_pattern = self._key(pattern)
                keys = await self._client.keys(full_pattern)
                prefix_len = len(self.config.prefix)
                return [k[prefix_len:] for k in keys]
            except Exception as e:
                logger.error(f"Redis KEYS error: {e}")
        
        return [k.replace(self.config.prefix, '') for k in self._local_cache.keys()]
    
    async def clear(self, pattern: str = "*") -> int:
        """Clear keys matching pattern."""
        keys = await self.keys(pattern)
        count = 0
        for key in keys:
            await self.delete(key)
            count += 1
        return count
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._connected


# =========================================================================
# Caching decorators
# =========================================================================

def cached(
    key_prefix: str,
    ttl: int = 3600,
    key_builder: Optional[Callable[..., str]] = None,
):
    """
    Decorator to cache function results.
    
    Args:
        key_prefix: Prefix for cache key
        ttl: Time to live in seconds
        key_builder: Custom function to build cache key from args
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Build cache key
            if key_builder:
                cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
            else:
                # Default key from args
                key_parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
                cache_key = f"{key_prefix}:{':'.join(key_parts)}"
            
            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


# =========================================================================
# Singleton instance
# =========================================================================

_cache_instance: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    """Get or create the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache()
    return _cache_instance


async def initialize_cache(config: CacheConfig = None) -> RedisCache:
    """Initialize the global cache instance."""
    global _cache_instance
    _cache_instance = RedisCache(config)
    await _cache_instance.connect()
    return _cache_instance


async def shutdown_cache():
    """Shutdown the global cache instance."""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.disconnect()
        _cache_instance = None
