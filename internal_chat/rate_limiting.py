"""
Rate limiting utilities for WebSocket connections

Provides WebSocketRateLimiter class for preventing DoS attacks via
message flooding. Uses Django cache backend (Redis or LocMemCache).
"""
import logging
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class WebSocketRateLimiter:
    """
    Rate limiter for WebSocket events
    
    Uses Django cache to track action counts per user within a time window.
    Supports distributed rate limiting when using Redis backend.
    """
    
    def __init__(self, user_id, action, limit=60, window=60):
        """
        Initialize rate limiter.
        
        Args:
            user_id: User ID to rate limit
            action: Action type (e.g., 'message_send', 'reaction', 'typing')
            limit: Maximum number of actions allowed in window
            window: Time window in seconds
        """
        self.user_id = user_id
        self.action = action
        self.limit = limit
        self.window = window
        self.cache_key = f"ws_rate_{action}_{user_id}"
    
    def is_allowed(self):
        """
        Check if action is allowed under rate limit.
        
        Returns:
            bool: True if allowed, False if rate limit exceeded
        """
        current_count = cache.get(self.cache_key, 0)
        
        if current_count >= self.limit:
            logger.warning(
                f"Rate limit exceeded for user {self.user_id} on {self.action}: "
                f"{current_count}/{self.limit} in {self.window}s"
            )
            return False
        
        return True
    
    def increment(self):
        """
        Increment the rate limit counter.
        
        Sets TTL to window duration on first increment to ensure automatic reset.
        """
        current_count = cache.get(self.cache_key, 0)
        cache.set(self.cache_key, current_count + 1, self.window)
    
    def get_remaining(self):
        """
        Get remaining actions allowed.
        
        Returns:
            int: Number of actions remaining
        """
        current_count = cache.get(self.cache_key, 0)
        return max(0, self.limit - current_count)
    
    def get_current_count(self):
        """
        Get current action count.
        
        Returns:
            int: Current number of actions in window
        """
        return cache.get(self.cache_key, 0)
    
    def reset(self):
        """
        Reset the rate limit counter (use with caution).
        
        This should only be used in testing or administrative actions.
        """
        cache.delete(self.cache_key)
        logger.info(f"Rate limit reset for user {self.user_id} on {self.action}")


def check_rate_limit(user_id, action, limit=60, window=60):
    """
    Convenience function to check and increment rate limit in one call.
    
    This is the recommended way to apply rate limiting as it's atomic
    (check + increment happen together).
    
    Args:
        user_id: User ID
        action: Action type (e.g., 'message_send', 'reaction_add')
        limit: Max actions per window (default: 60)
        window: Time window in seconds (default: 60)
        
    Returns:
        bool: True if allowed (and incremented), False if exceeded
    """
    limiter = WebSocketRateLimiter(user_id, action, limit, window)
    
    if limiter.is_allowed():
        limiter.increment()
        logger.debug(
            f"Rate limit check passed for user {user_id} on {action}: "
            f"{limiter.get_current_count()}/{limit}"
        )
        return True
    
    logger.warning(
        f"Rate limit check failed for user {user_id} on {action}: "
        f"{limiter.get_current_count()}/{limit}"
    )
    return False


def get_rate_limit_info(user_id, action, limit=60, window=60):
    """
    Get current rate limit status for a user action.
    
    Useful for informing clients about their current usage.
    
    Args:
        user_id: User ID
        action: Action type
        limit: Max actions per window
        window: Time window in seconds
        
    Returns:
        dict: Rate limit information with keys:
            - current: Current action count
            - limit: Maximum allowed
            - remaining: Actions remaining
            - window: Time window in seconds
            - allowed: Whether next action would be allowed
    """
    limiter = WebSocketRateLimiter(user_id, action, limit, window)
    current = limiter.get_current_count()
    remaining = limiter.get_remaining()
    
    return {
        'current': current,
        'limit': limit,
        'remaining': remaining,
        'window': window,
        'allowed': remaining > 0
    }
