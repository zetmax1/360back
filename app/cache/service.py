import json
import logging
from typing import Any, Optional
from redis.asyncio import Redis
from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self, redis: Redis):
        self.redis = redis

    # ── Core operations ──────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """Get a cached value. Returns None on miss or error."""
        try:
            raw = await self.redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Cache GET failed for key={key}: {e}")
            return None  # Cache miss on error — never crash on cache failure

    async def set(self, key: str, value: Any, ttl: int) -> bool:
        """Store a value with TTL in seconds. Returns False on error."""
        try:
            serialized = json.dumps(value, default=str)
            await self.redis.set(key, serialized, ex=ttl)
            return True
        except Exception as e:
            logger.warning(f"Cache SET failed for key={key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a single key."""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache DELETE failed for key={key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern. Returns count deleted."""
        try:
            # Use SCAN instead of KEYS — never block Redis with KEYS in production
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                    deleted += len(keys)
                if int(cursor) == 0:
                    break
            return deleted
        except Exception as e:
            logger.warning(f"Cache DELETE_PATTERN failed for pattern={pattern}: {e}")
            return 0

    # ── Namespace invalidation ────────────────────────────────

    async def invalidate_tour(self, tour_id: str, slug: str) -> None:
        """Invalidate all cache entries related to a specific tour."""
        await self.delete(f"tour360:tours:list")
        await self.delete(f"tour360:tours:slug:{slug}")
        await self.delete(f"tour360:admin:tours:list")
        await self.delete(f"tour360:admin:tours:{tour_id}:scenes")
        logger.info(f"Cache invalidated for tour_id={tour_id} slug={slug}")

    async def invalidate_scene(self, scene_id: str, tour_id: str, tour_slug: str) -> None:
        """Invalidate cache entries for a scene and its parent tour."""
        await self.delete(f"tour360:scenes:{scene_id}")
        await self.delete(f"tour360:scenes:{scene_id}:links")
        await self.invalidate_tour(tour_id, tour_slug)
        logger.info(f"Cache invalidated for scene_id={scene_id}")

    async def invalidate_all(self) -> int:
        """Nuclear option — delete ALL tour360 cache keys. Used by admin clear button."""
        count = await self.delete_pattern("tour360:*")
        logger.info(f"Full cache clear: {count} keys deleted")
        return count

    # ── Health ────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            return await self.redis.ping()
        except Exception:
            return False

    async def stats(self) -> dict:
        """Return cache statistics for the admin dashboard."""
        try:
            info = await self.redis.info("stats")
            keyspace = await self.redis.info("keyspace")
            cursor, keys = await self.redis.scan(0, match="tour360:*", count=1000)

            last_cleared = await self.get("tour360:meta:last_cleared")

            return {
                "connected": True,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calc_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                ),
                "tour360_keys": len(keys),
                "memory_used_mb": round(
                    int(await self.redis.memory_usage("tour360:tours:list") or 0) / 1024 / 1024, 2
                ) if keys else 0,
                "last_cleared": last_cleared,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def _calc_hit_rate(self, hits: int, misses: int) -> float:
        total = hits + misses
        return round(hits / total * 100, 1) if total > 0 else 0.0
