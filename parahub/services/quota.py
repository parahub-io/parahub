"""
Quota Service - Hybrid Redis + PostgreSQL quota management

Architecture:
- Redis: Real-time counters (fast, atomic, auto-expiring TTL)
- PostgreSQL: Historical audit log (QuotaUsageLog model)

Usage:
    from parahub.services.quota import QuotaService

    # Check quota
    quota_info = QuotaService.check_quota(account_id, 'ai_analysis')
    if quota_info['remaining'] <= 0:
        raise QuotaExceeded()

    # Consume quota
    QuotaService.consume_quota(account_id, 'ai_analysis', metadata={'log_id': 123})
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    """Raised when quota limit is exceeded"""
    def __init__(self, resource_type: str, limit: int, reset_at: datetime):
        self.resource_type = resource_type
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(f"Quota exceeded for {resource_type} (limit: {limit}, resets at {reset_at})")


class QuotaService:
    """
    Quota management service using Redis for real-time limits
    """

    # Default limits (can be overridden per account in future)
    DEFAULT_LIMITS = {
        'ai_analysis': 30,  # 30 AI analyses per day
        # Future: 'api_calls': 1000, 'storage_mb': 100, etc.
    }

    @staticmethod
    def _get_redis_key(account_id: str, resource_type: str, date: datetime.date) -> str:
        """Generate Redis key for quota counter"""
        return f"quota:daily:{resource_type}:{account_id}:{date.isoformat()}"

    @staticmethod
    def _get_end_of_day(date: datetime.date) -> datetime:
        """Get end of day (23:59:59) in UTC"""
        return datetime.combine(date, datetime.max.time()).replace(tzinfo=timezone.utc)

    @staticmethod
    def check_quota(
        account_id: str,
        resource_type: str,
        limit: Optional[int] = None
    ) -> Dict:
        """
        Check current quota usage

        Args:
            account_id: Account ULID
            resource_type: 'ai_analysis', 'api_calls', etc.
            limit: Override default limit (optional)

        Returns:
            {
                'remaining': 25,
                'limit': 30,
                'used': 5,
                'reset_at': datetime(2025-11-04T00:00:00Z)
            }
        """
        if limit is None:
            limit = QuotaService.DEFAULT_LIMITS.get(resource_type, 0)

        today = datetime.now(timezone.utc).date()
        redis_key = QuotaService._get_redis_key(account_id, resource_type, today)

        # Get current usage from Redis
        used = cache.get(redis_key)
        if used is None:
            used = 0

        # Calculate reset time (tomorrow midnight UTC)
        tomorrow = today + timedelta(days=1)
        reset_at = datetime.combine(tomorrow, datetime.min.time()).replace(tzinfo=timezone.utc)

        return {
            'remaining': max(0, limit - int(used)),
            'limit': limit,
            'used': int(used),
            'reset_at': reset_at
        }

    @staticmethod
    def consume_quota(
        account_id: str,
        resource_type: str,
        amount: int = 1,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Consume quota (increment counter)

        Args:
            account_id: Account ULID
            resource_type: 'ai_analysis', 'api_calls', etc.
            amount: Amount to consume (default 1)
            metadata: Optional context (AI log_id, etc.)

        Returns:
            Updated quota info (same format as check_quota)

        Raises:
            QuotaExceeded: If limit would be exceeded
        """
        from parahub.models import QuotaUsageLog
        from identity.models import Account

        # Check current quota before consuming
        quota_info = QuotaService.check_quota(account_id, resource_type)

        if quota_info['remaining'] < amount:
            raise QuotaExceeded(
                resource_type=resource_type,
                limit=quota_info['limit'],
                reset_at=quota_info['reset_at']
            )

        today = datetime.now(timezone.utc).date()
        redis_key = QuotaService._get_redis_key(account_id, resource_type, today)

        # Increment Redis counter with TTL (expire at end of day)
        current_value = cache.get(redis_key) or 0
        new_value = int(current_value) + amount

        # Set expiry to end of day (ensure key auto-deletes tomorrow)
        end_of_day = QuotaService._get_end_of_day(today)
        ttl_seconds = int((end_of_day - datetime.now(timezone.utc)).total_seconds())

        cache.set(redis_key, new_value, timeout=ttl_seconds)

        logger.info(f"Quota consumed: {account_id} - {resource_type} - {amount} (new total: {new_value}/{quota_info['limit']})")

        # Async logging to PostgreSQL (audit trail)
        try:
            account = Account.objects.get(id=account_id)
            QuotaUsageLog.objects.create(
                account=account,
                resource_type=resource_type,
                amount=amount,
                metadata=metadata
            )
        except Account.DoesNotExist:
            logger.error(f"Account not found for quota logging: {account_id}")
        except Exception as e:
            # Don't fail quota consumption if audit log fails
            logger.error(f"Failed to create QuotaUsageLog: {e}", exc_info=True)

        # Return updated quota info
        return QuotaService.check_quota(account_id, resource_type)

    @staticmethod
    def reset_quota(account_id: str, resource_type: str):
        """
        Manually reset quota (admin/testing only)

        Args:
            account_id: Account ULID
            resource_type: 'ai_analysis', etc.
        """
        today = datetime.now(timezone.utc).date()
        redis_key = QuotaService._get_redis_key(account_id, resource_type, today)
        cache.delete(redis_key)
        logger.info(f"Quota reset: {account_id} - {resource_type}")

    @staticmethod
    def get_account_usage_stats(account_id: str, resource_type: str, days: int = 30) -> Dict:
        """
        Get usage statistics from audit log (for analytics)

        Args:
            account_id: Account ULID
            resource_type: 'ai_analysis', etc.
            days: Number of days to analyze

        Returns:
            {
                'total_used': 150,
                'avg_per_day': 5.0,
                'days_analyzed': 30,
                'daily_breakdown': [{'date': '2025-11-01', 'count': 5}, ...]
            }
        """
        from parahub.models import QuotaUsageLog
        from django.db.models import Count, Sum
        from django.db.models.functions import TruncDate

        since_date = datetime.now(timezone.utc) - timedelta(days=days)

        logs = QuotaUsageLog.objects.filter(
            account_id=account_id,
            resource_type=resource_type,
            used_at__gte=since_date
        )

        total_used = logs.aggregate(total=Sum('amount'))['total'] or 0

        # Daily breakdown
        daily = logs.annotate(
            date=TruncDate('used_at')
        ).values('date').annotate(
            count=Sum('amount')
        ).order_by('-date')

        return {
            'total_used': total_used,
            'avg_per_day': round(total_used / days, 2) if days > 0 else 0,
            'days_analyzed': days,
            'daily_breakdown': list(daily)
        }
