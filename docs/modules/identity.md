# Identity and Trust

Decentralized identity system built on ULIDs, multi-profile accounts, Web of Trust verification, and client-side PGP cryptography.

## Accounts and Profiles

### Account
Extends Django's `AbstractUser`. One account per person. Handles authentication (email/password or Google OAuth). Human-readable address: `username@parahub.io` (also the Matrix ID: `@username:parahub.io`).

Username is auto-generated on signup (adjective-noun pattern, e.g., `daring-water`). OAuth users must choose their username before Matrix account creation (Matrix IDs are immutable).

Account flags:
- `is_test` -- test accounts used by E2E tests (e.g., alice, bob, charlie)
- `is_bot` -- AI agent accounts (e.g., pixel, forge, scout, vera)
- Both flags hidden from public profile/item/event listings for non-staff users

### Profiles
One account can have up to 7 profiles (1 primary + 6 additional):
- **Personal** -- real identity, main profile
- **Pseudonymous** -- alternative identity for privacy

Each profile has its own reputation, items, contracts, partners, and activity history. Users can switch between profiles.

### Partners
One-way contact relationships. Invite via token, QR code, or quick signup link. Accepting creates mutual partnership. Auto-creates Matrix DM between partners.

## Web of Trust (WoT)

### Verification
New accounts start unverified with limited permissions. To get verified:
1. Meet 3+ already-verified users (in person or through trusted channels)
2. Each verifier confirms the new user's identity
3. Once verified, the user can verify others

### Sybil Defense
If a verified account is proven fake, **all verifiers who vouched for it are automatically banned**. This makes false verification personally costly and creates social pressure for honest verification.

### Trust Levels

| Level | Requirements | Key Permissions |
|-------|-------------|-----------------|
| Anonymous | None | Browse public content |
| Registered | Account created | Create items (limited) |
| Verified | 3+ WoT confirmations | Full marketplace access, voting |
| Apoiante | Association supporter | Extended quotas |
| Efetivo | Full association member | Governance participation |
| Fundador | Founding member | Historical status |
| Admin | Appointed | System administration |

## PGP Cryptography

### Client-Side Only
- Keys generated in the browser via OpenPGP.js
- Private keys **never** sent to server
- Server stores only public keys
- Key rotation supported with full history tracking

### What Requires Signatures
- Contracts: both parties sign the SHA256 hash
- Governance votes: each vote is PGP-signed
- Debt records: creation and settlement confirmation
- Treasury allocations: budget proposals

### Optional: BIP39 Derivation
Users can derive their PGP keypair from a BIP39 mnemonic seed. Same seed also generates the Lightning wallet. One backup phrase covers both crypto identity and payments.

## Contracts

### P2P Contracts
Digital agreements between two parties:
1. Creator drafts contract with terms (optional arbiter selection, optional subject property)
2. Both parties review and PGP-sign the contract hash
3. Dual completion: both must confirm fulfillment
4. Arbitration available if dispute arises

Client-side SHA256 hash verification ensures document integrity. Matrix DM auto-created for contract discussion. Contracts can link to marketplace Items (auto-deactivated on completion) and Properties (`subject_property` FK). Inline contract editor with clause templates. Collapsible card UI for managing multiple contracts.

### Arbitration
- **ArbiterProfile**: qualified arbitrator registration with specialization
- **ArbitrationVerdict**: typed outcome (favor_creator, favor_partner, partial, dismissed) with amounts and currency
- **Three-level escalation**: P2P resolution -> Consumer arbitration center (CAC/CICAP) -> Court
- **Clause templates**: auto-generated via API with Portuguese law context (Lei references), configurable by type/city/arbiter/language

### Reviews
After contract completion, both parties can leave reviews that affect reputation.

## Social Recovery

Account recovery through trusted contacts. M-of-N scheme: designate N trusted contacts, any M can authorize recovery. No dependency on email or phone number.

## Federation

Git-based multi-node federation enables profile migration and cross-node trust:

- **Node Identity**: Each Parahub instance has an Ed25519 PGP key that signs all registry records
- **Profile Migration**: 4 signatures required (old user, new user, old node, new node) with OTS Bitcoin anchoring
- **Cross-Node WoT**: Federated verifications stored in git, synchronized between peers
- **Peer Discovery**: Bootstrap + automatic sync via WebSocket federation client

See [Federation module](federation.md) for full details.

## Technical Details

- **Models**: `identity/models.py` -- Account, Profile, Partner, Verification, Contract, ContractReview, ArbiterProfile, ArbitrationVerdict, SocialRecovery, PsychProfile, PGPKeyHistory, ProfileNote, ProfileVerificationPhoto (128-d face embedding for dedup)
- **API**: `parahub/endpoints/profiles.py`, `parahub/endpoints/partners.py`, `parahub/endpoints/contracts.py`, `parahub/endpoints/wot.py`
- **Auth**: `parahub/auth.py` -- ProfileAuth, GlobalAuth, OptionalProfileAuth
- **OIDC**: `oidc_provider/` -- OAuth/OIDC provider for Matrix, Traccar, Gitea SSO
- **Federation**: `parahub/services/federation_client.py` -- FederationClient; `audit_log/registry.py` -- RegistryService
