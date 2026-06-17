import functools
from typing import Callable, Any

def cached(key_fn: Callable, ttl: int):
    """
    Decorator for async service functions.

    Usage:
        @cached(key_fn=lambda tour_id: f"tour360:scenes:{tour_id}:links", ttl=86400)
        async def get_scene_links(self, scene_id: str, cache: CacheService) -> list:
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, cache=None, **kwargs):
            if cache is None:
                # No cache provided — call function directly
                return await func(*args, **kwargs)

            key = key_fn(*args, **kwargs)
            cached_val = await cache.get(key)
            if cached_val is not None:
                return cached_val

            result = await func(*args, cache=cache, **kwargs)
            if result is not None:
                # Serialize to dict before caching (Pydantic models → dict)
                # Need to handle case where result might be SQLAlchemy models, Pydantic models or dicts
                if isinstance(result, list):
                    serializable = [r.model_dump() if hasattr(r, 'model_dump') else (r if isinstance(r, dict) else r) for r in result]
                else:
                    serializable = result.model_dump() if hasattr(result, 'model_dump') else (result if isinstance(result, dict) else result)
                await cache.set(key, serializable, ttl)
            return result
        return wrapper
    return decorator
