# Security

## Trust Model: Web of Trust

Parahub uses a decentralized trust model instead of centralized KYC. Identity verification is a social process -- real humans vouch for other real humans.

### Verification Process
- New accounts are unverified (limited permissions)
- 3 or more verified users must confirm a new user's identity (in person or through trusted channels)
- Once verified, the user can verify others
- **Sybil defense**: if a verified account is proven fake, all verifiers who vouched for it are automatically banned
- This creates personal accountability -- verifying someone is a commitment

### Trust Levels
10 roles with granular permissions: Anonymous -> Authenticated -> Has Profile -> Personal -> Pseudonymous -> Verified -> Apoiante -> Efetivo -> Fundador -> Admin. Each level unlocks additional capabilities (posting items, creating events, acting as arbitrator, etc.).

## Cryptography

### PGP (Client-Side)
- Keys generated in the browser via OpenPGP.js
- Private keys **never** leave the client device
- Server stores only public keys
- PGP key history is tracked (key rotation supported)
- Optional: derive PGP keypair from BIP39 mnemonic seed

### What Requires PGP Signatures
- **Contracts**: both parties sign the contract hash
- **Governance votes**: each vote is PGP-signed for audit
- **Debt records**: creation and settlement
- **Treasury allocations**: budget proposals
- Server verifies PGP signatures for these operations

### Lightning Wallet
- Breez SDK Spark runs entirely in the browser (WASM)
- Non-custodial: the platform never holds funds or keys
- Seed stored in browser localStorage (security relies on device-level protection)

## Audit Trail

### Cryptographic Proof Chain
1. **PGP Signatures**: every critical operation signed by the user
2. **Git Merkle Tree**: events committed to a Git repository, creating a Merkle tree of all activity
3. **OpenTimestamps**: Git commit hashes anchored to Bitcoin blockchain via OTS calendar servers. One Bitcoin anchor covers all events through the Git Merkle tree
4. **Matrix E2E Backup**: encrypted message history retained
5. **Export**: ZIP archive with all proofs, suitable for court proceedings

### Automated Anchoring
- Django signals create `TimestampProof` records on critical events
- Systemd timer runs every 10 minutes: `git commit` events -> `ots stamp` commit hash -> `AuditBatch`
- Verification timer checks pending OTS proofs against Bitcoin blockchain
- Coverage: contracts, debts, verifications, governance votes

### Governance Audit
Polls use a Merkle audit log. Each vote creates an entry with a hash chain linking to all previous votes. Transitive delegation chains are recorded and verifiable.

## Authentication

### Session + JWT
- Django session cookie set on login (Google OAuth or email/password)
- JWT token obtained via `GET /api/v1/auth/session/token/` (30-minute lifetime)
- Both required for authenticated API calls
- JWT stored in memory only (not localStorage, not cookies)

### PGP Authentication
- For critical operations, requests include PGP signature of the payload
- Server verifies signature against stored public key
- PGP nonce with 1-hour TTL prevents replay attacks (timestamp drift limited to 5 minutes)

### WebSocket Auth
- Cookie-based: `ws_token` cookie set before WebSocket connection
- Token validated on connect, Profile resolved
- No query parameter tokens (avoids URL logging)

### OIDC Provider
Parahub acts as OIDC identity provider for:
- Matrix (Synapse) -- chat SSO
- Traccar -- GPS tracking SSO
- Gitea -- Git hosting SSO

Account ID (not Profile ID) used in `sub` claim to prevent duplicates across multiple profiles.

## Rate Limiting

Rate limits applied per-endpoint based on sensitivity. Quota system for AI analysis (30 analyses/day). Redis-backed counters with automatic TTL.

## Privacy

### Data Minimization
- Minimal PII collected
- Location fuzzing: public display uses 100m precision
- GeoIP for country detection, not precise location tracking
- No behavioral tracking or profiling

### Encryption
- Matrix messages: E2E encrypted (Megolm/Olm)
- Lightning wallet: client-side encryption
- All traffic: TLS (nginx)

### Data Portability
Users can export their data. Contracts and audit proofs available as downloadable ZIP files.

## Infrastructure Security

- All secrets in environment variables (not code)
- `rotate-secrets.sh` for credential rotation
- PostgreSQL automated backups via systemd timer
- Uptime Kuma monitors 30 service endpoints
- Auto-heal: systemd restarts failed services
- No default passwords -- all generated on deployment

## Threat Mitigation

| Threat | Defense |
|--------|---------|
| Sybil attacks | WoT with triple-verifier accountability |
| Fake verifications | Auto-ban of all verifiers if fake detected |
| Key compromise | PGP key rotation, key history tracking |
| Replay attacks | PGP nonce with 1-hour TTL, 5-min timestamp drift |
| Data tampering | OpenTimestamps Bitcoin anchoring |
| Vote manipulation | PGP-signed votes, Merkle audit log, TOCTOU protection |
| Session hijacking | Short-lived JWT, session binding |
| Spam | WoT levels gate posting permissions |
| DDoS | Rate limiting, nginx buffering |
