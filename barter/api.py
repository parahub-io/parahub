"""
Barter Exchange API Endpoints
Django Ninja REST API for barter exchange matching
"""

from ninja import Router, Schema
from typing import List, Optional
from django.core.cache import cache
from django.db import transaction
from barter.graph_service import BarterGraphService
from barter.models import Exchange, ExchangeApproval
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

import json
import logging

logger = logging.getLogger(__name__)

router = Router(tags=["Barter"])
graph_service = BarterGraphService()


# Schemas
class UserInfoSchema(Schema):
    id: str
    display_name: str
    hna: str = ''


class BarterChainSchema(Schema):
    users: List[UserInfoSchema]
    swaps: List[dict]


class BarterOpportunitiesResponse(Schema):
    user_id: str
    chains_count: int
    chains: List[BarterChainSchema]


class GraphStatsSchema(Schema):
    users: int
    items: int
    categories: int
    owns_relationships: int
    category_relationships: int


class ApprovalRequest(Schema):
    approved: bool
    swap_cri: Optional[str] = None


@router.get('/opportunities', response=BarterOpportunitiesResponse, auth=ProfileAuth())
@ratelimit(group='barter:opportunities', key=user_or_ip, rate='30/m')
def get_barter_opportunities(request, max_length: int = None, category_id: str = None):
    """
    Find all possible multi-party barter exchange chains for current user

    Query Params:
        max_length: Maximum chain length (capped by BARTER_MAX_CHAIN_LENGTH from admin settings)
        category_id: Optional category filter
    """
    from constance import config
    profile = request.auth
    user_id = profile.id

    effective_max = config.BARTER_MAX_CHAIN_LENGTH
    if max_length is not None:
        effective_max = min(max_length, effective_max)

    cache_version = cache.get(f"barter:version:{user_id}", 0)
    cache_key = f"barter:chains:{user_id}:{category_id or 'all'}:{effective_max}:v{cache_version}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        chains = graph_service.find_barter_chains(
            user_id=user_id,
            max_length=effective_max,
            category_id=category_id
        )

        result = {
            'user_id': user_id,
            'chains_count': len(chains),
            'chains': chains
        }

        cache.set(cache_key, result, timeout=300)  # 5 min TTL

        return result
    except Exception as e:
        logger.error(f"Failed to find barter opportunities for {user_id}: {e}")
        raise


@router.get('/graph-stats', response=GraphStatsSchema, auth=None)
@ratelimit(group='barter:stats', key='ip', rate='60/m')
def get_graph_stats(request):
    """
    Get Neo4j graph statistics
    """
    try:
        stats = graph_service.get_graph_stats()
        return GraphStatsSchema(**stats)
    except Exception as e:
        logger.error(f"Failed to get graph stats: {e}")
        return GraphStatsSchema(
            users=0,
            items=0,
            categories=0,
            owns_relationships=0,
            category_relationships=0
        )


@router.get('/exchanges/{exchange_cri}', auth=ProfileAuth())
@ratelimit(group='barter:detail', key=user_or_ip, rate='30/m')
def get_exchange(request, exchange_cri: str):
    """
    Get exchange details by ID
    """
    try:
        # Extract ULID from ID
        exchange_id = exchange_cri.replace('EXC-', '') if exchange_cri.startswith('EXC-') else exchange_cri

        exchange = Exchange.objects.prefetch_related(
            'swaps',
            'approvals',
            'category'
        ).get(id=exchange_id)

        return {
            'cri': exchange.id,
            'status': exchange.status,
            'user_chain': exchange.user_chain,
            'participants': exchange.participants,
            'category': exchange.category.id if exchange.category else None,
            'swaps_count': exchange.swaps.count(),
            'approvals': [
                {
                    'user_cri': approval.user.id,
                    'approved': approval.approved,
                    'created_at': approval.created_at.isoformat()
                }
                for approval in exchange.approvals.all()
            ],
            'created_at': exchange.created_at.isoformat(),
        }
    except Exchange.DoesNotExist:
        return {'error': 'Exchange not found'}, 404


@router.post('/exchanges/{exchange_cri}/approve', auth=ProfileAuth())
@ratelimit(group='barter:approve', key=user_or_ip, rate='30/m', method='POST')
@transaction.atomic
def approve_exchange(request, exchange_cri: str, data: ApprovalRequest):
    """
    Approve or reject an exchange

    Body:
        approved: true/false
        swap_cri: Optional specific swap ID
    """
    profile = request.auth

    try:
        # Extract ULID from ID
        exchange_id = exchange_cri.replace('EXC-', '') if exchange_cri.startswith('EXC-') else exchange_cri

        exchange = Exchange.objects.get(id=exchange_id)

        # Check if user is a participant
        if profile.id not in exchange.participants:
            return {'error': 'You are not a participant in this exchange'}, 403

        # Create or update approval
        approval, created = ExchangeApproval.objects.update_or_create(
            exchange=exchange,
            user=profile,
            defaults={
                'approved': data.approved
            }
        )

        # Reload exchange to get updated status
        exchange.refresh_from_db()

        return {
            'cri': approval.id,
            'exchange_cri': exchange.id,
            'approved': approval.approved,
            'exchange_status': exchange.status,
            'created': created
        }

    except Exchange.DoesNotExist:
        return {'error': 'Exchange not found'}, 404


@router.get('/my-exchanges', auth=ProfileAuth())
@ratelimit(group='barter:my_exchanges', key=user_or_ip, rate='30/m')
def get_my_exchanges(request, status: str = None):
    """
    Get exchanges involving current user

    Query Params:
        status: Optional status filter (PENDING, APPROVED, etc.)
    """
    profile = request.auth

    # Find exchanges where user is in the chain
    from django.db.models import Q

    # This is a bit complex - we need to filter JSONField for user ID
    # PostgreSQL jsonb_array_elements
    exchanges = Exchange.objects.filter(
        Q(user_chain__contains=[profile.id])
    )

    if status:
        exchanges = exchanges.filter(status=status)

    exchanges = exchanges.select_related('category').order_by('-created_at')[:50]

    return {
        'exchanges': [
            {
                'cri': exc.id,
                'status': exc.status,
                'participants_count': len(exc.participants),
                'user_chain': exc.user_chain,
                'category': exc.category.id if exc.category else None,
                'created_at': exc.created_at.isoformat(),
            }
            for exc in exchanges
        ]
    }
