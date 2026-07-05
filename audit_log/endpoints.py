"""
API endpoints for proof export.
"""
from ninja import Router
from django.http import HttpResponse
from typing import Dict, Any
import logging

from django.conf import settings

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from contracts.models import Contract
from debts.models import Debt
from .services import ProofExportService
from .models import ProofExport, AuditBatch, TimestampProof, PGPKeyPublication
import hashlib

logger = logging.getLogger(__name__)

router = Router(tags=["audit"])


@router.get("/export/contract/{contract_id}", auth=ProfileAuth(), response=None)
@ratelimit(group='audit:export_contract', key=user_or_ip, rate='10/m')
def export_contract_proof(request, contract_id: str):
    """
    Export cryptographic proof package for a specific contract.

    Returns ZIP file containing:
    - contract.json (full data + signatures)
    - creator_signature.asc / partner_signature.asc (PGP signatures)
    - contract.ots (OpenTimestamps proof)
    - verifications.json (identity proofs for parties)
    - README.txt (verification instructions)
    """
    try:
        # Get contract and verify access
        contract = Contract.objects.get(id=contract_id)

        # Check permissions - only parties can export
        if request.auth not in [contract.creator, contract.partner, contract.arbiter]:
            return HttpResponse("Forbidden", status=403)

        # Generate proof package
        export_service = ProofExportService()
        zip_data = export_service.export_contract(contract)

        # Track export
        file_hash = hashlib.sha256(zip_data).hexdigest()
        ProofExport.objects.create(
            profile=request.auth,
            export_type='contract',
            object_ids=[contract_id],
            file_hash=file_hash
        )

        # Return ZIP file
        response = HttpResponse(zip_data, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="contract_{contract_id}_proof.zip"'
        return response

    except Contract.DoesNotExist:
        return HttpResponse("Contract not found", status=404)
    except Exception as e:
        logger.error(f"Error exporting contract proof: {e}")
        return HttpResponse("Export failed", status=500)


@router.get("/export/debt/{debt_id}", auth=ProfileAuth(), response=None)
@ratelimit(group='audit:export_debt', key=user_or_ip, rate='10/m')
def export_debt_proof(request, debt_id: str):
    """
    Export cryptographic proof package for a specific debt.

    Returns ZIP file containing:
    - debt.json (full data + signatures)
    - creditor_signature.asc / debtor_signature.asc (PGP signatures)
    - debt.ots (OpenTimestamps proof)
    - README.txt (verification instructions)
    """
    try:
        # Get debt and verify access
        debt = Debt.objects.get(id=debt_id)

        # Check permissions - only creditor and debtor can export
        if request.auth not in [debt.creditor, debt.debtor]:
            return HttpResponse("Forbidden", status=403)

        # Generate proof package
        export_service = ProofExportService()
        zip_data = export_service.export_debt(debt)

        # Track export
        file_hash = hashlib.sha256(zip_data).hexdigest()
        ProofExport.objects.create(
            profile=request.auth,
            export_type='debt',
            object_ids=[debt_id],
            file_hash=file_hash
        )

        # Return ZIP file
        response = HttpResponse(zip_data, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="debt_{debt_id}_proof.zip"'
        return response

    except Debt.DoesNotExist:
        return HttpResponse("Debt not found", status=404)
    except Exception as e:
        logger.error(f"Error exporting debt proof: {e}")
        return HttpResponse("Export failed", status=500)


@router.get("/export/full", auth=ProfileAuth(), response=None)
@ratelimit(group='audit:export_full', key=user_or_ip, rate='5/m')
def export_full_account(request):
    """
    Export full account data with all cryptographic proofs.

    Returns ZIP file containing:
    - contracts/ (all contracts user is party to)
    - debts/ (all debts user is party to)
    - verifications/ (received and issued verifications)
    - pgp/ (public key and fingerprint)
    - README.txt (verification instructions)
    """
    try:
        # Generate full export
        export_service = ProofExportService()
        zip_data = export_service.export_full_account(request.auth)

        # Get all object IDs for tracking
        from contracts.models import Contract
        from identity.models import Verification
        from debts.models import Debt
        from market.models import Item

        contracts = Contract.objects.filter(creator=request.auth) | Contract.objects.filter(partner=request.auth)
        debts = Debt.objects.filter(creditor=request.auth) | Debt.objects.filter(debtor=request.auth)
        verifications = Verification.objects.filter(verified_profile=request.auth) | Verification.objects.filter(verifier=request.auth)
        items = Item.objects.filter(owner=request.auth)

        object_ids = (
            list(contracts.values_list('id', flat=True)) +
            list(debts.values_list('id', flat=True)) +
            list(verifications.values_list('id', flat=True)) +
            list(items.values_list('id', flat=True))
        )

        # Track export
        file_hash = hashlib.sha256(zip_data).hexdigest()
        ProofExport.objects.create(
            profile=request.auth,
            export_type='full',
            object_ids=object_ids,
            file_hash=file_hash
        )

        # Return ZIP file
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(zip_data, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="parahub_{request.auth.id[:8]}_export_{timestamp}.zip"'
        return response

    except Exception as e:
        logger.error(f"Error exporting full account: {e}")
        return HttpResponse("Export failed", status=500)


@router.get("/export/history", auth=ProfileAuth(), response=Dict[str, Any])
@ratelimit(group='audit:export_history', key=user_or_ip, rate='30/m')
def get_export_history(request):
    """
    Get user's export history.

    Returns list of all exports with timestamps and file hashes.
    """
    exports = ProofExport.objects.filter(profile=request.auth)

    return {
        'exports': [
            {
                'export_type': exp.export_type,
                'created_at': exp.created_at.isoformat(),
                'file_hash': exp.file_hash,
                'object_count': len(exp.object_ids)
            }
            for exp in exports
        ]
    }


@router.get("/anchoring", auth=None, response=Dict[str, Any])
@ratelimit(group='audit:anchoring', key='ip', rate='60/m')
def anchoring_status(request):
    """
    Public transparency: aggregate OTS/Bitcoin anchoring status.

    Read-only counters + latest batch. No PII — only public aggregates and the
    node's own commit/block references. Powers the /docs/crypto live status block.
    """
    latest = AuditBatch.objects.order_by('-stamped_at').first()
    latest_data = None
    if latest:
        latest_data = {
            'git_commit_hash': latest.git_commit_hash,
            'bitcoin_block': latest.bitcoin_block,
            'event_count': latest.event_count,
            'stamped_at': latest.stamped_at.isoformat() if latest.stamped_at else None,
            'verified_at': latest.verified_at.isoformat() if latest.verified_at else None,
        }

    return {
        'enabled': bool(getattr(settings, 'OPENTIMESTAMPS_ENABLED', False)),
        'keys_published': PGPKeyPublication.objects.filter(revoked=False).count(),
        'proofs_anchored': TimestampProof.objects.filter(batch__isnull=False).count(),
        'proofs_pending': TimestampProof.objects.filter(batch__isnull=True).count(),
        'batches': AuditBatch.objects.count(),
        'batches_confirmed': AuditBatch.objects.filter(bitcoin_block__isnull=False).count(),
        'latest_batch': latest_data,
    }
