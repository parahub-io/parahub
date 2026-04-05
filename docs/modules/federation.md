# Federation

Git-based server-to-server federation enabling multi-node deployment with profile migration and cross-node trust.

## Architecture

Federation uses a **git state layer** for durable records, **WebSocket signals** for real-time notifications, and **Matrix** for inter-node communication.

### Registry
Each node maintains a public git repository (`/audit-log/public-git/`) containing:
- `node.json` -- node identity, PGP public key, endpoints
- Organizations, migrations, verifications -- PGP-signed records
- PGP keyring -- public keys of all known nodes

### Node Identity
Each Parahub instance generates an Ed25519 PGP key (via `init_federation_node` command). This key signs all outbound registry records.

## Features

### Profile Migration
Users can migrate their profile from one node to another. Requires 4 signatures:
1. Old user (authorizing departure)
2. New user (accepting arrival)
3. Old node (confirming release)
4. New node (confirming acceptance)

Migration records are anchored via OpenTimestamps to the Bitcoin blockchain.

### Cross-Node WoT
Verifications between users on different nodes are stored in both nodes' git registries. Federated verifications contribute to WoT trust levels.

### Federated Search
Nodes can search each other's public data (profiles, items, establishments) via the federation WebSocket protocol.

### Data Import
Bulk import of profiles and items from peer nodes.

### Peer Discovery
Bootstrap peers configured at startup. Automatic peer sync via `FederationClient` (long-running WebSocket connections with 5-minute heartbeat).

## Implementation

All 4 phases complete:
1. **Phase 1**: Node identity and registry git structure
2. **Phase 2**: Inter-node WebSocket protocol
3. **Phase 3**: Profile migration with multi-signature verification
4. **Phase 4**: Cross-node WoT, federated search, data import

## Technical Details

- **Services**: `parahub/services/federation_client.py` -- FederationClient; `audit_log/registry.py` -- RegistryService
- **Daemon**: `parahub-federation.service` -- long-running WebSocket client
- **Registry**: `/audit-log/public-git/` -- git repository with PGP-signed records
- **Command**: `init_federation_node` -- generates node PGP key
