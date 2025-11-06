"""
Simple in-memory rate limiter middleware for Quart.
Uses a sliding window approach to track requests per IP address.
"""
import time
import logging
from collections import defaultdict, deque
from functools import wraps
from typing import Dict, Deque, Tuple
from quart import request, jsonify

logger = logging.getLogger(__name__)


class SimpleRateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.
    
    Note: This is suitable for single-instance deployments.
    For multi-instance deployments, use Redis or Azure services.
    """
    
    def __init__(self):
        # Store: {ip_address: {endpoint: deque of timestamps}}
        self.requests: Dict[str, Dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(deque))
        logger.info("Rate limiter initialized (in-memory)")
    
    def is_rate_limited(self, ip: str, endpoint: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if a request should be rate limited.
        
        Args:
            ip: Client IP address
            endpoint: API endpoint identifier
            max_requests: Maximum requests allowed in the time window
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (is_limited, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds
        
        # Get request history for this IP and endpoint
        request_times = self.requests[ip][endpoint]
        
        # Remove old requests outside the window
        while request_times and request_times[0] < window_start:
            request_times.popleft()
        
        # Check if limit exceeded
        if len(request_times) >= max_requests:
            # Calculate retry-after: time until oldest request expires
            oldest_request = request_times[0]
            retry_after = int(window_seconds - (now - oldest_request)) + 1
            return True, retry_after
        
        # Add current request
        request_times.append(now)
        return False, 0
    
    def cleanup_old_entries(self, max_age_seconds: int = 3600):
        """
        Periodic cleanup of old entries to prevent memory growth.
        Should be called periodically (e.g., every hour).
        """
        now = time.time()
        cutoff = now - max_age_seconds
        
        # Remove IPs with no recent requests
        ips_to_remove = []
        for ip, endpoints in self.requests.items():
            for endpoint, request_times in list(endpoints.items()):
                # Remove old timestamps
                while request_times and request_times[0] < cutoff:
                    request_times.popleft()
                
                # Remove empty endpoint entries
                if not request_times:
                    del endpoints[endpoint]
            
            # Mark IP for removal if no endpoints remain
            if not endpoints:
                ips_to_remove.append(ip)
        
        # Remove empty IP entries
        for ip in ips_to_remove:
            del self.requests[ip]
        
        logger.debug(f"Rate limiter cleanup: removed {len(ips_to_remove)} IPs")


# Global rate limiter instance
_rate_limiter = SimpleRateLimiter()


def rate_limit(max_requests: int, window_seconds: int, endpoint_name: str = None):
    """
    Decorator to apply rate limiting to a route.
    
    Args:
        max_requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
        endpoint_name: Optional custom endpoint name (defaults to route path)
        
    Example:
        @app.route("/api/upload", methods=["POST"])
        @rate_limit(max_requests=10, window_seconds=3600)  # 10 per hour
        async def upload():
            ...
    """
    def decorator(f):
        @wraps(f)
        async def wrapped(*args, **kwargs):
            # Get client IP (handle X-Forwarded-For for proxies)
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()
            
            # Use custom endpoint name or default to request path
            endpoint = endpoint_name or request.path
            
            # Check rate limit
            is_limited, retry_after = _rate_limiter.is_rate_limited(
                ip=client_ip,
                endpoint=endpoint,
                max_requests=max_requests,
                window_seconds=window_seconds
            )
            
            if is_limited:
                logger.warning(f"Rate limit exceeded for {client_ip} on {endpoint}")
                return jsonify({
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds.",
                    "retry_after": retry_after
                }), 429, {
                    'Retry-After': str(retry_after),
                    'X-RateLimit-Limit': str(max_requests),
                    'X-RateLimit-Window': str(window_seconds)
                }
            
            # Request allowed, proceed
            return await f(*args, **kwargs)
        
        return wrapped
    return decorator


def get_rate_limiter():
    """Get the global rate limiter instance for cleanup tasks."""
    return _rate_limiter
