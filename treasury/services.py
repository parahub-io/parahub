"""
Treasury Service — participatory budget allocation with median voting.
Per-establishment: every method takes an Establishment instance.
"""
import hashlib
import json
import statistics
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple, Optional

from django.db import transaction
from django.utils import timezone

from identity.models import Profile
from geo.models import Establishment, EstablishmentMembership
from .models import BudgetCategory, BudgetAllocation, BudgetEpoch, TreasuryAuditLog

logger = logging.getLogger(__name__)


class TreasuryService:

    @staticmethod
    def get_eligible_profiles(establishment: Establishment):
        """QuerySet of profiles eligible to vote based on establishment's treasury_eligible_levels."""
        levels = establishment.treasury_eligible_levels or []
        if not levels:
            return Profile.objects.none()
        return Profile.objects.filter(
            establishment_memberships__establishment=establishment,
            establishment_memberships__membership_level__in=levels,
        ).distinct()

    @staticmethod
    def is_eligible(profile: Profile, establishment: Establishment) -> bool:
        levels = establishment.treasury_eligible_levels or []
        if not levels:
            return False
        return EstablishmentMembership.objects.filter(
            profile=profile,
            establishment=establishment,
            membership_level__in=levels,
        ).exists()

    @staticmethod
    def get_active_categories(establishment: Establishment):
        return BudgetCategory.objects.filter(
            establishment=establishment, is_active=True
        ).order_by('order', 'name')

    @staticmethod
    def validate_allocations(allocations: dict, establishment: Establishment) -> Tuple[bool, Optional[str]]:
        """
        Validate allocation dict: {category_id: float_percent}.
        Returns (is_valid, error_msg).
        """
        active_ids = set(
            BudgetCategory.objects.filter(
                establishment=establishment, is_active=True
            ).values_list('id', flat=True)
        )

        alloc_ids = set(allocations.keys())

        # All active categories must be present
        missing = active_ids - alloc_ids
        if missing:
            return False, f"Missing categories: {missing}"

        # No unknown categories
        unknown = alloc_ids - active_ids
        if unknown:
            return False, f"Unknown categories: {unknown}"

        # All values >= 0
        for cat_id, value in allocations.items():
            try:
                v = Decimal(str(value))
            except Exception:
                return False, f"Invalid value for {cat_id}: {value}"
            if v < 0:
                return False, f"Negative value for {cat_id}: {value}"

        # Sum must be 100 (± 0.01 tolerance)
        total = sum(Decimal(str(v)) for v in allocations.values())
        if abs(total - Decimal('100')) > Decimal('0.01'):
            return False, f"Sum must be 100.0, got {total}"

        return True, None

    @staticmethod
    def calculate_current_medians(establishment: Establishment) -> List[Dict]:
        """
        Calculate median allocation for each active category across all eligible voters.
        Normalizes the resulting medians to sum to 100%.
        """
        categories = BudgetCategory.objects.filter(
            establishment=establishment, is_active=True
        ).order_by('order', 'name')
        eligible_ids = set(
            TreasuryService.get_eligible_profiles(establishment).values_list('id', flat=True)
        )

        # Get all allocations from eligible profiles for this establishment
        allocations = BudgetAllocation.objects.filter(
            establishment=establishment,
            profile_id__in=eligible_ids,
        ).select_related('profile')

        # Build per-category value lists
        cat_values: Dict[str, List[float]] = {cat.id: [] for cat in categories}
        for alloc in allocations:
            for cat_id, value in alloc.allocations.items():
                if cat_id in cat_values:
                    cat_values[cat_id].append(float(value))

        # Calculate medians
        results = []
        raw_medians = {}
        for cat in categories:
            values = cat_values.get(cat.id, [])
            if values:
                median_val = statistics.median(values)
            else:
                median_val = 0.0
            raw_medians[cat.id] = median_val
            results.append({
                'category_id': cat.id,
                'slug': cat.slug,
                'name': cat.name,
                'icon': cat.icon,
                'median_percent': median_val,
                'voter_count': len(values),
            })

        # Normalize to 100%
        total_median = sum(raw_medians.values())
        if total_median > 0:
            for r in results:
                r['median_percent'] = round(r['median_percent'] / total_median * 100, 1)

        return results

    @staticmethod
    @transaction.atomic
    def update_allocation(profile: Profile, establishment: Establishment,
                          allocations: dict, pgp_signature: str = '',
                          signed_payload: dict = None):
        """Create or update budget allocation for a profile in an establishment."""
        obj, created = BudgetAllocation.objects.update_or_create(
            profile=profile,
            establishment=establishment,
            defaults={
                'allocations': allocations,
                'pgp_signature': pgp_signature,
                'signed_payload': signed_payload or {},
            }
        )
        return obj

    @staticmethod
    @transaction.atomic
    def freeze_epoch(establishment: Establishment, label: str,
                     start_date, end_date) -> BudgetEpoch:
        """Create a BudgetEpoch snapshot of all current allocations for an establishment."""
        eligible_profiles = TreasuryService.get_eligible_profiles(establishment)
        eligible_ids = set(eligible_profiles.values_list('id', flat=True))
        total_eligible = len(eligible_ids)

        # Get all eligible allocations for this establishment
        allocations = BudgetAllocation.objects.filter(
            establishment=establishment,
            profile_id__in=eligible_ids,
        ).select_related('profile')
        total_participants = allocations.count()

        # Build individual snapshot
        individual_snapshot = []
        for alloc in allocations:
            individual_snapshot.append({
                'profile_id': alloc.profile.id,
                'hna': alloc.profile.hna,
                'allocations': alloc.allocations,
                'pgp_signature': alloc.pgp_signature,
            })

        # Calculate medians
        frozen_medians = TreasuryService.calculate_current_medians(establishment)

        # Calculate Merkle root from individual allocations
        merkle_root = TreasuryService._calculate_merkle_root(individual_snapshot)

        epoch = BudgetEpoch.objects.create(
            establishment=establishment,
            label=label,
            start_date=start_date,
            end_date=end_date,
            status=BudgetEpoch.Status.FINALIZED,
            frozen_allocations=frozen_medians,
            total_eligible=total_eligible,
            total_participants=total_participants,
            merkle_root=merkle_root,
            individual_allocations_snapshot=individual_snapshot,
            finalized_at=timezone.now(),
        )

        return epoch

    @staticmethod
    def _calculate_merkle_root(individual_snapshot: List[Dict]) -> str:
        """Calculate SHA256 Merkle root from individual allocations."""
        if not individual_snapshot:
            return hashlib.sha256(b'empty').hexdigest()

        # Leaf hashes
        leaves = []
        for entry in sorted(individual_snapshot, key=lambda x: x['profile_id']):
            leaf_data = json.dumps(entry, sort_keys=True).encode('utf-8')
            leaves.append(hashlib.sha256(leaf_data).hexdigest())

        # Build tree
        while len(leaves) > 1:
            next_level = []
            for i in range(0, len(leaves), 2):
                left = leaves[i]
                right = leaves[i + 1] if i + 1 < len(leaves) else left
                combined = hashlib.sha256(f"{left}{right}".encode('utf-8')).hexdigest()
                next_level.append(combined)
            leaves = next_level

        return leaves[0]

    @staticmethod
    def get_participation_stats(establishment: Establishment) -> Dict:
        """Get participation statistics for an establishment."""
        eligible = TreasuryService.get_eligible_profiles(establishment)
        total_eligible = eligible.count()
        eligible_ids = set(eligible.values_list('id', flat=True))
        total_participants = BudgetAllocation.objects.filter(
            establishment=establishment,
            profile_id__in=eligible_ids,
        ).count()

        return {
            'total_eligible': total_eligible,
            'total_participants': total_participants,
            'participation_percent': round(
                total_participants / total_eligible * 100, 1
            ) if total_eligible > 0 else 0,
        }


