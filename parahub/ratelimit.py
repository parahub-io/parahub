"""
Rate limiting utilities for Parahub API endpoints
Using django-ratelimit with Django Ninja integration
"""

from functools import wraps
from django.core.cache import cache
from ninja.errors import HttpError
from django_ratelimit.decorators import ratelimit as django_ratelimit
from django_ratelimit.exceptions import Ratelimited
import logging

logger = logging.getLogger(__name__)


def ratelimit(group=None, key='ip', rate='5/m', method='ALL', block=True):
    """
    Rate limiting decorator for Django Ninja endpoints

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
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Skip rate limiting for localhost (E2E tests)
            client_ip = get_ip(request)
            if client_ip in ('127.0.0.1', 'localhost', '::1'):
                return func(request, *args, **kwargs)

            # Apply django-ratelimit logic manually
            try:
                # Use django-ratelimit to check the rate
                limited = django_ratelimit(
                    group=group,
                    key=key,
                    rate=rate,
                    method=method,
                    block=block
                )(lambda r: None)

                # Call the rate limit check
                limited(request)

                # Check if request was rate limited
                if getattr(request, 'limited', False) and block:
                    logger.warning(
                        f"Rate limit exceeded for {group or 'endpoint'}: "
                        f"IP={request.META.get('REMOTE_ADDR')}, "
                        f"Path={request.path}"
                    )
                    raise HttpError(
                        429,
                        "rate_limited"
                    )

                # Execute the actual endpoint function
                return func(request, *args, **kwargs)

            except Ratelimited:
                logger.warning(
                    f"Rate limit exceeded for {group or 'endpoint'}: "
                    f"IP={request.META.get('REMOTE_ADDR')}, "
                    f"Path={request.path}"
                )
                raise HttpError(
                    429,
                    "rate_limited"
                )

        return wrapper
    return decorator


def get_ip(request):
    """
    Get client IP address from request, considering proxies
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


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
