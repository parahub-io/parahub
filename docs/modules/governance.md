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

## Civic Opinion Polls

Alongside binding group decisions, Parahub runs a non-binding **opinion barometer**
scoped to where you live. Every civic poll is clearly badged as opinion (not a
binding decision) and is scoped to a level of territory: your parish, município,
region, country, or the whole EU. You see the polls for the places you belong to,
rolled up the ladder.

### Anonymous by Design

Territorial opinion votes are stored **unlinked from your profile**. Before your
first one you pass a plain-words consent screen that is honest about the limits
(the data is de-identified, not magically anonymous). Results are only ever shown
in groups — a breakdown needs at least five voters before it appears — and exact
live counts stay hidden until enough people have voted, so no one can be
identified by timing.

### Verifiable Without De-anonymizing

After voting you get a **counted-as-cast receipt**. Later you can check that
receipt against the poll's audit chain to confirm your vote was included — without
ever revealing how you voted. If you withdraw consent or delete your account, your
opinion votes are removed and the results are recounted.

### Standing Delegations

Liquid democracy that persists: delegate your voice on a **whole topic** or a
**whole territory** to someone you trust, and it applies to future polls in that
scope until you revoke it. Delegation needs the delegate's acceptance, chains
transitively, and is always overridden the moment you vote yourself.

### Household & Condominium Ballots

A lightweight, **open** (named) ballot for shared decisions among the members of
your home or the residents of your condominium — a sandbox for the small votes
that don't need the full binding-assembly machinery.

### Citizen Ideas

A proposals pipeline: suggest an idea for your territory, others support it, and
once it gathers enough support it is flagged for review and can be promoted into a
full poll.

### EU Barometer

The EU-level barometer is a public showcase — anyone can see it. EU polls also show
an honest **momentum gauge** toward the European Citizens' Initiative threshold
(one million supporters across at least seven countries). It measures support and
momentum, not official ECI signatures, and says so.

Curated poll text is hand-authored in all six languages (never machine-translated,
to keep voting legitimacy) and switches instantly with the interface language.

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
- **Frontend**: `pages/governance/polls/` (index, [id], create, delegations-[id], audit-[id]), `pages/governance/delegations`, `pages/governance/ideas`, `pages/household/join`
