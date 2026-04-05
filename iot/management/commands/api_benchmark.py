"""
Measure API response time baseline for top endpoints.

Usage:
    python3 manage.py api_benchmark [--requests 100] [--base-url http://localhost:8000]
    python3 manage.py api_benchmark --save  # saves JSON report to .agents/reports/
"""

import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Measure p50/p95/p99/max response times for top API endpoints"

    def add_arguments(self, parser):
        parser.add_argument(
            "--requests", type=int, default=100,
            help="Number of requests per endpoint (default: 100)"
        )
        parser.add_argument(
            "--base-url", type=str, default="http://localhost:8000",
            help="Base URL to test against (default: http://localhost:8000)"
        )
        parser.add_argument(
            "--save", action="store_true",
            help="Save results to .agents/reports/api-baseline-YYYY-MM-DD.json"
        )

    def handle(self, *args, **options):
        base = options["base_url"].rstrip("/")
        num_requests = options["requests"]

        # Get test user credentials
        pw_file = Path(settings.BASE_DIR) / ".test_users_password"
        if not pw_file.exists():
            self.stderr.write("Run 'manage.py seed_test_users' first.")
            return

        password = None
        for line in pw_file.read_text().splitlines():
            if line.startswith("alice:"):
                password = line.split(":", 1)[1]
                break

        if not password:
            self.stderr.write("alice not found in .test_users_password")
            return

        # Get JWT token for alice (regular user)
        r = requests.post(f"{base}/api/v1/auth/token/", json={
            "username": "alice", "password": password
        })
        if r.status_code != 200:
            self.stderr.write(f"Auth failed: {r.status_code} {r.text}")
            return
        user_token = r.json()["access_token"]

        # Get staff token for admin
        from identity.models import Account
        admin = Account.objects.filter(is_staff=True).first()
        if admin:
            from parahub.auth import create_tokens_for_user
            staff_token = create_tokens_for_user(admin)["access_token"]
        else:
            staff_token = None

        # Get a real item ID for detail endpoint
        from market.models import Item
        item = Item.objects.first()
        item_id = item.id if item else "nonexistent"

        # Define endpoints
        endpoints = [
            {
                "name": "GET /api/v1/profiles/me/",
                "method": "GET",
                "url": f"{base}/api/v1/profiles/me/",
                "auth": "user",
            },
            {
                "name": "GET /api/v1/items/",
                "method": "GET",
                "url": f"{base}/api/v1/items/",
                "auth": None,
            },
            {
                "name": f"GET /api/v1/items/<id>/",
                "method": "GET",
                "url": f"{base}/api/v1/items/{item_id}/",
                "auth": None,
            },
            {
                "name": "GET /api/v1/geo/establishments/",
                "method": "GET",
                "url": f"{base}/api/v1/geo/establishments/",
                "auth": None,
            },
            {
                "name": "GET /api/v1/geo/geocode/search",
                "method": "GET",
                "url": f"{base}/api/v1/geo/geocode/search?q=lisbon",
                "auth": None,
            },
            {
                "name": "GET /api/v1/governance/polls/",
                "method": "GET",
                "url": f"{base}/api/v1/governance/polls/",
                "auth": None,
            },
            {
                "name": "GET /api/v1/partners/list/",
                "method": "GET",
                "url": f"{base}/api/v1/partners/list/",
                "auth": "user",
            },
            {
                "name": "GET /api/v1/geo/transit/routes/",
                "method": "GET",
                "url": f"{base}/api/v1/geo/transit/routes/",
                "auth": None,
            },
            {
                "name": "POST /api/v1/auth/token/",
                "method": "POST",
                "url": f"{base}/api/v1/auth/token/",
                "auth": None,
                "json": {"username": "alice", "password": password},
            },
            {
                "name": "GET /api/v1/iot/server/health",
                "method": "GET",
                "url": f"{base}/api/v1/iot/server/health",
                "auth": "staff",
            },
        ]

        results = []
        threshold_ms = 50
        violations = []

        self.stdout.write(f"\nAPI Benchmark: {num_requests} requests per endpoint")
        self.stdout.write(f"Target: {base}")
        self.stdout.write("=" * 72)

        session = requests.Session()

        for ep in endpoints:
            # Build headers
            headers = {}
            if ep["auth"] == "user":
                headers["Authorization"] = f"Bearer {user_token}"
            elif ep["auth"] == "staff":
                if not staff_token:
                    self.stdout.write(f"  SKIP {ep['name']} (no staff user)")
                    results.append({
                        "endpoint": ep["name"],
                        "skipped": True,
                        "reason": "no staff user",
                    })
                    continue
                headers["Authorization"] = f"Bearer {staff_token}"

            # Warmup (2 requests, discarded)
            for _ in range(2):
                try:
                    if ep["method"] == "POST":
                        session.post(ep["url"], json=ep.get("json"), headers=headers, timeout=10)
                    else:
                        session.get(ep["url"], headers=headers, timeout=10)
                except Exception:
                    pass

            # Measure
            times_ms = []
            errors = 0
            status_codes = {}

            for i in range(num_requests):
                try:
                    start = time.perf_counter()
                    if ep["method"] == "POST":
                        resp = session.post(ep["url"], json=ep.get("json"), headers=headers, timeout=10)
                    else:
                        resp = session.get(ep["url"], headers=headers, timeout=10)
                    elapsed = (time.perf_counter() - start) * 1000  # ms

                    times_ms.append(elapsed)
                    status_codes[resp.status_code] = status_codes.get(resp.status_code, 0) + 1
                except Exception as e:
                    errors += 1

            if not times_ms:
                self.stdout.write(f"  FAIL {ep['name']} — all {errors} requests failed")
                results.append({
                    "endpoint": ep["name"],
                    "error": f"all {errors} requests failed",
                })
                continue

            times_ms.sort()
            p50 = times_ms[len(times_ms) * 50 // 100]
            p95 = times_ms[len(times_ms) * 95 // 100]
            p99 = times_ms[len(times_ms) * 99 // 100]
            max_t = times_ms[-1]
            mean = statistics.mean(times_ms)

            flag = " *** EXCEEDS 50ms p95" if p95 > threshold_ms else ""

            self.stdout.write(
                f"  {ep['name']}\n"
                f"    p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms  "
                f"max={max_t:.1f}ms  mean={mean:.1f}ms  "
                f"status={status_codes}  errors={errors}{flag}"
            )

            result = {
                "endpoint": ep["name"],
                "requests": num_requests,
                "successful": len(times_ms),
                "errors": errors,
                "status_codes": {str(k): v for k, v in status_codes.items()},
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "max_ms": round(max_t, 2),
                "mean_ms": round(mean, 2),
                "min_ms": round(times_ms[0], 2),
            }
            results.append(result)

            if p95 > threshold_ms:
                violations.append(result)

        # Summary
        self.stdout.write("\n" + "=" * 72)
        if violations:
            self.stdout.write(
                f"\n*** {len(violations)} endpoint(s) EXCEED {threshold_ms}ms p95 threshold:"
            )
            for v in violations:
                self.stdout.write(f"  - {v['endpoint']}: p95={v['p95_ms']}ms")
        else:
            self.stdout.write(f"\nAll endpoints within {threshold_ms}ms p95 threshold.")

        # Build report
        report = {
            "timestamp": datetime.now().isoformat(),
            "base_url": base,
            "requests_per_endpoint": num_requests,
            "threshold_ms": threshold_ms,
            "results": results,
            "violations": [v["endpoint"] for v in violations],
            "summary": {
                "total_endpoints": len(endpoints),
                "measured": sum(1 for r in results if "p95_ms" in r),
                "skipped": sum(1 for r in results if r.get("skipped")),
                "failed": sum(1 for r in results if "error" in r),
                "violations": len(violations),
            },
        }

        if options["save"]:
            reports_dir = Path(settings.BASE_DIR) / ".agents" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            filename = f"api-baseline-{datetime.now().strftime('%Y-%m-%d')}.json"
            filepath = reports_dir / filename
            filepath.write_text(json.dumps(report, indent=2))
            self.stdout.write(f"\nSaved to {filepath}")

        # Print JSON to stdout regardless
        self.stdout.write(f"\n{json.dumps(report, indent=2)}")