class TreasuryAuditService:
    """Merkle-chain audit log service — scoped per establishment."""

    @staticmethod
    def create_log_entry(
        establishment: Establishment,
        action: str,
        payload: dict,
        actor: Optional[Profile] = None,
        pgp_signature: str = ''
    ) -> TreasuryAuditLog:
        """Create audit log entry with Merkle chain hash scoped per establishment."""
        previous_log = TreasuryAuditLog.objects.filter(
            establishment=establishment
        ).order_by('-timestamp').first()
        previous_hash = previous_log.current_log_hash if previous_log else None

        entry_timestamp = timezone.now()

        hash_data = {
            'previous_hash': previous_hash,
            'action': action,
            'actor_id': actor.id if actor else None,
            'establishment_id': establishment.id,
            'payload': payload,
            'timestamp': entry_timestamp.isoformat()
        }
        current_hash = hashlib.sha256(
            json.dumps(hash_data, sort_keys=True).encode('utf-8')
        ).hexdigest()

        log_entry = TreasuryAuditLog(
            establishment=establishment,
            action=action,
            actor=actor,
            previous_log_hash=previous_hash,
            current_log_hash=current_hash,
            payload=payload,
            pgp_signature=pgp_signature,
            timestamp=entry_timestamp,
        )
        log_entry.save()

        return log_entry

    @staticmethod
    def verify_merkle_chain(establishment: Establishment) -> tuple[bool, str | None]:
        """Verify Merkle chain integrity for an establishment's audit log."""
        logs = TreasuryAuditLog.objects.filter(
            establishment=establishment
        ).order_by('timestamp')

        previous_hash = None
        for log in logs:
            if log.previous_log_hash != previous_hash:
                return False, f"Chain break at entry {log.id}: expected previous_hash {previous_hash}, got {log.previous_log_hash}"

            hash_data = {
                'previous_hash': previous_hash,
                'action': log.action,
                'actor_id': log.actor_id,
                'establishment_id': establishment.id,
                'payload': log.payload,
                'timestamp': log.timestamp.isoformat()
            }
            calculated_hash = hashlib.sha256(
                json.dumps(hash_data, sort_keys=True).encode('utf-8')
            ).hexdigest()

            if calculated_hash != log.current_log_hash:
                return False, f"Hash mismatch at entry {log.id}: expected {calculated_hash}, got {log.current_log_hash}"

            previous_hash = log.current_log_hash

        return True, None
