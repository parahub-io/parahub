#!/usr/bin/env python3
"""
Test script for barter exchange cycle detection
Tests the /api/v1/barter/opportunities endpoint with test users
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/opt/parahub')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')
django.setup()

import requests
from identity.models import Account, Profile
from parahub.auth import create_tokens_for_user
from market.models import Item
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.panel import Panel

console = Console()


def get_test_user_tokens():
    """Get JWT tokens for test users"""
    test_users = Account.objects.filter(groups__name='test_users')

    if not test_users.exists():
        console.print("[red]No test users found! Run: python3 manage.py seed_test_users[/red]")
        sys.exit(1)

    tokens = {}
    for user in test_users:
        token_data = create_tokens_for_user(user)
        profile = user.profiles.first()
        tokens[user.username] = {
            'token': token_data['access_token'],
            'profile': profile,
            'cri': profile.id if profile else None,
            'hna': profile.hna if profile else None,
        }

    return tokens


def test_barter_opportunities(base_url='http://127.0.0.1:8000'):
    """Test barter opportunities API for each user"""
    console.print("\n[bold cyan]Testing Barter Exchange Cycles[/bold cyan]\n")

    # Get tokens
    tokens = get_test_user_tokens()
    console.print(f"[green]Found {len(tokens)} test users[/green]\n")

    # Show test users and their items
    for username, data in tokens.items():
        profile = data['profile']
        items_credit = Item.objects.filter(owner=profile, type='CREDIT', is_active=True)
        items_debit = Item.objects.filter(owner=profile, type='DEBIT', is_active=True)

        console.print(f"[bold]{username}[/bold] ({data['hna']})")
        console.print(f"  CREDIT (offers): {items_credit.count()}")
        for item in items_credit:
            console.print(f"    • {item.title} ({item.category.slug})")
        console.print(f"  DEBIT (wants): {items_debit.count()}")
        for item in items_debit:
            console.print(f"    • {item.title} ({item.category.slug})")
        console.print()

    # Test API for each user
    console.print("[bold cyan]Testing /api/v1/barter/opportunities endpoint[/bold cyan]\n")

    results = {}
    for username, data in tokens.items():
        console.print(f"[bold yellow]Testing as {username}...[/bold yellow]")

        headers = {
            'Authorization': f'Bearer {data["token"]}',
            'Content-Type': 'application/json'
        }

        url = f"{base_url}/api/v1/barter/opportunities"

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                chains = data.get('chains', [])
                results[username] = chains

                console.print(f"  Status: [green]200 OK[/green]")
                console.print(f"  Found: [bold]{len(chains)}[/bold] exchange opportunities\n")

                if chains:
                    for idx, opp in enumerate(chains, 1):
                        users = opp.get('users', [])
                        swaps = opp.get('swaps', [])

                        # Determine cycle type
                        cycle_type = f"{len(users)}-way cycle"
                        if len(users) == 2:
                            cycle_type = "2-way (direct)"
                        elif len(users) == 3:
                            cycle_type = "3-way (triangular)"

                        console.print(f"  [bold cyan]Opportunity #{idx}[/bold cyan] ({cycle_type})")
                        console.print(f"    Users: {' → '.join([f'{u[:8]}...' for u in users])}")
                        console.print(f"    Swaps: {len(swaps)}")

                        for swap_idx, swap in enumerate(swaps, 1):
                            from_user = swap['from_user'][:12]
                            to_user = swap['to_user'][:12]
                            offered_items = swap.get('offered_items', [])
                            wanted_items = swap.get('wanted_items', [])

                            # Format offered/wanted items
                            offered_str = ', '.join([item['title'] for item in offered_items]) if offered_items else 'N/A'
                            wanted_str = ', '.join([item['title'] for item in wanted_items]) if wanted_items else 'N/A'

                            console.print(f"      {swap_idx}. {from_user}... → {to_user}...")
                            console.print(f"         Offers: {offered_str}")
                            console.print(f"         Wants:  {wanted_str}")
                        console.print()
                else:
                    console.print("  [yellow]No exchange cycles found for this user[/yellow]\n")
            else:
                console.print(f"  Status: [red]{response.status_code}[/red]")
                console.print(f"  Error: {response.text}\n")
                results[username] = {'error': response.status_code, 'message': response.text}

        except Exception as e:
            console.print(f"  [red]Exception: {e}[/red]\n")
            results[username] = {'error': 'exception', 'message': str(e)}

    # Summary
    console.print("\n[bold cyan]Summary[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("User", style="cyan")
    table.add_column("Opportunities Found", justify="center")
    table.add_column("2-way", justify="center")
    table.add_column("3-way", justify="center")
    table.add_column("4-way+", justify="center")

    for username, data in results.items():
        if isinstance(data, list):
            total = len(data)
            two_way = sum(1 for o in data if len(o.get('users', [])) == 2)
            three_way = sum(1 for o in data if len(o.get('users', [])) == 3)
            four_way_plus = sum(1 for o in data if len(o.get('users', [])) >= 4)

            table.add_row(
                username,
                str(total),
                str(two_way),
                str(three_way),
                str(four_way_plus)
            )
        else:
            table.add_row(username, "[red]ERROR[/red]", "-", "-", "-")

    console.print(table)
    console.print()

    # Check if we have expected cycles
    total_opportunities = sum(len(r) for r in results.values() if isinstance(r, list))

    if total_opportunities >= 4:
        console.print(Panel(
            "[bold green]✓ SUCCESS[/bold green]\n"
            f"Found {total_opportunities} exchange opportunities across all users.\n"
            "The test data is working correctly!",
            title="Test Result",
            border_style="green"
        ))
    else:
        console.print(Panel(
            "[bold yellow]⚠ WARNING[/bold yellow]\n"
            f"Only found {total_opportunities} exchange opportunities.\n"
            "Expected at least 4 cycles (2 direct + 2 triangular).\n"
            "Check if all test items were created correctly.",
            title="Test Result",
            border_style="yellow"
        ))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test barter exchange cycle detection')
    parser.add_argument(
        '--url',
        default='http://127.0.0.1:8000',
        help='Base URL for API (default: http://127.0.0.1:8000)'
    )

    args = parser.parse_args()

    test_barter_opportunities(base_url=args.url)
