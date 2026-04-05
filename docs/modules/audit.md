# Audit Trail

Cryptographic court-ready proofs for contracts, debts, and verifications. Multiple independent evidence sources ensure that no single party — including Parahub — can tamper with records.

## Four Layers of Proof

### 1. PGP Signatures

Every critical action (signing a contract, confirming a debt, casting a vote) is signed with the user's PGP key in the browser. The server verifies the signature but never has access to the private key. Public keys are published to a Git repository for independent verification.

### 2. OpenTimestamps (Bitcoin Anchoring)

Events are batched and timestamped on the Bitcoin blockchain via OpenTimestamps. One Bitcoin anchor covers many events through a Merkle tree — proving that data existed at a specific point in time. Batches are created every 10 minutes and verified against Bitcoin daily.

### 3. Matrix E2E Backup

Important events are mirrored to encrypted Matrix rooms:
- **Personal system room**: Notifications about verifications and important account events
- **Dispute rooms**: End-to-end encrypted rooms with contract parties and arbiter, containing copies of contract details

### 4. JSON Export

Users can export proof packages as ZIP files:
- **Per-contract/debt**: Contract metadata, PGP signatures, OpenTimestamps proof, verification records, and a README with verification instructions
- **Full account export**: All contracts, debts, verifications, and PGP keys (GDPR Art. 20 compliant)

## Verification Without Parahub

Anyone can verify proofs independently, without relying on Parahub:
1. Import the PGP public key from the audit Git repository
2. Verify PGP signatures with `gpg --verify`
3. Verify timestamps with `ots verify`
4. Compare SHA256 hashes against the original documents

## Legal Standing

PGP signatures qualify as Advanced Electronic Signatures under eIDAS (EU Regulation 910/2014). For contracts under €5,000, PGP + OpenTimestamps proof is generally sufficient. For larger amounts, notarization is recommended. Portuguese law references: DL 12/2021, Código Civil Art. 363º.
