"""
Deploy & Verify — automated deployment verification for Vercel projects.

Usage:
    python execution/deploy_verify.py --url https://247growth.org --checks routes.json
    python execution/deploy_verify.py --url https://247profits.org --checks routes.json --max-retries 3

Checks file format (JSON):
[
    {"path": "/", "status": 200, "contains": "Dashboard"},
    {"path": "/api/health", "status": 200, "contains": "ok"},
    {"path": "/login", "status": 200}
]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import ssl


def verify_endpoint(base_url: str, check: dict, timeout: int = 10) -> dict:
    """Verify a single endpoint returns expected status and content."""
    url = f"{base_url.rstrip('/')}{check['path']}"
    expected_status = check.get("status", 200)
    contains = check.get("contains")

    result = {
        "path": check["path"],
        "url": url,
        "expected_status": expected_status,
        "passed": False,
        "error": None,
    }

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "DeployVerify/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        actual_status = resp.getcode()
        body = resp.read().decode("utf-8", errors="replace")

        result["actual_status"] = actual_status

        if actual_status != expected_status:
            result["error"] = f"Status {actual_status} != expected {expected_status}"
            return result

        if contains and contains.lower() not in body.lower():
            result["error"] = f"Response body missing expected text: '{contains}'"
            return result

        # Check for auth walls (common Vercel issue)
        auth_indicators = ["sign in", "log in", "authentication required", "unauthorized"]
        if expected_status == 200 and any(ind in body.lower() for ind in auth_indicators):
            if not check.get("auth_expected"):
                result["error"] = "Page appears to be behind an auth wall"
                return result

        result["passed"] = True
    except urllib.error.HTTPError as e:
        result["actual_status"] = e.code
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["error"] = f"URL error: {e.reason}"
    except Exception as e:
        result["error"] = str(e)

    return result


def run_verification(base_url: str, checks: list[dict], max_retries: int = 2, retry_delay: int = 10) -> bool:
    """Run all checks with retry logic."""
    print(f"\n{'='*60}")
    print(f"Deploy Verification: {base_url}")
    print(f"{'='*60}\n")

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"\n--- Retry {attempt}/{max_retries} (waiting {retry_delay}s) ---\n")
            time.sleep(retry_delay)

        results = []
        all_passed = True

        for check in checks:
            result = verify_endpoint(base_url, check)
            results.append(result)

            status = "PASS" if result["passed"] else "FAIL"
            icon = "+" if result["passed"] else "x"
            print(f"  [{icon}] {status}  {check['path']}", end="")
            if not result["passed"]:
                print(f"  -- {result['error']}")
                all_passed = False
            else:
                print()

        if all_passed:
            print(f"\n  All {len(checks)} checks passed.\n")
            return True

        failed = [r for r in results if not r["passed"]]
        print(f"\n  {len(failed)}/{len(checks)} checks failed.")

    print(f"\n  Verification FAILED after {max_retries} attempts.\n")

    # Print diagnostic summary
    print("Diagnostics:")
    for r in results:
        if not r["passed"]:
            print(f"  - {r['path']}: {r['error']}")
            if r.get("actual_status") == 404:
                print(f"    Likely cause: route not configured in vercel.json or missing page")
            elif r.get("actual_status") in (401, 403):
                print(f"    Likely cause: auth wall or missing env var")
            elif "auth wall" in str(r.get("error", "")):
                print(f"    Likely cause: Vercel preview protection or missing public access")

    return False


def main():
    parser = argparse.ArgumentParser(description="Verify deployment endpoints")
    parser.add_argument("--url", required=True, help="Base URL to verify (e.g., https://247growth.org)")
    parser.add_argument("--checks", required=True, help="JSON file with endpoint checks")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retry attempts (default: 2)")
    parser.add_argument("--retry-delay", type=int, default=10, help="Seconds between retries (default: 10)")
    args = parser.parse_args()

    with open(args.checks) as f:
        checks = json.load(f)

    success = run_verification(args.url, checks, args.max_retries, args.retry_delay)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
