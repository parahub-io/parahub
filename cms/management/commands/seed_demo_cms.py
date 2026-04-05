from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cms.models import Post, Site, SitePage
from identity.models import Profile
from geo.models import Establishment


# Blog posts: (slug, language, title, meta_description, content, author_username, establishment_slug, is_pinned, translation_of_slug)
POSTS = [
    {
        'slug': 'welcome-to-parahub',
        'language': 'en',
        'title': 'Welcome to Parahub — Civic Infrastructure for Communities',
        'meta_description': 'Introducing Parahub: a self-hosted civic platform for local commerce, governance, and mutual aid. No middlemen, no fees, no surveillance.',
        'author': 'alice',
        'establishment': None,
        'is_pinned': False,
        'translation_of': None,
        'content': """\
Parahub is an open-source civic infrastructure platform designed for real communities. It combines a local directory, peer-to-peer marketplace, democratic governance tools, and mutual aid systems — all without intermediaries.

## Why Another Platform?

Most platforms extract value from communities. They charge fees, harvest data, and optimize for engagement over wellbeing. Parahub takes the opposite approach:

- **No escrow** — funds flow directly between people
- **No surveillance** — client-side encryption for sensitive data
- **No middlemen** — peer-to-peer by design
- **No vendor lock-in** — self-hosted, federated, open source

## What You Can Do

### Local Directory
Find and list local businesses, cooperatives, and services. Think of it as a community-owned alternative to Google Maps — with reviews backed by a Web of Trust instead of anonymous accounts.

### P2P Marketplace
Buy, sell, and barter goods and services directly. The barter engine can even find multi-party exchange cycles: you have what I need, I have what they need, and they have what you need.

### Democratic Governance
Run polls with liquid democracy — delegate your vote to someone you trust on topics you don't follow closely. Perfect for condominiums, cooperatives, and neighborhood associations.

### Transit & Routing
Real-time public transit information with GTFS integration. Plan multi-modal trips combining walking, cycling, and public transport.

## Getting Started

1. Create your profile and get verified by community members (Web of Trust)
2. Explore the local directory and marketplace
3. Join or create a condominium or cooperative
4. Participate in governance polls

Welcome aboard. This platform belongs to you.
""",
    },
    {
        'slug': 'bem-vindo-ao-parahub',
        'language': 'pt',
        'title': 'Bem-vindo ao Parahub — Infraestrutura Cívica para Comunidades',
        'meta_description': 'Apresentamos o Parahub: uma plataforma cívica auto-hospedada para comércio local, governança e ajuda mútua. Sem intermediários, sem taxas, sem vigilância.',
        'author': 'alice',
        'establishment': None,
        'is_pinned': False,
        'translation_of': 'welcome-to-parahub',
        'content': """\
O Parahub é uma plataforma de infraestrutura cívica de código aberto concebida para comunidades reais. Combina um diretório local, mercado peer-to-peer, ferramentas de governança democrática e sistemas de ajuda mútua — tudo sem intermediários.

## Porquê Mais Uma Plataforma?

A maioria das plataformas extrai valor das comunidades. Cobram taxas, recolhem dados e otimizam para o envolvimento em vez do bem-estar. O Parahub segue a abordagem oposta:

- **Sem custódia** — os fundos fluem diretamente entre pessoas
- **Sem vigilância** — encriptação do lado do cliente para dados sensíveis
- **Sem intermediários** — peer-to-peer por design
- **Sem dependência** — auto-hospedado, federado, código aberto

## O Que Pode Fazer

### Diretório Local
Encontre e liste empresas locais, cooperativas e serviços. Pense nisto como uma alternativa ao Google Maps pertencente à comunidade — com avaliações apoiadas por uma Rede de Confiança em vez de contas anónimas.

### Mercado P2P
Compre, venda e troque bens e serviços diretamente. O motor de troca pode até encontrar ciclos de troca multi-partes: você tem o que eu preciso, eu tenho o que eles precisam, e eles têm o que você precisa.

### Governança Democrática
Realize votações com democracia líquida — delegue o seu voto a alguém em quem confia nos temas que não acompanha de perto. Perfeito para condomínios, cooperativas e associações de moradores.

### Transportes e Rotas
Informação em tempo real sobre transportes públicos com integração GTFS. Planeie viagens multimodais combinando caminhada, ciclismo e transporte público.

## Como Começar

1. Crie o seu perfil e seja verificado por membros da comunidade (Rede de Confiança)
2. Explore o diretório local e o mercado
3. Junte-se ou crie um condomínio ou cooperativa
4. Participe nas votações de governança

Bem-vindo a bordo. Esta plataforma pertence-lhe.
""",
    },
    {
        'slug': 'condominium-management-guide',
        'language': 'en',
        'title': 'Managing Your Condominium with Parahub',
        'meta_description': 'A practical guide to using Parahub for condominium management: budgets, polls, maintenance, and compliance with Lei 8/2022.',
        'author': 'bob',
        'establishment': None,
        'is_pinned': False,
        'translation_of': None,
        'content': """\
If you manage a condominium — or live in one and want better transparency — Parahub has tools built specifically for you. This guide walks through the key features.

## Fractions and Permilagem

Portuguese law (Lei 8/2022) requires condominiums to track ownership fractions expressed in *permilagem* (parts per thousand). Parahub handles this natively: each unit has a fraction value, and voting power is calculated automatically.

## Democratic Decision-Making

Use governance polls for assembly decisions. Parahub supports:

- **Multiple choice** voting with configurable options
- **Liquid democracy** — residents can delegate their vote to someone they trust
- **Weighted by fraction** — respecting legal requirements for ownership-proportional voting
- **Audit trail** — every vote is logged with cryptographic proof

## Budget Management

The treasury system supports participatory budgeting:

1. Propose budget items (repairs, improvements, services)
2. Residents vote using median voting with sliders
3. Results are transparent and verifiable via Merkle proofs

## Maintenance Requests

Track maintenance through the platform. Create issues, assign contractors from the local directory, and manage timelines — all visible to residents who have a stake.

## Getting Started

1. Register your condominium as an establishment
2. Add units with their permilagem fractions
3. Invite residents to join
4. Create your first governance poll for an upcoming assembly

The goal is simple: make condominium management transparent, democratic, and efficient.
""",
    },
    {
        'slug': 'guia-gestao-condominio',
        'language': 'pt',
        'title': 'Gestão do Condomínio com o Parahub',
        'meta_description': 'Um guia prático para usar o Parahub na gestão de condomínios: orçamentos, votações, manutenção e conformidade com a Lei 8/2022.',
        'author': 'bob',
        'establishment': None,
        'is_pinned': False,
        'translation_of': 'condominium-management-guide',
        'content': """\
Se gere um condomínio — ou vive num e quer mais transparência — o Parahub tem ferramentas construídas especificamente para si. Este guia apresenta as funcionalidades principais.

## Frações e Permilagem

A lei portuguesa (Lei 8/2022) exige que os condomínios registem frações de propriedade expressas em *permilagem* (partes por mil). O Parahub trata disto nativamente: cada fração tem um valor, e o poder de voto é calculado automaticamente.

## Tomada de Decisão Democrática

Utilize votações de governança para decisões de assembleia. O Parahub suporta:

- **Escolha múltipla** com opções configuráveis
- **Democracia líquida** — os residentes podem delegar o voto em alguém de confiança
- **Ponderado por fração** — respeitando os requisitos legais de votação proporcional
- **Registo de auditoria** — cada voto é registado com prova criptográfica

## Gestão de Orçamento

O sistema de tesouraria suporta orçamento participativo:

1. Proponha itens orçamentais (reparações, melhorias, serviços)
2. Os residentes votam usando votação mediana com cursores
3. Os resultados são transparentes e verificáveis através de provas Merkle

## Pedidos de Manutenção

Acompanhe a manutenção através da plataforma. Crie pedidos, atribua prestadores do diretório local e gerencie prazos — tudo visível para os residentes interessados.

## Como Começar

1. Registe o seu condomínio como estabelecimento
2. Adicione as frações com os valores de permilagem
3. Convide os residentes a aderir
4. Crie a sua primeira votação para uma assembleia

O objetivo é simples: tornar a gestão do condomínio transparente, democrática e eficiente.
""",
    },
    {
        'slug': 'p2p-marketplace-guide',
        'language': 'en',
        'title': 'Getting Started with the P2P Marketplace',
        'meta_description': 'Learn how to buy, sell, and barter on Parahub. No fees, no middlemen — direct peer-to-peer trade with smart contract support.',
        'author': 'charlie',
        'establishment': None,
        'is_pinned': False,
        'translation_of': None,
        'content': """\
The Parahub marketplace is a peer-to-peer trading platform with no fees, no escrow, and no middlemen. Here's how to get started.

## Listing Items

Create a listing in minutes:

1. Go to the marketplace and click "New Listing"
2. Add photos, description, and price (or mark as barter-only)
3. Choose categories from the taxonomy to help buyers find you
4. Publish — your item is now visible to the community

## The Barter Engine

This is where it gets interesting. Parahub includes a barter cycle detection engine powered by Neo4j. If you want something but don't have cash, the system can find exchange chains:

> Alice has a bicycle and wants a guitar.
> Bob has a guitar and wants a camera.
> Charlie has a camera and wants a bicycle.
> → Three-way barter cycle detected!

The system finds cycles of up to 5 participants and notifies everyone involved.

## Contracts

For larger transactions, use the built-in P2P contract system:

- Both parties sign digitally (PGP)
- Contract terms are hashed (SHA256) for integrity
- Dual completion — both sides must confirm delivery
- Arbitration support if things go wrong

## Trust and Safety

All marketplace participants need Web of Trust verification (3+ community verifications). This Sybil defense keeps fake accounts out without requiring government ID or corporate gatekeepers.

## Tips

- Use clear, well-lit photos
- Be specific about condition and dimensions
- Respond to messages promptly
- Leave honest reviews after transactions

Happy trading!
""",
    },
    {
        'slug': 'transit-routing-showcase',
        'language': 'en',
        'title': 'Public Transit at Your Fingertips',
        'meta_description': 'Parahub integrates real-time transit data from multiple cities. Plan trips, track vehicles, and never miss a bus again.',
        'author': 'alice',
        'establishment': 'techhub-lisboa',
        'is_pinned': True,
        'translation_of': None,
        'content': """\
Parahub integrates real-time public transit data from cities across Europe and North America. Whether you're commuting to work or exploring a new city, we've got you covered.

## Supported Cities

We currently import GTFS data from these transit agencies:

| City | Agency | Real-time |
|------|--------|-----------|
| Lisbon | Carris Metropolitana | Yes |
| Lisbon | Carris (trams) | Yes |
| Porto | STCP | Yes |
| Helsinki | HSL | Yes |
| Prague | PID | Yes |
| Philadelphia | SEPTA | Yes |
| Seattle | King County Metro | Yes |
| Boston | MBTA | Yes |

## How It Works

### GTFS Integration
We import static GTFS feeds (routes, stops, schedules) and overlay real-time GTFS-RT data (vehicle positions, trip updates, service alerts). The result: accurate arrival predictions and live vehicle tracking on the map.

### Multi-Modal Routing
The routing engine combines:

- **MOTIS** (RAPTOR algorithm) for transit routing — fast, accurate, multi-modal
- **Valhalla** for street routing — walking, cycling, driving
- **MapLibre** for beautiful map rendering with Martin vector tiles

### The Map

Open the map and you'll see transit routes, stops, and (where available) live vehicle positions. Click any stop to see upcoming departures. Plan a trip by setting origin and destination — the router will find the best combination of walking and transit.

## Community Routes

Beyond imported GTFS data, community members can create custom routes through the transit management interface. These are exportable as GTFS and GTFS-RT feeds, making community-created transit data interoperable with any GTFS-compatible app.

## Driver Mode

If you're a transit driver (verified via Web of Trust), you can share your GPS position in real-time. Your location updates appear on the map for passengers tracking your vehicle. All powered by browser GPS and Redis — no special hardware needed.

Explore the map and plan your next trip!
""",
    },
]


