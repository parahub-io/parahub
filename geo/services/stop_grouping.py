"""
Virtual stop grouping (StopGroup) — display-level dedup of physical stops.

Pipeline: load units (parent_station trees) → candidate edges (PostGIS ≤50m)
→ name gates (canonical token equality / containment) → union-find with guards
→ cluster attributes (centroid, elected name) → idempotent upsert.

Physical Stop rows are never mutated beyond the nullable `group` FK.
Recomputed after GTFS imports; same data twice → zero diff.
See PK/transit-system.md § Virtual stops.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.contrib.gis.geos import Point
from django.db import connection, transaction

from geo.models import Stop, StopGroup

RADIUS_M = 50              # candidate edge radius between unit roots
STATION_RADIUS_M = 150     # wider radius when AT LEAST ONE side is a rail/metro
                           # station (interchange tier): a station is one centroid
                           # sitting 60–170m both from the on-street bus poles serving
                           # it AND from a neighbouring station of another feed (Cais
                           # Sodré 167m, Areeiro 74m, CP↔ML Oriente 60m), so the 50m
                           # gate misses nearly every bus↔metro AND rail↔metro transfer.
                           # Bus↔bus pairs (neither rail) never get it (see cluster_units).
MAX_CLUSTER_WARN = 40      # warn loudly above this — never truncate silently
MAX_PARENT_DEPTH = 5       # parent_station chain guard (GTFS allows 2 levels)
UPDATE_BATCH = 10_000

# Toponym-type abbreviation canonicalization, applied per token AFTER diacritics
# stripping (pt 'pç.' arrives here as 'pc'). Cyrillic and latin keys can't collide.
# English 'st' is deliberately absent: leading St = Saint, trailing = Street —
# too ambiguous; identical spellings still merge via plain equality.
ABBREVIATIONS = {
    # ru
    'пл': 'площадь', 'ул': 'улица', 'пр': 'проспект', 'просп': 'проспект',
    'пер': 'переулок', 'наб': 'набережная', 'ш': 'шоссе', 'бул': 'бульвар',
    # pt
    'pc': 'praca', 'av': 'avenida', 'r': 'rua', 'lgo': 'largo',
    'estr': 'estrada', 'tv': 'travessa',
    # en
    'ave': 'avenue', 'rd': 'road', 'sq': 'square', 'blvd': 'boulevard', 'hwy': 'highway',
    # cs
    'nam': 'namesti', 'ul': 'ulice',
}

# Full forms used by the type-conflict guard: a cluster may not mix two different
# toponym types — bare «Ленина» must not glue «улица Ленина» to «площадь Ленина».
TYPE_TOKENS = frozenset(ABBREVIATIONS.values())

# Non-type token expansions: saint-name qualifiers (pt/es/it «Sta.»/«Sto.»). Kept
# OUT of ABBREVIATIONS deliberately so 'santa'/'santo' never join TYPE_TOKENS —
# they are name qualifiers, not toponym types, so «Santa X» must not type-conflict
# with «Praça X». Without this, «Estação Sta. Apolónia» {estacao,sta,apolonia} fails
# to contain «Santa Apolónia» {santa,apolonia} (sta ≠ santa) even at 3m apart.
QUALIFIER_ABBREVIATIONS = {'sta': 'santa', 'sto': 'santo'}

# Single lookup used during normalization (types + qualifiers).
_TOKEN_CANON = {**ABBREVIATIONS, **QUALIFIER_ABBREVIATIONS}

# Pure connectives carry no identity («Cais do Sodré» = «Cais Sodré»).
STOPWORDS = frozenset({'de', 'do', 'da', 'dos', 'das', 'del', 'e', 'of', 'the', 'and', 'и'})

_PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)


def normalize_tokens(name: str) -> frozenset:
    """Canonical significant-token set of a stop name. Language-agnostic core
    (casefold + NFKD diacritics strip) + small abbreviation/stopword dictionaries."""
    s = unicodedata.normalize('NFKD', (name or '').casefold())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = _PUNCT_RE.sub(' ', s)
    tokens = [_TOKEN_CANON.get(t, t) for t in s.split()]
    significant = frozenset(t for t in tokens if t not in STOPWORDS)
    return significant if significant else frozenset(tokens)


def edge_passes(tokens_a: frozenset, tokens_b: frozenset) -> bool:
    """Name gate for a ≤RADIUS_M candidate pair: canonical equality, or proper
    containment with at least one alphabetic token on the smaller side (so a
    bare house/platform number can never glue two unrelated stops)."""
    if not tokens_a or not tokens_b:
        return False
    if tokens_a == tokens_b:
        return True
    small, big = (tokens_a, tokens_b) if len(tokens_a) < len(tokens_b) else (tokens_b, tokens_a)
    return small < big and any(t.isalpha() for t in small)


@dataclass
class Unit:
    """Clustering atom: a parent_station tree (root + children) or a lone stop."""
    root_id: str
    name: str
    norm: frozenset
    lon: float
    lat: float
    is_station: bool
    ds_id: str
    is_rail: bool = False   # any member served by a metro/rail route → interchange tier
    member_ids: list = field(default_factory=list)
    place_ids: list = field(default_factory=list)
    lt0_count: int = 0

    @property
    def type_tokens(self) -> frozenset:
        return self.norm & TYPE_TOKENS


def load_railgrade_stop_ids():
    """Stop ids served by a metro/rail route on any active feed. These are the
    fixed-infrastructure stations whose single centroid sits far from the curbside
    poles they interchange with → they (and only they) get STATION_RADIUS_M.
    Buckets: subway/metro (1), rail (2), extended rail (100–199), extended urban
    rail/metro (400–499). Coach (200–299) is long-distance BUS — excluded; tram,
    trolleybus, funicular and ferry are curbside/short and stay on the 50m tier."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT rs.stop_id
            FROM geo_routestop rs
            JOIN geo_route r ON r.id = rs.route_id
            JOIN geo_agency a ON a.id = r.agency_id
            JOIN geo_transitdatasource ds ON ds.id = a.data_source_id AND ds.is_active
            WHERE r.route_type IN (1, 2)
               OR (r.route_type BETWEEN 100 AND 199)
               OR (r.route_type BETWEEN 400 AND 499)
        """)
        return frozenset(row[0] for row in cur.fetchall())


def load_units(railgrade_ids=frozenset()):
    """All stops of active TransitDataSources (managed included), lt ≤ 1,
    folded into parent_station trees. Returns {root_id: Unit}.
    A unit is rail-grade if ANY of its member stops is served by metro/rail
    (the flag propagates to the parent-station root)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.id, s.name, s.location_type, s.parent_station_id, s.place_id,
                   ST_X(s.location::geometry), ST_Y(s.location::geometry),
                   a.data_source_id
            FROM geo_stop s
            JOIN geo_agency a ON a.id = s.agency_id
            JOIN geo_transitdatasource ds ON ds.id = a.data_source_id
            WHERE ds.is_active AND s.location_type <= 1 AND s.location IS NOT NULL
        """)
        rows = cur.fetchall()

    by_id = {r[0]: r for r in rows}

    def root_of(stop_id):
        cur_id = stop_id
        for _ in range(MAX_PARENT_DEPTH):
            parent_id = by_id[cur_id][3]
            if parent_id is None or parent_id not in by_id:
                return cur_id
            cur_id = parent_id
        return cur_id

    units = {}
    for r in rows:
        rid = root_of(r[0])
        root = by_id[rid]
        unit = units.get(rid)
        if unit is None:
            unit = units[rid] = Unit(
                root_id=rid, name=root[1], norm=normalize_tokens(root[1]),
                lon=root[5], lat=root[6], is_station=(root[2] == 1), ds_id=root[7],
            )
        unit.member_ids.append(r[0])
        if r[0] in railgrade_ids:
            unit.is_rail = True
        if r[4]:
            unit.place_ids.append(r[4])
        if r[2] == 0:
            unit.lt0_count += 1
    return units


def load_candidate_edges():
    """Root pairs within STATION_RADIUS_M across all active feeds. Returns
    [(root_a, root_b, distance_m)] sorted by (distance, ids) — deterministic.
    The wide radius is fetched here; cluster_units applies the per-pair tier
    (50m default, 150m only for a cross-mode rail↔street pair)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT a.id, b.id, ST_Distance(a.location, b.location)
            FROM geo_stop a
            JOIN geo_stop b ON b.id > a.id AND ST_DWithin(a.location, b.location, %s)
            JOIN geo_agency ga ON ga.id = a.agency_id
            JOIN geo_transitdatasource da ON da.id = ga.data_source_id AND da.is_active
            JOIN geo_agency gb ON gb.id = b.agency_id
            JOIN geo_transitdatasource db ON db.id = gb.data_source_id AND db.is_active
            WHERE a.location_type <= 1 AND b.location_type <= 1
              AND a.parent_station_id IS NULL AND b.parent_station_id IS NULL
        """, [STATION_RADIUS_M])
        edges = cur.fetchall()
    edges.sort(key=lambda e: (e[2], e[0], e[1]))
    return edges


def cluster_units(units, edges, warn=None):
    """Union-find over gate-passing edges with two guards:
    - type-conflict: both sides carry non-empty, differing toponym-type sets → skip
    - same-feed-station: both sides contain a station of the same feed → skip
    Returns clusters of ≥2 units as [[Unit, ...], ...]."""
    parent = {}
    cluster_types = {}     # dsu root -> set of toponym-type tokens
    cluster_stations = {}  # dsu root -> set of ds_ids having a station

    def find(x):
        root = x
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(x, x) != root:
            parent[x], x = root, parent[x]
        return root

    for uid, u in units.items():
        parent[uid] = uid
        cluster_types[uid] = set(u.type_tokens)
        cluster_stations[uid] = {u.ds_id} if u.is_station else set()

    for a_id, b_id, dist in edges:
        ua, ub = units.get(a_id), units.get(b_id)
        if ua is None or ub is None or not edge_passes(ua.norm, ub.norm):
            continue
        # Distance tier: 50m for street/same-mode pairs; widen to 150m when AT LEAST
        # ONE side is a rail/metro station (the interchange case) — covers bus↔metro
        # AND rail↔metro/rail↔rail across feeds (CP «Lisboa Oriente» ↔ ML «Oriente»,
        # 60m). Bus↔bus chains (neither rail) never get the wide radius. The name gate
        # already demands same/containment names, so genuinely distinct stations (km
        # apart) never merge; a same-name rail neighbour within 150m is one interchange.
        if dist > RADIUS_M and not (dist <= STATION_RADIUS_M and (ua.is_rail or ub.is_rail)):
            continue
        ra, rb = find(a_id), find(b_id)
        if ra == rb:
            continue
        ta, tb = cluster_types[ra], cluster_types[rb]
        if ta and tb and ta != tb:
            continue
        if cluster_stations[ra] & cluster_stations[rb]:
            continue
        parent[rb] = ra
        cluster_types[ra] = ta | tb
        cluster_stations[ra] = cluster_stations[ra] | cluster_stations[rb]

    grouped = defaultdict(list)
    for uid, u in units.items():
        grouped[find(uid)].append(u)

    clusters = [c for c in grouped.values() if len(c) >= 2]
    for c in clusters:
        if len(c) > MAX_CLUSTER_WARN and warn:
            warn(f"Cluster of {len(c)} units around «{c[0].name}» — inspect for false merges")
    return clusters


def elect_name(cluster):
    """(1) station-grade member's name; (2) majority canonical token set among
    unit roots, displayed as its longest raw spelling; ties → smaller root ULID."""
    stations = [u for u in cluster if u.is_station]
    if stations:
        return min(stations, key=lambda u: u.root_id).name
    counts = Counter(u.norm for u in cluster)
    min_ulid = {s: min(u.root_id for u in cluster if u.norm == s) for s in counts}
    best_set = sorted(counts, key=lambda s: (-counts[s], min_ulid[s]))[0]
    candidates = sorted((u for u in cluster if u.norm == best_set),
                        key=lambda u: (-len(u.name), u.root_id))
    return candidates[0].name


def build_cluster_attrs(cluster):
    """Desired StopGroup row + member set for one cluster."""
    member_ids = [sid for u in cluster for sid in u.member_ids]
    lt0 = sum(u.lt0_count for u in cluster)
    place_counts = Counter(pid for u in cluster for pid in u.place_ids)
    place_id = sorted(place_counts, key=lambda p: (-place_counts[p], p))[0] if place_counts else None
    return {
        'name': elect_name(cluster),
        'lon': sum(u.lon for u in cluster) / len(cluster),
        'lat': sum(u.lat for u in cluster) / len(cluster),
        'place_id': place_id,
        'member_count': lt0 if lt0 else len(member_ids),
        'member_ids': frozenset(member_ids),
    }


def compute_desired_groups(warn=None):
    units = load_units(load_railgrade_stop_ids())
    edges = load_candidate_edges()
    clusters = cluster_units(units, edges, warn=warn)
    return [build_cluster_attrs(c) for c in clusters]


def _match_existing(desired, current_members):
    """Match desired clusters to existing groups by max member overlap.
    current_members: {group_id: set(stop_ids)}. Returns {cluster_idx: group_id}."""
    old_group_of = {}
    for gid, members in current_members.items():
        for sid in members:
            old_group_of[sid] = gid

    claims = []
    for idx, cluster in enumerate(desired):
        overlap = Counter()
        for sid in cluster['member_ids']:
            gid = old_group_of.get(sid)
            if gid:
                overlap[gid] += 1
        for gid, n in overlap.items():
            claims.append((-n, gid, min(cluster['member_ids']), idx))

    claims.sort()
    assigned, taken_groups = {}, set()
    for _neg, gid, _key, idx in claims:
        if idx in assigned or gid in taken_groups:
            continue
        assigned[idx] = gid
        taken_groups.add(gid)
    return assigned


def _bulk_set_group(pairs):
    """pairs: [(stop_id, group_id)] — one UPDATE per batch via parallel unnest."""
    with connection.cursor() as cur:
        for i in range(0, len(pairs), UPDATE_BATCH):
            chunk = pairs[i:i + UPDATE_BATCH]
            cur.execute("""
                UPDATE geo_stop AS s SET group_id = v.gid
                FROM (SELECT unnest(%s::varchar[]) AS id, unnest(%s::varchar[]) AS gid) v
                WHERE s.id = v.id
            """, [[p[0] for p in chunk], [p[1] for p in chunk]])


def _bulk_clear_group(stop_ids):
    with connection.cursor() as cur:
        for i in range(0, len(stop_ids), UPDATE_BATCH):
            cur.execute(
                "UPDATE geo_stop SET group_id = NULL WHERE id = ANY(%s)",
                [stop_ids[i:i + UPDATE_BATCH]],
            )


def recompute_stop_groups(dry_run=False, warn=None):
    """Idempotent recompute. Returns stats dict; second run on unchanged data
    yields all-zero stats. Everything inside one transaction."""
    desired = compute_desired_groups(warn=warn)

    current_members = defaultdict(set)
    for sid, gid in Stop.objects.exclude(group=None).values_list('id', 'group_id'):
        current_members[gid].add(sid)
    existing = {g.id: g for g in StopGroup.objects.all()}
    # Orphan groups (no members) are matched by nobody → deleted below.

    assigned = _match_existing(desired, current_members)

    stats = {'groups_created': 0, 'groups_updated': 0, 'groups_deleted': 0,
             'members_assigned': 0, 'members_cleared': 0,
             'groups_total': len(desired),
             'members_total': sum(len(c['member_ids']) for c in desired)}

    if dry_run:
        matched_gids = set(assigned.values())
        stats['groups_created'] = sum(1 for i in range(len(desired)) if i not in assigned)
        stats['groups_deleted'] = len(set(existing) - matched_gids)
        desired_map = {}
        for idx, cluster in enumerate(desired):
            gid = assigned.get(idx)
            for sid in cluster['member_ids']:
                desired_map[sid] = (gid, idx)
        for sid, (gid, _idx) in desired_map.items():
            if gid is None or sid not in current_members.get(gid, ()):
                stats['members_assigned'] += 1
        currently_grouped = set().union(*current_members.values()) if current_members else set()
        stats['members_cleared'] = len(currently_grouped - set(desired_map))
        return stats

    with transaction.atomic():
        new_groups, assign_pairs = [], []
        for idx, cluster in enumerate(desired):
            gid = assigned.get(idx)
            if gid is None:
                group = StopGroup(
                    name=cluster['name'],
                    location=Point(cluster['lon'], cluster['lat'], srid=4326),
                    place_id=cluster['place_id'],
                    member_count=cluster['member_count'],
                )
                new_groups.append(group)
                gid = group.id
                stats['groups_created'] += 1
                assign_pairs.extend((sid, gid) for sid in cluster['member_ids'])
            else:
                g = existing[gid]
                changed = []
                if g.name != cluster['name']:
                    g.name = cluster['name']; changed.append('name')
                if abs(g.location.x - cluster['lon']) > 1e-9 or abs(g.location.y - cluster['lat']) > 1e-9:
                    g.location = Point(cluster['lon'], cluster['lat'], srid=4326); changed.append('location')
                if g.place_id != cluster['place_id']:
                    g.place_id = cluster['place_id']; changed.append('place_id')
                if g.member_count != cluster['member_count']:
                    g.member_count = cluster['member_count']; changed.append('member_count')
                if changed:
                    g.save(update_fields=changed + ['updated_at'])
                    stats['groups_updated'] += 1
                old = current_members.get(gid, set())
                assign_pairs.extend((sid, gid) for sid in cluster['member_ids'] - old)

        if new_groups:
            StopGroup.objects.bulk_create(new_groups, batch_size=1000)
        if assign_pairs:
            _bulk_set_group(assign_pairs)
            stats['members_assigned'] = len(assign_pairs)

        desired_member_ids = set()
        for cluster in desired:
            desired_member_ids |= cluster['member_ids']
        currently_grouped = set().union(*current_members.values()) if current_members else set()
        to_clear = sorted(currently_grouped - desired_member_ids)
        if to_clear:
            _bulk_clear_group(to_clear)
            stats['members_cleared'] = len(to_clear)

        dead = set(existing) - set(assigned.values())
        if dead:
            stats['groups_deleted'] = StopGroup.objects.filter(id__in=dead).delete()[0]

    return stats
