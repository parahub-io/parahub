"""
Barter Graph Service
Business logic for multi-party exchange matching using Neo4j
"""

from typing import List, Dict, Optional
from barter.neo4j_client import Neo4jClient
from identity.models import Profile
from market.models import Item
import logging

logger = logging.getLogger(__name__)


class BarterGraphService:
    """
    Service for managing barter exchange graph in Neo4j

    Graph Model:
        Nodes: User, Item, Category
        Relationships: OWNS, IN_CATEGORY
        Virtual relationships: CAN_EXCHANGE (computed from CREDIT/DEBIT items)
    """

    def __init__(self):
        self.client = Neo4jClient()

    def sync_user_to_graph(self, profile):
        """
        Sync Profile (User) to Neo4j graph

        Args:
            profile: Profile instance
        """
        query = """
        MERGE (u:User {id: $id})
        SET u.display_name = $display_name,
            u.updated_at = datetime()
        RETURN u.id as id
        """

        params = {
            'id': profile.id,
            'display_name': profile.display_name,
        }

        try:
            result = self.client.execute_write(query, params)
            logger.info(f"Synced user {profile.id} to Neo4j")
            return result
        except Exception as e:
            logger.error(f"Failed to sync user {profile.id}: {e}")
            raise

    def sync_category_to_graph(self, category):
        """
        Sync Category to Neo4j graph with hierarchy

        Args:
            category: Category instance
        """
        query = """
        MERGE (c:Category {id: $id})
        SET c.slug = $slug,
            c.name = $name,
            c.name_en = $name_en,
            c.updated_at = datetime()

        WITH c
        MATCH (parent:Category {id: $parent_id})
        WHERE $parent_id IS NOT NULL
        MERGE (c)-[:PARENT]->(parent)

        RETURN c.id as id
        """

        params = {
            'id': category.id,
            'slug': category.slug,
            'name': category.name,
            'name_en': category.name_i18n.get('en', category.name) if category.name_i18n else category.name,
            'parent_id': category.parent.id if category.parent else None,
        }

        try:
            result = self.client.execute_write(query, params)
            logger.info(f"Synced category {category.id} to Neo4j")
            return result
        except Exception as e:
            logger.error(f"Failed to sync category {category.id}: {e}")
            raise

    def sync_item_to_graph(self, item):
        """
        Sync Item from PostgreSQL to Neo4j graph

        Args:
            item: Item instance from Django ORM
        """
        query = """
        MERGE (i:Item {id: $id})
        SET i.type = $type,
            i.category_id = $category_id,
            i.owner_id = $owner_id,
            i.title = $title,
            i.is_active = $is_active,
            i.updated_at = datetime()

        // Add location if exists
        FOREACH (ignoreMe IN CASE WHEN $lat IS NOT NULL THEN [1] ELSE [] END |
            SET i.location = point({latitude: $lat, longitude: $lon})
        )

        WITH i
        MATCH (u:User {id: $owner_id})
        MERGE (u)-[:OWNS]->(i)

        WITH i
        MATCH (c:Category {id: $category_id})
        WHERE $category_id IS NOT NULL
        MERGE (i)-[:IN_CATEGORY]->(c)

        RETURN i.id as id
        """

        location = item.location
        params = {
            'id': item.id,
            'type': item.type,
            'category_id': item.category.id if item.category else None,
            'owner_id': item.owner.id,
            'title': item.title,
            'is_active': item.is_active,
            'lat': location.y if location else None,
            'lon': location.x if location else None,
        }

        try:
            result = self.client.execute_write(query, params)
            logger.info(f"Synced item {item.id} to Neo4j")
            return result
        except Exception as e:
            logger.error(f"Failed to sync item {item.id}: {e}")
            raise

    def delete_item_from_graph(self, item_id: str):
        """
        Remove Item from Neo4j graph

        Args:
            item_cri: Item ID to delete
        """
        query = """
        MATCH (i:Item {id: $id})
        DETACH DELETE i
        RETURN count(i) as deleted
        """

        try:
            result = self.client.execute_write(query, {'id': item_id})
            logger.info(f"Deleted item {item_id} from Neo4j")
            return result
        except Exception as e:
            logger.error(f"Failed to delete item {item_id}: {e}")
            raise

    def _build_items_chain_query(self, length: int) -> str:
        """Build Cypher MATCH block for items barter cycle of given length (>= 2)."""
        lines = []
        lines.append(f"MATCH (start)-[:OWNS]->(offered1:Item {{type: 'CREDIT', is_active: true}})-[:IN_CATEGORY]->(cat1:Category)")
        lines.append(f"MATCH (cat1)<-[:IN_CATEGORY]-(wanted1:Item {{type: 'DEBIT', is_active: true}})<-[:OWNS]-(u2:User)")
        lines.append(f"WHERE u2.id <> start.id")
        for i in range(2, length):
            prev_u = f"u{i}"
            next_u = f"u{i + 1}"
            not_clauses = " AND ".join(
                f"{next_u}.id <> {('start' if j == 1 else f'u{j}')}.id"
                for j in range(1, i + 1)
            )
            lines.append(f"MATCH ({prev_u})-[:OWNS]->(offered{i}:Item {{type: 'CREDIT', is_active: true}})-[:IN_CATEGORY]->(cat{i}:Category)")
            lines.append(f"MATCH (cat{i})<-[:IN_CATEGORY]-(wanted{i}:Item {{type: 'DEBIT', is_active: true}})<-[:OWNS]-({next_u}:User)")
            lines.append(f"WHERE {not_clauses}")
        last_u = f"u{length}"
        lines.append(f"MATCH ({last_u})-[:OWNS]->(offered{length}:Item {{type: 'CREDIT', is_active: true}})-[:IN_CATEGORY]->(cat{length}:Category)")
        lines.append(f"MATCH (cat{length})<-[:IN_CATEGORY]-(wanted{length}:Item {{type: 'DEBIT', is_active: true}})<-[:OWNS]-(start)")
        chain_ids = ", ".join(["start.id"] + [f"u{i}.id" for i in range(2, length + 1)] + ["start.id"])
        cat_ids = ", ".join([f"cat{i}.id" for i in range(1, length + 1)])
        lines.append(f"WITH [{chain_ids}] as chain, [{cat_ids}] as categories")
        lines.append("RETURN DISTINCT chain, categories")
        lines.append("LIMIT 500")
        return "\n".join(lines)

    def _build_debt_chain_query(self, length: int) -> str:
        """Build Cypher MATCH block for debt clearing cycle of given length (>= 2)."""
        lines = []
        lines.append("MATCH (start:User {id: $user_id})-[:OWNS]->(debt1:Item {type: 'DEBT', is_active: true})")
        lines.append("WHERE debt1.is_debt = true")
        lines.append("MATCH (u2:User {id: debt1.creditor_id})")
        lines.append("WHERE u2.id <> start.id")
        for i in range(2, length):
            prev_u = f"u{i}"
            next_u = f"u{i + 1}"
            not_clauses = " AND ".join(
                f"{next_u}.id <> {('start' if j == 1 else f'u{j}')}.id"
                for j in range(1, i + 1)
            )
            lines.append(f"MATCH ({prev_u})-[:OWNS]->(debt{i}:Item {{type: 'DEBT', is_active: true}})")
            lines.append(f"WHERE debt{i}.is_debt = true")
            lines.append(f"MATCH ({next_u}:User {{id: debt{i}.creditor_id}})")
            lines.append(f"WHERE {not_clauses}")
        last_u = f"u{length}"
        lines.append(f"MATCH ({last_u})-[:OWNS]->(debt{length}:Item {{type: 'DEBT', is_active: true}})")
        lines.append(f"WHERE debt{length}.is_debt = true AND debt{length}.creditor_id = start.id")
        chain_ids = ", ".join(["start.id"] + [f"u{i}.id" for i in range(2, length + 1)] + ["start.id"])
        debt_cats = ", ".join(["'DEBT'"] * length)
        lines.append(f"WITH [{chain_ids}] as chain, [{debt_cats}] as categories")
        lines.append("RETURN DISTINCT chain, categories")
        lines.append("LIMIT 500")
        return "\n".join(lines)

    def find_barter_chains(self, user_id: str, max_length: int = 3, category_id: Optional[str] = None) -> List[Dict]:
        """
        Find all possible barter exchange chains for a user

        Algorithm:
        1. Find all categories where user has CREDIT items
        2. For each category, find users with DEBIT items in same category
        3. Build virtual graph of possible exchanges
        4. Find cycles back to starting user

        Args:
            user_id: User ID to find exchanges for
            max_length: Maximum chain length (number of participants)
            category_id: Optional category filter

        Returns:
            List of exchange chains:
            [
                {
                    'users': ['01K2SH48YZ...', '01K3AB78CD...', '01K4XY12MN...', '01K2SH48YZ...'],
                    'swaps': [
                        {
                            'from_user': '01K2SH48YZ...',
                            'to_user': '01K3AB78CD...',
                            'offered_items': [{'id': '01K5MN34PQ...', 'title': '...'}],
                            'wanted_items': [{'id': '01K6RS56TU...', 'title': '...'}],
                            'category_id': '01K7VW78XY...'
                        },
                        ...
                    ]
                }
            ]
        """

        from constance import config
        effective_max = min(max_length, config.BARTER_MAX_CHAIN_LENGTH)
        effective_max = max(2, effective_max)  # minimum 2

        # Build UNION ALL of item + debt cycle queries for each length 2..effective_max
        blocks = []
        for length in range(2, effective_max + 1):
            blocks.append(f"// Items cycle length {length}\nMATCH (start:User {{id: $user_id}})\n" + self._build_items_chain_query(length))
            blocks.append(f"// Debt cycle length {length}\n" + self._build_debt_chain_query(length))

        query = "\nUNION ALL\n\n".join(blocks)

        params = {
            'user_id': user_id,
            'category_id': category_id,
        }

        try:
            results = self.client.execute_read(query, params)
            logger.info(f"Cypher returned {len(results)} raw results for user {user_id}")

            chains = []

            for record in results:
                chain = record['chain']
                categories = record['categories']

                # Skip chains where current user doesn't participate
                if user_id not in chain:
                    logger.warning(f"Skipping chain {chain} - user {user_id} not a participant")
                    continue

                # Normalize chain to start with user_id
                normalized_chain, normalized_categories, _ = self._normalize_chain(chain, categories, user_id)

                # Build swap details for this (participants + category path) combination.
                # All combinations with the same participants are later merged by _group_two_way_exchanges.
                swaps = self._extract_swaps_from_chain(normalized_chain, normalized_categories)

                chains.append({
                    'users': normalized_chain,
                    'swaps': swaps
                })

            # Group 2-way exchanges by participants (Alice-Bob = one opportunity)
            grouped_chains = self._group_two_way_exchanges(chains, user_id)

            # Enrich with user and item data from PostgreSQL
            enriched_chains = self._enrich_chains_with_details(grouped_chains)

            logger.info(f"Found {len(enriched_chains)} barter chains for user {user_id} (deduplicated from {len(results)} raw, grouped 2-way)")
            return enriched_chains

        except Exception as e:
            logger.error(f"Failed to find barter chains for {user_id}: {e}")
            raise

    def _group_two_way_exchanges(self, chains: List[Dict], user_id: str) -> List[Dict]:
        """
        Group exchanges by participants (both 2-way and 3+ way).

        Multiple chains with same participants but different items/categories
        should be merged into single exchange opportunity showing all possible items.

        Args:
            chains: List of chain dicts with 'users' and 'swaps'
            user_id: Current user ID

        Returns:
            List of grouped chains
        """
        grouped_chains = {}  # {participants_tuple: chain_data}

        for chain in chains:
            users = chain['users']
            # Create key from participants (already normalized to start with user_id)
            participants_key = tuple(users[:-1])  # Remove last element (same as first)

            if participants_key not in grouped_chains:
                grouped_chains[participants_key] = {
                    'users': users,
                    'all_swaps': []  # Collect ALL swaps from all variations
                }

            # Collect all swaps
            grouped_chains[participants_key]['all_swaps'].extend(chain.get('swaps', []))

        # Convert grouped exchanges to final format
        result = []
        for participants, data in grouped_chains.items():
            # For 2-way exchanges: show as "you can offer" / "they can offer"
            if len(participants) == 2:
                user_offers = []
                partner_offers = []

                for swap in data['all_swaps']:
                    if swap['from_user'] == user_id:
                        user_offers.extend(swap.get('offered_items', []))
                    else:
                        partner_offers.extend(swap.get('offered_items', []))

                # Deduplicate items by ID
                user_offers_map = {item['id']: item for item in user_offers}
                partner_offers_map = {item['id']: item for item in partner_offers}

                result.append({
                    'users': data['users'],
                    'swaps': [
                        {
                            'from_user': user_id,
                            'to_user': participants[1],
                            'offered_items': list(user_offers_map.values()),
                            'wanted_items': [],
                            'category_id': None
                        },
                        {
                            'from_user': participants[1],
                            'to_user': user_id,
                            'offered_items': list(partner_offers_map.values()),
                            'wanted_items': [],
                            'category_id': None
                        }
                    ]
                })
            else:
                # 3+ way exchanges: group swaps by from_user -> to_user pair
                swap_map = {}  # {(from, to): items}

                for swap in data['all_swaps']:
                    key = (swap['from_user'], swap['to_user'])
                    if key not in swap_map:
                        swap_map[key] = {
                            'from_user': swap['from_user'],
                            'to_user': swap['to_user'],
                            'offered_items': [],
                            'wanted_items': [],
                            'category_id': None
                        }
                    swap_map[key]['offered_items'].extend(swap.get('offered_items', []))

                # Deduplicate items in each swap
                final_swaps = []
                for swap_data in swap_map.values():
                    items_map = {item['id']: item for item in swap_data['offered_items']}
                    swap_data['offered_items'] = list(items_map.values())
                    final_swaps.append(swap_data)

                result.append({
                    'users': data['users'],
                    'swaps': final_swaps
                })

        return result

    def _normalize_chain(self, chain: List[str], categories: List[str], user_id: str) -> tuple:
        """
        Normalize a chain to start with user_id and create signature for deduplication.

        Cycles like [A,B,C,A], [B,C,A,B], [C,A,B,C] are the same cycle.
        We normalize them to always start with user_id.

        Args:
            chain: List of user IDs forming a cycle (last element = first element)
            categories: List of category IDs for each swap
            user_id: Current user ID to start the chain with

        Returns:
            Tuple of (normalized_chain, rotated_categories, signature) for deduplication
        """
        # Cycle is [A, B, C, A] - remove last element to get [A, B, C]
        cycle = chain[:-1]

        # Verify user_id is in the cycle
        if user_id not in cycle:
            logger.warning(f"User {user_id} not found in chain {chain}")
            return (chain, categories, (tuple(chain),))

        # Rotate cycle to start with user_id
        user_idx = cycle.index(user_id)
        rotated_users = cycle[user_idx:] + cycle[:user_idx]

        # Also rotate categories to match
        rotated_categories = categories[user_idx:] + categories[:user_idx]

        # Add back the closing element
        normalized_chain = rotated_users + [rotated_users[0]]

        # Create signature for deduplication: ONLY by participants, not categories
        # Same participants = same opportunity, regardless of which items/categories
        signature = (tuple(rotated_users),)

        return (normalized_chain, rotated_categories, signature)

    def _extract_swaps_from_chain(self, user_chain: List[str], categories: List[str]) -> List[Dict]:
        """
        Extract detailed swap information from a user chain

        Args:
            user_chain: List of user IDs forming a cycle
            categories: List of category IDs for each swap

        Returns:
            List of swap dictionaries with item details
        """
        swaps = []

        for i in range(len(user_chain) - 1):
            from_user = user_chain[i]
            to_user = user_chain[i + 1]
            category = categories[i] if i < len(categories) else categories[0]

            # Query to get specific items involved in this swap
            query = """
            MATCH (from_user:User {id: $from_user})-[:OWNS]->(offered:Item {type: 'CREDIT', is_active: true})
            MATCH (offered)-[:IN_CATEGORY]->(cat:Category {id: $category})
            MATCH (cat)<-[:IN_CATEGORY]-(wanted:Item {type: 'DEBIT', is_active: true})
            MATCH (wanted)<-[:OWNS]-(to_user:User {id: $to_user})

            RETURN
                collect(DISTINCT {id: offered.id, title: offered.title}) as offered_items,
                collect(DISTINCT {id: wanted.id, title: wanted.title}) as wanted_items,
                cat.id as category_cri
            """

            params = {
                'from_user': from_user,
                'to_user': to_user,
                'category': category,
            }

            try:
                result = self.client.execute_read(query, params)
                if result:
                    record = result[0]
                    swaps.append({
                        'from_user': from_user,
                        'to_user': to_user,
                        'offered_items': record['offered_items'],
                        'wanted_items': record['wanted_items'],
                        'category_id': record['category_cri']
                    })
            except Exception as e:
                logger.warning(f"Failed to extract swap details for {from_user}->{to_user}: {e}")

        return swaps

    def _enrich_chains_with_details(self, chains: List[Dict]) -> List[Dict]:
        """
        Enrich chains with user display names and full item details from PostgreSQL

        Args:
            chains: List of chains with user IDs and item IDs

        Returns:
            Enriched chains with user info and full item details (images, pricing, category path)
        """
        # Collect all unique user IDs and item IDs
        user_ids = set()
        item_ids = set()

        for chain in chains:
            for user_id in chain['users']:
                user_ids.add(user_id)
            for swap in chain.get('swaps', []):
                for item in swap.get('offered_items', []):
                    item_ids.add(item['id'])
                for item in swap.get('wanted_items', []):
                    item_ids.add(item['id'])

        # Batch load profiles
        profiles = Profile.objects.filter(id__in=user_ids).values('id', 'display_name')
        profile_map = {p['id']: p for p in profiles}

        # Batch load items with all related data
        items = Item.objects.filter(id__in=item_ids).select_related('category').prefetch_related('images')
        item_map = {}
        for item in items:
            first_image = item.images.first()
            item_map[item.id] = {
                'image': first_image.image.url if first_image else None,
                'pricing_options': item.pricing_options or [],
                'category_name': item.category.name if item.category else None,
                'category_path': item.category.get_path() if item.category else None
            }

        # Enrich chains
        enriched = []
        for chain in chains:
            # Replace user IDs with user info
            users_info = []
            for user_id in chain['users']:
                profile = profile_map.get(user_id, {})
                users_info.append({
                    'id': user_id,
                    'display_name': profile.get('display_name', '')
                })

            # Enrich swaps with full item details
            enriched_swaps = []
            for swap in chain.get('swaps', []):
                # Enrich offered items
                for item in swap.get('offered_items', []):
                    item_data = item_map.get(item['id'], {})
                    item['image'] = item_data.get('image')
                    item['pricing_options'] = item_data.get('pricing_options', [])
                    item['category_name'] = item_data.get('category_name')
                    item['category_path'] = item_data.get('category_path')

                # Enrich wanted items
                for item in swap.get('wanted_items', []):
                    item_data = item_map.get(item['id'], {})
                    item['image'] = item_data.get('image')
                    item['pricing_options'] = item_data.get('pricing_options', [])
                    item['category_name'] = item_data.get('category_name')
                    item['category_path'] = item_data.get('category_path')

                enriched_swaps.append(swap)

            enriched.append({
                'users': users_info,
                'swaps': enriched_swaps
            })

        return enriched

    def get_graph_stats(self) -> Dict:
        """
        Get statistics about the barter graph

        Returns:
            Dict with node and relationship counts
        """
        query = """
        MATCH (u:User) WITH count(u) as users
        MATCH (i:Item) WITH users, count(i) as items
        MATCH (c:Category) WITH users, items, count(c) as categories
        MATCH ()-[r:OWNS]->() WITH users, items, categories, count(r) as owns_rels
        MATCH ()-[r2:IN_CATEGORY]->() WITH users, items, categories, owns_rels, count(r2) as category_rels

        RETURN {
            users: users,
            items: items,
            categories: categories,
            owns_relationships: owns_rels,
            category_relationships: category_rels
        } as stats
        """

        try:
            result = self.client.execute_read(query)
            return result[0]['stats'] if result else {}
        except Exception as e:
            logger.error(f"Failed to get graph stats: {e}")
            return {}

    def sync_debt_to_graph(self, debt):
        """
        Sync Debt to Neo4j as virtual Item

        Debt is represented as a virtual Item node:
        - type = 'DEBT'
        - owner_id = debtor (person who owes money)
        - Properties: creditor_id, amount, currency, remaining_amount

        In barter cycles, debt can be used to offset other debts

        Args:
            debt: Debt instance from debts.models
        """
        query = """
        MERGE (d:Item {id: $id})
        SET d.type = 'DEBT',
            d.owner_id = $debtor_id,
            d.creditor_id = $creditor_id,
            d.amount = $amount,
            d.remaining_amount = $remaining_amount,
            d.currency = $currency,
            d.title = $title,
            d.is_active = true,
            d.is_debt = true,
            d.updated_at = datetime()

        WITH d
        MATCH (debtor:User {id: $debtor_id})
        MERGE (debtor)-[:OWNS]->(d)

        RETURN d.id as id
        """

        params = {
            'id': f"DEBT-{debt.id}",  # Prefix to distinguish from regular items
            'debtor_id': debt.debtor_id,
            'creditor_id': debt.creditor_id,
            'amount': float(debt.amount),
            'remaining_amount': float(debt.remaining_amount),
            'currency': debt.currency,
            'title': f"Debt: {debt.debtor.display_name or debt.debtor.hna} owes {debt.creditor.display_name or debt.creditor.hna} {debt.remaining_amount} {debt.currency}",
        }

        try:
            result = self.client.execute_write(query, params)
            logger.info(f"Synced debt {debt.id} to Neo4j as virtual item")
            return result
        except Exception as e:
            logger.error(f"Failed to sync debt {debt.id} to Neo4j: {e}")
            raise

    def delete_debt_from_graph(self, debt_id: str):
        """
        Remove Debt virtual item from Neo4j graph

        Args:
            debt_id: Debt ULID to delete
        """
        query = """
        MATCH (d:Item {id: $id, is_debt: true})
        DETACH DELETE d
        RETURN count(d) as deleted
        """

        try:
            result = self.client.execute_write(query, {'id': f"DEBT-{debt_id}"})
            logger.info(f"Deleted debt {debt_id} from Neo4j")
            return result
        except Exception as e:
            logger.error(f"Failed to delete debt {debt_id} from Neo4j: {e}")
            raise