# Mini-site for TechHub Lisboa
SITE_CONFIG = {
    'establishment_slug': 'techhub-lisboa',
    'accent_color': '#2563EB',
    'hero_text': """\
## TechHub Lisboa

Coworking, community, and collaboration in the heart of Lisbon. A space where local businesses, freelancers, and creators come together.

*Powered by Parahub — open-source civic infrastructure.*
""",
    'nav_sections': [
        {'type': 'blog', 'order': 1},
        {'type': 'gallery', 'order': 2},
        {'type': 'items', 'order': 3},
        {'type': 'contact', 'order': 4},
    ],
    'pages': [
        {
            'title': 'About Us',
            'slug': 'about',
            'order': 1,
            'content': """\
## About TechHub Lisboa

TechHub Lisboa is a community coworking space on Rua do Carmo in the heart of Lisbon's Chiado district. We provide affordable workspace, high-speed internet, meeting rooms, and a vibrant community of local professionals.

### Our Mission

We believe that independent workers, small businesses, and community organizations deserve access to professional workspace without corporate overhead. TechHub is run as a cooperative — decisions are made democratically by members.

### Facilities

- **40 hot desks** with ergonomic chairs and 27" monitors
- **4 meeting rooms** (2-8 people) with video conferencing
- **Event space** for up to 50 people
- **Kitchen** with free coffee, tea, and filtered water
- **Bike storage** and shower facilities
- **24/7 access** for monthly members

### Membership

| Plan | Price | Includes |
|------|-------|----------|
| Day pass | €15 | Desk, wifi, coffee |
| Weekly | €60 | All facilities |
| Monthly | €180 | All facilities + 24/7 access |
| Team (3+) | €150/person | Dedicated area + meeting room credits |

### Community Events

We host weekly community events including tech talks, startup pitches, language exchanges, and co-learning sessions. Check our blog for upcoming events.
""",
        },
        {
            'title': 'Services',
            'slug': 'services',
            'order': 2,
            'content': """\
## Services

Beyond coworking, TechHub Lisboa offers services to help local businesses grow.

### For Businesses

- **Virtual office** — Lisbon business address, mail handling, phone answering
- **Company registration** — we partner with local accountants for NIF/company setup
- **Meeting rooms** — hourly rental for non-members, with projector and whiteboard

### For Freelancers

- **Community introductions** — we connect freelancers with local businesses who need their skills
- **Invoice management** — integration with Portuguese e-fatura through our accounting partners
- **Workspace** — quiet zones for focused work, social areas for collaboration

### For Events

- **Space rental** — our event space fits 50 people with chairs or 30 with tables
- **A/V equipment** — projector, microphones, streaming setup
- **Catering** — partnerships with local restaurants for event catering

### Technology

All our systems run on Parahub — from membership management to event organization. As a cooperative, we practice what we preach: transparent governance, democratic decision-making, and community ownership.

Contact us at hello@techhub-lisboa.pt or visit during opening hours.
""",
        },
        {
            'title': 'Community',
            'slug': 'community',
            'order': 3,
            'content': """\
## Community

TechHub Lisboa is more than a workspace — it's a community of people building things that matter.

### Who Works Here

Our members include web developers, designers, translators, architects, environmental consultants, social workers, and small business owners. What they share: a commitment to local community and independent work.

### Cooperativa TechHub

TechHub operates as a cooperative under Portuguese law. Every monthly member gets a vote in major decisions — from pricing changes to renovation plans. We use Parahub's governance tools for transparent, auditable voting.

### Partnerships

We collaborate with:

- **Local businesses** listed in the Parahub directory
- **Lisbon municipality** on digital inclusion programs
- **Portuguese cooperative federation** (CASES)
- **University of Lisbon** for internship placements

### Open Source

All our internal tools are built on Parahub, which is fully open source. If you're a developer interested in civic technology, we welcome contributions. Check our Gitea repository or join our Matrix chat.

### Join Us

The best way to experience TechHub is to drop by. Grab a day pass, try the wifi, meet the community, and see if it fits. No pressure, no long-term contracts.

**Address:** Rua do Carmo 45, 3rd floor, 1200-093 Lisboa
**Hours:** Mon-Fri 08:00-22:00, Sat 09:00-18:00
**Email:** hello@techhub-lisboa.pt
""",
        },
    ],
}


