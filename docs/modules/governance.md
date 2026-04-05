# Governance

Liquid democracy voting system with cryptographic audit trail. One user, one vote -- but you can delegate your vote to someone you trust.

## Polls

Multiple-choice polls with configurable options. Any verified user can create a poll. Polls can be attached to establishments (organizational decisions) or standalone (community-wide).

### Voting

- Each vote is PGP-signed by the voter (client-side)
- Server verifies PGP signature before recording
- One vote per eligible voter per poll
- Vote can be changed until poll closes

### Delegation (Liquid Democracy)

Users can delegate their vote to another user on a specific poll. Delegations are transitive: if Alice delegates to Bob, and Bob delegates to Carol, then Carol's vote counts for all three.

- Delegation chains are resolved at vote time
- Circular delegation detection prevents infinite loops
- Delegations can be revoked at any time
- Voting directly overrides any delegation

### Audit Trail

Every vote and delegation creates a Merkle audit log entry:
- Hash chain links each entry to all previous entries
- Any tampering breaks the chain
- Audit log viewable by any authenticated user
- TOCTOU race conditions explicitly protected against (security-audited)

### Real-Time Updates

WebSocket room-based updates (`poll:{id}` channel):
- Vote counts update live as people vote
- Delegation changes reflected immediately
- Connected via `usePollWebSocket` composable

## Treasury

Per-establishment participatory budgets. Members vote on how to allocate funds.

### Median Voting

Budget allocation uses median voting with interactive sliders:
- Each member assigns percentages to budget categories
- Final allocation = median of all member votes
- Prevents extreme positions from dominating

### Epochs

Monthly budget epochs with freeze mechanism:
- Active epoch: members can adjust votes
- Finalized epoch: votes locked, allocation calculated
- Merkle audit chain for all treasury operations

### Real-Time

WebSocket updates (`treasury:{id}` channel) show live median changes as members adjust sliders.

## Transparency

The platform operates on a transparent revenue model with no hidden fees.

### Revenue Sources

| Source | Type | Rate | Optional |
|--------|------|------|----------|
| Wallet/Ads donations | Voluntary | 0% / 0.1% / 1% | Yes |
| EGAC energy management fee | Fixed | 1% | No (legal obligation) |

### Donations

When sending Lightning payments or creating ad campaigns, users see a donation prompt with three options (0%, 0.1%, 1%). The default is 0.1% but can be changed at any time. Donations go directly to the governing association's Lightning wallet — the platform never holds funds in between.

Users who have donated receive a supporter badge on their profile.

### Transparency Page

A public transparency page (`/docs/transparency`) shows:
- Total donations received (in sats)
- Number of donations and unique supporters
- Monthly breakdown by source
- Four commitments on what the association will never do

All data is fetched live from the API.

## Technical Details

- **Models**: `governance/models.py` -- Poll, PollContext, PollOption, PollEligibleVoter, PollVoteDelegation, PollVote, PollAuditLog
- **Models**: `treasury/models.py` -- BudgetCategory, BudgetAllocation, BudgetEpoch, Expense, TreasuryAuditLog
- **API**: `governance/api.py` -- polls CRUD, voting, delegation
- **API**: `treasury/api.py` -- `/api/v1/treasury/{slug}/`
- **Services**: `governance/services.py` -- VotingService (delegation resolution), AuditService (Merkle tree)
- **Frontend**: `pages/governance/polls/` (index, [id], create, delegations-[id], audit-[id])
