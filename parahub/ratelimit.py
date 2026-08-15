"""
Rate limiting utilities for Parahub API endpoints
Using django-ratelimit with Django Ninja integration
"""

import asyncio
from functools import wraps
from asgiref.sync import sync_to_async
from django_ratelimit import ALL as RL_ALL
from django_ratelimit.core import get_usage
from parahub.errors import RateLimitedError
import logging

logger = logging.getLogger(__name__)


def ratelimit(group=None, key='ip', rate='5/m', method='ALL', block=True):
    """
    Rate limiting decorator for Django Ninja endpoints

    Supports both sync and async endpoint functions. For async endpoints the
    check runs via sync_to_async: key callables may resolve request.user,
    which is a lazy sync ORM/session lookup and must not run on the event loop.

    Args:
        group: Group name for the rate limit (e.g., 'auth:login')
        key: Rate limit key ('ip', 'user', or callable)
        rate: Rate limit (e.g., '5/m' = 5 per minute, '10/h' = 10 per hour)
        method: HTTP method to limit ('GET', 'POST', 'ALL')
        block: If True, block requests exceeding limit. If False, allow but mark as limited.

    Usage:
        @ratelimit(group='auth:login', key='ip', rate='5/m')
        def login(request, data):
            ...
    """
    def _enforce(request):
        """Count this request and raise 429 when the window is exhausted.

        Uses get_usage() rather than the blocking decorator so the response can
        carry how long the window still has to run: a bare "too many attempts"
        leaves the user tapping retry (each tap counting), while a countdown
        tells them to come back later.
        """
        # django-ratelimit's ALL is a sentinel tuple, not the string 'ALL'.
        # Passing the string made _method_match compare request.method
        # against ['ALL'] — never matching, i.e. the limit was silently
        # OFF for every endpoint that used our 'ALL' default (all GETs).
        usage = get_usage(
            request,
            group=group,
            key=key,
            rate=rate,
            method=RL_ALL if method == 'ALL' else method,
            increment=True,
        )
        # None = method not covered, or RATELIMIT_FAIL_OPEN with a dead cache.
        limited = bool(usage and usage['should_limit'])
        request.limited = limited or getattr(request, 'limited', False)

        if limited and block:
            logger.warning(
                f"Rate limit exceeded for {group or 'endpoint'}: "
                f"IP={request.META.get('REMOTE_ADDR')}, "
                f"Path={request.path}"
            )
            # time_left is -1 when the counter itself failed to load
            raise RateLimitedError(retry_after=max(usage['time_left'], 1))

    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, *args, **kwargs):
                # Skip rate limiting for localhost (E2E tests)
                if get_ip(request) not in ('127.0.0.1', 'localhost', '::1'):
                    await sync_to_async(_enforce)(request)
                return await func(request, *args, **kwargs)

            return async_wrapper

        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Skip rate limiting for localhost (E2E tests)
            if get_ip(request) not in ('127.0.0.1', 'localhost', '::1'):
                _enforce(request)
            return func(request, *args, **kwargs)

        return wrapper
    return decorator


def get_ip(request):
    """
    Real client IP, safe to use as a trust / rate-limit key.

    uvicorn runs with proxy-headers (trusted_hosts=127.0.0.1) and rewrites the
    ASGI client — hence REMOTE_ADDR — to the right-most untrusted host in
    X-Forwarded-For, i.e. the address our own nginx appended ($remote_addr on
    the public path, the ygg client on the mesh path). That value is not
    spoofable. Never parse the raw X-Forwarded-For header here: nginx appends
    to any client-sent value, so its left-most element is attacker-controlled
    and would let anyone mint a fresh rate-limit bucket per request.
    """
    return request.META.get('REMOTE_ADDR', '')


def user_or_ip(group, request):
    """
    Rate limit key function: use user ID if authenticated, otherwise IP

    Args:
        group: Rate limit group name (provided by django-ratelimit)
        request: Django request object

    Returns:
        str: Key for rate limiting (user:ID or ip:ADDRESS)
    """
    if request.user.is_authenticated:
        return f"user:{request.user.id}"
    return f"ip:{get_ip(request)}"