class Command(BaseCommand):
    help = 'Seed demo CMS content: blog posts and a mini-site for Show HN'

    DEMO_MARKER = {'demo': True}

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete demo CMS objects before recreating',
        )

    def _get_test_profiles(self):
        """Return dict of username -> Profile for test users."""
        profiles = Profile.objects.filter(
            account__groups__name='test_users'
        ).select_related('account')
        return {p.account.username: p for p in profiles}

    def _get_demo_establishment(self, slug):
        """Get a demo establishment by slug."""
        try:
            return Establishment.objects.get(slug=slug)
        except Establishment.DoesNotExist:
            return None

    def _reset(self):
        """Delete only demo-marked CMS objects."""
        pages_del = SitePage.objects.filter(attributes__demo=True).delete()
        self.stdout.write(self.style.WARNING(f'Deleted {pages_del[0]} demo SitePages'))

        posts_del = Post.objects.filter(attributes__demo=True).delete()
        self.stdout.write(self.style.WARNING(f'Deleted {posts_del[0]} demo Posts'))

        sites_del = Site.objects.filter(attributes__demo=True).delete()
        self.stdout.write(self.style.WARNING(f'Deleted {sites_del[0]} demo Sites'))

    def _seed_posts(self, profiles):
        """Create blog posts with translations."""
        now = timezone.now()
        created_posts = {}  # slug -> Post
        post_count = 0

        for i, post_data in enumerate(POSTS):
            author = profiles.get(post_data['author'])
            if not author:
                self.stdout.write(self.style.WARNING(
                    f'Author {post_data["author"]} not found, skipping post: {post_data["title"]}'
                ))
                continue

            # Resolve establishment
            establishment = None
            if post_data['establishment']:
                establishment = self._get_demo_establishment(post_data['establishment'])
                if not establishment:
                    self.stdout.write(self.style.WARNING(
                        f'Establishment {post_data["establishment"]} not found, creating as personal post'
                    ))

            # Resolve translation_of
            translation_of = None
            if post_data['translation_of']:
                translation_of = created_posts.get(post_data['translation_of'])

            # Check if already exists
            qs = Post.objects.filter(slug=post_data['slug'])
            if establishment:
                qs = qs.filter(establishment=establishment)
            else:
                qs = qs.filter(author=author, establishment__isnull=True)
            if qs.exists():
                created_posts[post_data['slug']] = qs.first()
                self.stdout.write(f'  Post already exists: {post_data["title"]}')
                continue

            post = Post(
                author=author,
                establishment=establishment,
                title=post_data['title'],
                slug=post_data['slug'],
                content=post_data['content'].strip(),
                language=post_data['language'],
                translation_of=translation_of,
                meta_description=post_data['meta_description'],
                status='published',
                published_at=now - timedelta(days=len(POSTS) - i),
                is_pinned=post_data['is_pinned'],
                allow_comments=True,
                allow_tips=True,
                attributes={'demo': True},
            )
            post.save()
            created_posts[post_data['slug']] = post
            post_count += 1

            label = f'[{post.language.upper()}]'
            if establishment:
                label += f' @{establishment.slug}'
            if translation_of:
                label += f' (translation of: {post_data["translation_of"]})'

            self.stdout.write(self.style.SUCCESS(
                f'  + {label} {post.title} — by {post_data["author"]}'
            ))

        return post_count

    def _seed_site(self, profiles):
        """Create mini-site for demo establishment."""
        cfg = SITE_CONFIG
        establishment = self._get_demo_establishment(cfg['establishment_slug'])
        if not establishment:
            self.stdout.write(self.style.WARNING(
                f'Establishment {cfg["establishment_slug"]} not found. '
                f'Run seed_demo_establishments first.'
            ))
            return 0, 0

        # Check if a non-demo site already exists for this establishment
        existing = Site.objects.filter(establishment=establishment).first()
        if existing and not existing.attributes.get('demo'):
            self.stdout.write(self.style.WARNING(
                f'Non-demo site already exists for {establishment.name}, skipping'
            ))
            return 0, 0

        # Create or update site
        site, created = Site.objects.update_or_create(
            establishment=establishment,
            defaults={
                'accent_color': cfg['accent_color'],
                'hero_text': cfg['hero_text'].strip(),
                'nav_sections': cfg['nav_sections'],
                'is_active': True,
                'attributes': {'demo': True},
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS(
                f'  + Site for {establishment.name} (accent: {cfg["accent_color"]})'
            ))
        else:
            self.stdout.write(f'  Updated site for {establishment.name}')

        # Create pages
        page_count = 0
        for page_data in cfg['pages']:
            existing_page = SitePage.objects.filter(
                site=site, slug=page_data['slug']
            ).first()
            if existing_page:
                self.stdout.write(f'  Page already exists: {page_data["title"]}')
                continue

            SitePage.objects.create(
                site=site,
                title=page_data['title'],
                slug=page_data['slug'],
                content=page_data['content'].strip(),
                order=page_data['order'],
                show_in_nav=True,
                is_published=True,
                attributes={'demo': True},
            )
            page_count += 1
            self.stdout.write(self.style.SUCCESS(
                f'  + Page: {page_data["title"]} (/{page_data["slug"]})'
            ))

        return 1 if created else 0, page_count

    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        profiles = self._get_test_profiles()
        if not profiles:
            self.stdout.write(self.style.ERROR(
                'No test users found. Run: python3 manage.py seed_test_users'
            ))
            return

        self.stdout.write('\n--- Blog Posts ---')
        post_count = self._seed_posts(profiles)

        self.stdout.write('\n--- Mini-site ---')
        site_count, page_count = self._seed_site(profiles)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {post_count} posts, {site_count} sites, {page_count} pages created'
        ))
