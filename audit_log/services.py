"""
Audit Log services for cryptographic proof generation and management.
"""
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import git
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from .models import AuditBatch, PGPKeyPublication, TimestampProof

logger = logging.getLogger(__name__)


class PGPKeyringService:
    """Manage public PGP keyring in Git repository"""

    def __init__(self):
        self.repo_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git'
        self.keyring_path = self.repo_path / 'pgp-keyring'
        self.repo = git.Repo(self.repo_path)

    def publish_key(self, profile) -> Optional[PGPKeyPublication]:
        """
        Publish PGP public key to Git repository.

        Returns PGPKeyPublication if published, None if key already exists.
        """
        if not profile.pgp_public_key:
            return None

        fingerprint = self._extract_fingerprint(profile.pgp_public_key)
        if not fingerprint:
            return None

        # Check if already published
        existing = PGPKeyPublication.objects.filter(
            profile=profile,
            fingerprint=fingerprint,
            revoked=False
        ).first()

        if existing:
            return existing

        # Write key file
        key_file = self.keyring_path / f"{profile.id}.asc"
        key_file.write_text(profile.pgp_public_key)

        # Update metadata
        metadata_file = self.keyring_path / 'metadata.json'
        metadata = json.loads(metadata_file.read_text())

        metadata['keys'][profile.id] = {
            'fingerprint': fingerprint,
            'added_at': datetime.now(timezone.utc).isoformat(),
            'revoked': False,
        }

        metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        # Git commit
        self.repo.index.add([str(key_file), str(metadata_file)])
        commit = self.repo.index.commit(
            f"Add PGP key for profile {profile.id[:8]}\n\nFingerprint: {fingerprint}"
        )

        # Track publication
        publication = PGPKeyPublication.objects.create(
            profile=profile,
            fingerprint=fingerprint,
            public_key=profile.pgp_public_key,
            git_commit_hash=commit.hexsha,
        )

        return publication

    def revoke_key(self, profile, reason: str = None) -> bool:
        """Revoke PGP key (mark in metadata, keep file for historical verification)"""
        latest = PGPKeyPublication.objects.filter(
            profile=profile,
            revoked=False
        ).first()

        if not latest:
            return False

        # Update metadata (don't delete file - needed for historical verification)
        metadata_file = self.keyring_path / 'metadata.json'
        metadata = json.loads(metadata_file.read_text())

        if profile.id in metadata['keys']:
            metadata['keys'][profile.id]['revoked'] = True
            metadata['keys'][profile.id]['revoked_at'] = datetime.now(timezone.utc).isoformat()
            metadata['keys'][profile.id]['revocation_reason'] = reason or 'User requested'

            metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

            # Git commit
            self.repo.index.add([str(metadata_file)])
            self.repo.index.commit(
                f"Revoke PGP key for profile {profile.id[:8]}\n\nReason: {reason or 'User requested'}"
            )

        # Mark as revoked in DB
        latest.revoked = True
        latest.revoked_at = datetime.now(timezone.utc)
        latest.revocation_reason = reason
        latest.save()

        return True

    def _extract_fingerprint(self, public_key: str) -> Optional[str]:
        """Extract fingerprint from PGP public key using gpg"""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.asc', delete=False) as f:
                f.write(public_key)
                f.flush()

                result = subprocess.run(
                    ['gpg', '--with-colons', '--import-options', 'show-only', '--import', f.name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                # Parse gpg output for fingerprint
                for line in result.stdout.split('\n'):
                    if line.startswith('fpr:'):
                        return line.split(':')[9]

                return None
        except Exception as e:
            print(f"Error extracting fingerprint: {e}")
            return None
        finally:
            try:
                Path(f.name).unlink()
            except Exception:
                pass


class GitAuditService:
    """Batch git commit + OTS stamp for pending TimestampProofs"""

    OTS_BIN = str(Path(settings.BASE_DIR) / 'venv/bin/ots')

    def __init__(self):
        base = Path(settings.AUDIT_LOG_GIT_PATH)
        # PUBLIC mirror (pushed to Gitea): keyring + batch_commits + federation registry
        self.repo_path = base / 'public-git'
        self.batch_commits_path = self.repo_path / 'batch_commits'
        self.batch_commits_path.mkdir(parents=True, exist_ok=True)
        self.repo = git.Repo(self.repo_path)

        # LOCAL-ONLY repo for per-event JSON snapshots (contract/debt/verification
        # metadata). Deliberately has NO remote — events never leave this host.
        # The OTS proof anchors this repo's commit hash (a git Merkle root), and
        # only that hash + its .ots land in the public mirror; the event blobs do
        # not. See PK/audit-system.md.
        self.events_repo_path = base / 'events-local'
        self.events_path = self.events_repo_path / 'events'
        self.events_path.mkdir(parents=True, exist_ok=True)
        self.events_repo = self._ensure_events_repo()

    def _ensure_events_repo(self) -> 'git.Repo':
        """Open the local-only events repo, initializing it on first use. No remote."""
        try:
            return git.Repo(self.events_repo_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            repo = git.Repo.init(self.events_repo_path)
            with repo.config_writer() as cw:
                cw.set_value('user', 'name', 'Parahub Audit System')
                cw.set_value('user', 'email', 'audit@parahub.io')
            return repo

    def write_event_files(self, proofs) -> List[Path]:
        """
        Ensure an event JSON file exists on disk for every (batch-less) proof and
        return ALL their paths — so they get committed + stamped this run.

        Must NOT skip proofs that already have git_event_path: a proof can carry a
        path from a previous run that failed before AuditBatch creation (git commit
        or OTS stamp failed), leaving the file uncommitted/unstamped. Gating on
        "path already set" stranded such proofs permanently. We gate on batch__isnull
        (caller's query) and re-materialize any missing file here.
        """
        paths = []
        for proof in proofs:
            if proof.git_event_path:
                file_path = self.events_repo_path / proof.git_event_path
            else:
                day_dir = self.events_path / proof.created_at.strftime('%Y-%m-%d')
                day_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{proof.content_type.model}_{proof.object_id}.json"
                file_path = day_dir / filename
                proof.git_event_path = str(file_path.relative_to(self.events_repo_path))
                proof.save(update_fields=['git_event_path'])
            if not file_path.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(proof.data_json, encoding='utf-8')
            paths.append(file_path)
        return paths

    def commit_events(self, file_paths: List[Path], batch_label: str) -> str:
        """git add + commit event files to the LOCAL-ONLY events repo; returns commit hexsha."""
        if not file_paths:
            raise ValueError("No files to commit")
        str_paths = [str(p) for p in file_paths]
        last_exc = None
        for attempt in range(3):
            try:
                self.events_repo.index.add(str_paths)
                commit = self.events_repo.index.commit(
                    f"audit: batch event log {batch_label}\n\n{len(file_paths)} events"
                )
                return commit.hexsha
            except Exception as e:
                last_exc = e
                import time
                time.sleep(1)
        raise RuntimeError(f"git commit failed after 3 attempts: {last_exc}")

    @staticmethod
    def _batch_file_text(events_commit: str, registry_commit: Optional[str] = None) -> str:
        """
        Canonical content of batch_commits/{label}.txt — the EXACT bytes that get
        OTS-stamped. A batch anchors TWO git Merkle roots under one Bitcoin
        timestamp:
          registry_commit — HEAD of the PUBLIC repo (PGP keyring + federation
                            registry). It is checkout-able by anyone, so the
                            keyring is both Bitcoin-anchored AND independently
                            verifiable (`git checkout <registry_commit>`).
          events_commit  — HEAD of the LOCAL-ONLY event log (contract/debt
                            metadata). Only its hash is published; the event
                            blobs never leave the host.
        Legacy single-root batches (registry_commit=None) keep the bare-hash form
        so their already-stamped .ots proofs still verify byte-for-byte.
        """
        if registry_commit:
            return f"registry_commit {registry_commit}\nevents_commit {events_commit}\n"
        return events_commit + '\n'

    def write_commit_hash_file(self, events_commit: str, registry_commit: Optional[str],
                               batch_label: str) -> Path:
        """Write batch_commits/{batch_label}.txt with the batch's Merkle root(s)."""
        hash_file = self.batch_commits_path / f"{batch_label}.txt"
        hash_file.write_text(self._batch_file_text(events_commit, registry_commit), encoding='utf-8')
        return hash_file

    def stamp_commit_hash_file(self, hash_file_path: Path) -> Optional[bytes]:
        """Run ots stamp on the commit hash file; return .ots bytes or None."""
        ots_path = Path(str(hash_file_path) + '.ots')
        try:
            result = subprocess.run(
                [self.OTS_BIN, 'stamp', str(hash_file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"OTS stamp failed: {result.stderr}")
                return None
            if ots_path.exists():
                return ots_path.read_bytes()
            return None
        except Exception as e:
            print(f"Error running ots stamp: {e}")
            return None

    def commit_ots_proof(self, hash_file_path: Path, batch_label: str):
        """Commit the hash file + its .ots proof to the git repo."""
        ots_path = Path(str(hash_file_path) + '.ots')
        files_to_add = [str(hash_file_path)]
        if ots_path.exists():
            files_to_add.append(str(ots_path))
        self.repo.index.add(files_to_add)
        self.repo.index.commit(f"audit: OTS proof for batch {batch_label}")

    def verify_batch(self, batch: AuditBatch) -> bool:
        """
        Verify a batch's OTS proof against Bitcoin. Verifies the ACTUAL published
        artifact (batch_commits/*.txt) so it is format-agnostic — single-root
        (legacy) or dual-root (registry+events) both verify against their own
        stamped bytes. Falls back to reconstructing the legacy single-root content
        only if the published file is unavailable.
        """
        if not batch.ots_proof:
            return False
        published = (self.repo_path / batch.git_commit_file) if batch.git_commit_file else None
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            hash_file = tmp_path / 'commit.txt'
            ots_file = tmp_path / 'commit.txt.ots'
            if published and published.exists():
                hash_file.write_bytes(published.read_bytes())
            else:
                hash_file.write_text(self._batch_file_text(batch.git_commit_hash), encoding='utf-8')
            ots_file.write_bytes(bytes(batch.ots_proof))
            try:
                result = subprocess.run(
                    [self.OTS_BIN, 'verify', str(ots_file)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = result.stdout + result.stderr
                # Confirmed ONLY when a real Bitcoin block number is attested.
                # A pending stamp prints "Pending confirmation in Bitcoin
                # blockchain" — the bare substring "Bitcoin block" matches that
                # ("block"+"chain"), so we must require "Bitcoin block <digits>".
                import re
                m = re.search(r'Bitcoin block (\d+)', output)
                if m:
                    batch.bitcoin_block = int(m.group(1))
                    batch.verified_at = datetime.now(timezone.utc)
                    batch.save(update_fields=['bitcoin_block', 'verified_at'])
                    return True
                return False
            except Exception as e:
                logger.warning(f"Error verifying batch {batch.id}: {e}")
                return False


class ProofExportService:
    """Generate proof export packages for legal purposes"""

    def export_contract(self, contract) -> bytes:
        """
        Export contract with all cryptographic proofs as ZIP file.

        Returns ZIP file bytes containing:
        - contract.json (full data + signatures)
        - contract.json.asc (PGP signature)
        - contract.ots (OpenTimestamps proof)
        - README.txt (verification instructions)
        - verifications/ (identity proofs for parties)
        """
        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 1. Contract JSON
            contract_data = self._contract_to_dict(contract)
            zipf.writestr(
                f'contract_{contract.id}.json',
                json.dumps(contract_data, indent=2, ensure_ascii=False)
            )

            # 2. PGP signatures (if available)
            if hasattr(contract, 'creator_signature') and contract.creator_signature:
                zipf.writestr(
                    f'creator_signature.asc',
                    contract.creator_signature
                )
            if hasattr(contract, 'partner_signature') and contract.partner_signature:
                zipf.writestr(
                    f'partner_signature.asc',
                    contract.partner_signature
                )

            # 3. OpenTimestamps proof
            content_type = ContentType.objects.get_for_model(contract)
            ots_proof = TimestampProof.objects.select_related('batch').filter(
                content_type=content_type,
                object_id=contract.id
            ).first()

            self._write_batch_proof(zipf, ots_proof)

            # 4. Verification instructions
            readme = self._generate_readme('contract', contract.id)
            zipf.writestr('README.txt', readme)

            # 5. Verifications for parties (identity proof)
            verifications = self._export_verifications_for_contract(contract)
            if verifications:
                zipf.writestr(
                    'verifications.json',
                    json.dumps(verifications, indent=2, ensure_ascii=False)
                )

        zip_buffer.seek(0)
        return zip_buffer.read()

    def export_debt(self, debt) -> bytes:
        """Export debt with proofs (similar to contract)"""
        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Debt JSON
            debt_data = self._debt_to_dict(debt)
            zipf.writestr(
                f'debt_{debt.id}.json',
                json.dumps(debt_data, indent=2, ensure_ascii=False)
            )

            # PGP signatures
            if hasattr(debt, 'creditor_signature') and debt.creditor_signature:
                zipf.writestr('creditor_signature.asc', debt.creditor_signature)
            if hasattr(debt, 'debtor_signature') and debt.debtor_signature:
                zipf.writestr('debtor_signature.asc', debt.debtor_signature)

            # OTS proof
            content_type = ContentType.objects.get_for_model(debt)
            ots_proof = TimestampProof.objects.select_related('batch').filter(
                content_type=content_type,
                object_id=debt.id
            ).first()

            self._write_batch_proof(zipf, ots_proof)

            # README
            readme = self._generate_readme('debt', debt.id)
            zipf.writestr('README.txt', readme)

        zip_buffer.seek(0)
        return zip_buffer.read()

    def export_full_account(self, profile) -> bytes:
        """Export all user data (contracts, debts, verifications)"""
        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Export contracts
            from contracts.models import Contract
            contracts = Contract.objects.filter(
                creator=profile
            ) | Contract.objects.filter(partner=profile)

            for contract in contracts:
                contract_data = self._contract_to_dict(contract)
                zipf.writestr(
                    f'contracts/contract_{contract.id}.json',
                    json.dumps(contract_data, indent=2, ensure_ascii=False)
                )

            # Export debts
            from debts.models import Debt
            debts = Debt.objects.filter(creditor=profile) | Debt.objects.filter(debtor=profile)

            for debt in debts:
                debt_data = self._debt_to_dict(debt)
                zipf.writestr(
                    f'debts/debt_{debt.id}.json',
                    json.dumps(debt_data, indent=2, ensure_ascii=False)
                )

            # Export verifications
            from identity.models import Verification
            verifications_received = Verification.objects.filter(verified_profile=profile)
            verifications_issued = Verification.objects.filter(verifier=profile)

            zipf.writestr(
                'verifications/received.json',
                json.dumps([self._verification_to_dict(v) for v in verifications_received], indent=2, ensure_ascii=False)
            )
            zipf.writestr(
                'verifications/issued.json',
                json.dumps([self._verification_to_dict(v) for v in verifications_issued], indent=2, ensure_ascii=False)
            )

            # Export items (marketplace ads) with photos
            from market.models import Item
            items = Item.objects.filter(owner=profile).prefetch_related('images', 'tags')

            for item in items:
                item_data = self._item_to_dict(item)
                zipf.writestr(
                    f'items/item_{item.id}.json',
                    json.dumps(item_data, indent=2, ensure_ascii=False)
                )

                # Export item photos
                for img in item.images.all():
                    try:
                        if img.image and img.image.path:
                            import os
                            if os.path.exists(img.image.path):
                                # Get file extension
                                ext = os.path.splitext(img.image.name)[1]
                                # Add to ZIP with structured path
                                zipf.write(
                                    img.image.path,
                                    f'items/item_{item.id}/photos/{img.order}{ext}'
                                )
                    except Exception as e:
                        logger.warning(f"Failed to export image {img.id} for item {item.id}: {e}")

            # PGP key
            if profile.pgp_public_key:
                zipf.writestr('pgp/public_key.asc', profile.pgp_public_key)

                pub = PGPKeyPublication.objects.filter(profile=profile, revoked=False).first()
                if pub:
                    zipf.writestr(
                        'pgp/fingerprint.txt',
                        f"{pub.fingerprint}\nPublished: {pub.published_at.isoformat()}"
                    )

            # README
            readme = self._generate_readme('full', profile.id)
            zipf.writestr('README.txt', readme)

        zip_buffer.seek(0)
        return zip_buffer.read()

    def _write_batch_proof(self, zipf, ots_proof):
        """
        Add the OTS-stamped batch file + its Bitcoin proof to the export ZIP so the
        timestamp is independently verifiable straight from the ZIP:
            ots verify batch_commit.txt.ots
        `batch_commit.txt` is the exact stamped artifact (dual-root: registry +
        events commit hashes), required because the dual-root content can't be
        reconstructed from a single hash. `batch_proof_info.txt` is the human-
        readable summary.
        """
        if not (ots_proof and ots_proof.batch_id and ots_proof.batch and ots_proof.batch.ots_proof):
            return
        batch = ots_proof.batch
        stamped = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git' / batch.git_commit_file
        if stamped.exists():
            zipf.writestr('batch_commit.txt', stamped.read_text(encoding='utf-8'))
        zipf.writestr('batch_commit.txt.ots', bytes(batch.ots_proof))
        zipf.writestr('batch_proof_info.txt', (
            f"Git commit (event log): {batch.git_commit_hash}\n"
            f"Event file: {ots_proof.git_event_path}\n"
            f"Stamped: {batch.stamped_at.isoformat()}\n"
            f"Bitcoin block: {batch.bitcoin_block or 'pending'}\n"
        ))

    def _contract_to_dict(self, contract) -> Dict:
        """Convert contract to JSON-serializable dict"""
        return {
            'id': contract.id,
            'object_type': 'contract',
            'created_at': contract.created_at.isoformat(),
            'creator_id': contract.creator_id,
            'partner_id': contract.partner_id,
            'arbiter_id': contract.arbiter_id,
            'status': contract.status,
            'terms': getattr(contract, 'terms', ''),
            'signatures': {
                'creator': contract.creator_signature,
                'partner': contract.partner_signature,
            },
            'completed_at': contract.completed_at.isoformat() if hasattr(contract, 'completed_at') and contract.completed_at else None,
        }

    def _debt_to_dict(self, debt) -> Dict:
        """Convert debt to JSON-serializable dict"""
        return {
            'id': debt.id,
            'object_type': 'debt',
            'created_at': debt.created_at.isoformat(),
            'creditor_id': debt.creditor_id,
            'debtor_id': debt.debtor_id,
            'amount': str(debt.amount),
            'remaining_amount': str(debt.remaining_amount),
            'currency': debt.currency,
            'description': debt.description,
            'status': debt.status,
            'confirmed_by_creditor_at': debt.confirmed_by_creditor_at.isoformat() if debt.confirmed_by_creditor_at else None,
            'confirmed_by_debtor_at': debt.confirmed_by_debtor_at.isoformat() if debt.confirmed_by_debtor_at else None,
        }

    def _verification_to_dict(self, verification) -> Dict:
        """Convert verification to JSON-serializable dict"""
        return {
            'id': verification.id,
            'object_type': 'verification',
            'created_at': verification.created_at.isoformat(),
            'verifier_id': verification.verifier_id,
            'verified_profile_id': verification.verified_profile_id,
            'verification_method': verification.verification_method,
            'signature': verification.signature,
            'is_active': verification.is_active,
        }

    def _item_to_dict(self, item) -> Dict:
        """Convert marketplace item to JSON-serializable dict"""
        return {
            'id': item.id,
            'object_type': 'item',
            'created_at': item.created_at.isoformat(),
            'updated_at': item.updated_at.isoformat(),
            'owner_id': item.owner_id,
            'title': item.title,
            'description': item.description,
            'type': item.type,
            'spec_data': item.spec_data,
            'pricing_options': item.pricing_options,
            'accepted_payment_methods': item.accepted_payment_methods,
            'is_active': item.is_active,
            'category_id': item.category_id,
            'tags': [tag.name for tag in item.tags.all()],
            'location': {
                'lat': item.location.y if item.location else None,
                'lon': item.location.x if item.location else None,
            } if item.location else None,
            'images': [
                {
                    'id': img.id,
                    'order': img.order,
                    'caption': img.caption,
                    'filename': f'{img.order}{os.path.splitext(img.image.name)[1]}',
                }
                for img in item.images.all()
            ],
        }

    def _export_verifications_for_contract(self, contract) -> List[Dict]:
        """Export verifications for contract parties (for identity proof)"""
        from identity.models import Verification

        verifications = []
        parties = [contract.creator_id]
        if contract.partner_id:
            parties.append(contract.partner_id)
        if contract.arbiter_id:
            parties.append(contract.arbiter_id)

        for party_id in parties:
            party_verifications = Verification.objects.filter(verified_profile_id=party_id)[:10]
            verifications.extend([self._verification_to_dict(v) for v in party_verifications])

        return verifications

    def _generate_readme(self, export_type: str, object_id: str) -> str:
        """Generate README with verification instructions"""
        return f"""
Parahub Cryptographic Proof Export
===================================

Export Type: {export_type}
Export Date: {datetime.now(timezone.utc).isoformat()}
Object ID: {object_id}

VERIFICATION INSTRUCTIONS
-------------------------

1. Verify PGP Signatures:

   # Public keys live in the audit keyring, one file per PROFILE id.
   # The party profile IDs are in the exported .json files. Browse:
   #   https://git.parahub.io/audit/parahub-registry/src/branch/master/pgp-keyring
   curl https://git.parahub.io/audit/parahub-registry/raw/branch/master/pgp-keyring/<PROFILE_ID>.asc | gpg --import

   # Verify a detached signature
   gpg --verify creator_signature.asc

2. Verify OpenTimestamps Proof:

   # Install opentimestamps-client
   pip install opentimestamps-client

   # Verify the Bitcoin timestamp of the batch this object was anchored in
   ots verify batch_commit.txt.ots

3. Verify Data Integrity:

   # Calculate SHA256 hash
   sha256sum *.json

   # Compare with hash in .ots file

LEGAL NOTICE - Portugal / EU
----------------------------

PGP Signatures:
- NOT Qualified Electronic Signatures (QES) under eIDAS Regulation (EU 910/2014)
- CAN be considered Advanced Electronic Signatures (AES) under eIDAS
- Accepted by Portuguese courts as evidence in civil disputes
- Similar to email correspondence (established case law)
- eIDAS Article 25(1): Electronic signatures cannot be denied legal effect solely
  because they are electronic

OpenTimestamps:
- Cryptographic proof that document existed NO LATER than specific time
- Anchored in Bitcoin blockchain (cannot be forged)
- Independent verification possible without parahub access

Recommendations:
- For amounts <€5,000: PGP + OpenTimestamps usually sufficient
- For amounts >€5,000: Consider notarization at cartório (notary office)
- For significant contracts: Consult lawyer about eIDAS compliance
- Portuguese Civil Code (Código Civil) Article 363º accepts electronic evidence

Legal References:
- eIDAS Regulation (EU) 910/2014
- Portuguese implementation: Decreto-Lei n.º 12/2021

PRIVACY
-------

This export is PRIVATE and intended only for parties to the agreement.
Do NOT publish this data publicly.

CONTACT
-------

Support: support@parahub.io
Website: https://parahub.io
"""
