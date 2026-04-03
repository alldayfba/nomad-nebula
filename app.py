import glob
import json
import csv
import io
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect
from flask_cors import CORS

# Lazy imports for modules with heavy deps (playwright, etc.)
# These won't be available on Vercel but the web UI routes still work
try:
    from scraper import run_scraper
except ImportError:
    run_scraper = None  # type: ignore

# Make execution/ importable
sys.path.insert(0, str(Path(__file__).parent / "execution"))
try:
    from generate_business_audit import run_audit
except ImportError:
    run_audit = None  # type: ignore

app = Flask(__name__)

# Register AI Setter dashboard blueprint
try:
    from execution.setter.setter_dashboard import setter_bp
    app.register_blueprint(setter_bp)
except ImportError:
    pass
CORS(app, resources={
    r"/api/*": {"origins": [
        "https://247profits.org",
        "https://247growth.org",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]},
    r"/nova/*": {"origins": [
        "https://247profits.org",
        "https://www.247profits.org",
        "https://247growth.org",
        "https://www.247growth.org",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]},  # Nova API — CORS restricted to known SaaS origins
})

# ── Concurrency controls ─────────────────────────────────────────────────────
_sourcing_semaphore = threading.Semaphore(int(os.environ.get("MAX_CONCURRENT_SCANS", "3")))
_sourcing_lock = threading.Lock()


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/offer")
def offer_breakdown():
    return render_template("offer-breakdown.html")


@app.route("/leads")
def leads():
    return render_template("index.html")


@app.route("/scrape", methods=["POST"])
def scrape():
    data = request.get_json()
    query = data.get("query", "").strip()
    location = data.get("location", "").strip()
    max_results = int(data.get("max_results", 20))
    fetch_emails = bool(data.get("fetch_emails", True))

    if not query or not location:
        return jsonify({"error": "Query and location are required."}), 400

    try:
        results = run_scraper(query, location, max_results, fetch_emails)
        return jsonify({"results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export", methods=["POST"])
def export_csv():
    data = request.get_json()
    results = data.get("results", [])

    if not results:
        return jsonify({"error": "No results to export."}), 400

    fieldnames = ["business_name", "owner_name", "category", "phone", "email", "website", "address", "rating", "maps_url"]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in results:
        writer.writerow({k: row.get(k, "N/A") for k in fieldnames})

    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=b2b_leads.csv"}
    )


@app.route("/audit")
def audit():
    return render_template("audit.html")


@app.route("/audit/generate", methods=["POST"])
def generate_audit():
    data = request.get_json()
    business = data.get("business", {})

    if not business.get("business_name", "").strip():
        return jsonify({"error": "Business name is required."}), 400

    q = queue.Queue()

    def progress_cb(step, total, msg):
        q.put({"type": "progress", "step": step, "total": total, "message": msg})

    def run():
        try:
            result = run_audit(business, progress_cb=progress_cb)
            q.put({"type": "done", "result": result})
        except Exception as e:
            q.put({"type": "done", "result": {"ok": False, "error": str(e)}})

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def stream():
        while True:
            try:
                event = q.get(timeout=120)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Audit timed out after 2 minutes.'})}\n\n"
                break

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/sourcing")
def sourcing():
    return render_template("sourcing.html")


@app.route("/sourcing/run", methods=["POST"])
def run_sourcing():
    """Run the FBA sourcing pipeline. Uses SSE for progress streaming."""
    data = request.get_json()
    url = data.get("url", "").strip()
    min_roi = float(data.get("min_roi", 30))
    min_profit = float(data.get("min_profit", 3.0))
    max_price = float(data.get("max_price", 50.0))
    max_products = int(data.get("max_products", 50))

    if not url:
        return jsonify({"error": "URL is required."}), 400

    q = queue.Queue()

    def run():
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp_dir = Path(__file__).parent / ".tmp" / "sourcing"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(tmp_dir / f"{ts}-results.json")

            script = Path(__file__).parent / "execution" / "run_sourcing_pipeline.py"
            python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
            cmd = [python, str(script),
                   "--url", url,
                   "--min-roi", str(min_roi),
                   "--min-profit", str(min_profit),
                   "--max-price", str(max_price),
                   "--max-products", str(max_products),
                   "--output", out_path]

            q.put({"type": "progress", "step": 1, "total": 3,
                    "message": "Scraping retail products..."})

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                q.put({"type": "done", "result": {"ok": False, "error": result.stderr[-500:]}})
                return

            with open(out_path) as f:
                results = json.load(f)

            q.put({"type": "done", "result": {"ok": True, "data": results}})

        except subprocess.TimeoutExpired:
            q.put({"type": "done", "result": {"ok": False, "error": "Pipeline timed out after 10 minutes."}})
        except Exception as e:
            q.put({"type": "done", "result": {"ok": False, "error": str(e)}})

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def stream():
        while True:
            try:
                event = q.get(timeout=300)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Sourcing timed out after 5 minutes.'})}\n\n"
                break

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/sourcing/search", methods=["POST"])
def run_multi_search():
    """Multi-retailer product search. Uses SSE for progress streaming."""
    data = request.get_json()
    query = data.get("query", "").strip()
    category = data.get("category", "").strip() or None
    max_retailers = int(data.get("max_retailers", 10))
    max_per_retailer = int(data.get("max_per_retailer", 5))
    min_roi = float(data.get("min_roi", 30))
    min_profit = float(data.get("min_profit", 3.0))
    max_price = float(data.get("max_price", 50.0))
    mode = data.get("mode", "search")  # "search" or "clearance"

    if mode == "search" and not query:
        return jsonify({"error": "Product query is required."}), 400

    q = queue.Queue()

    def run():
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp_dir = Path(__file__).parent / ".tmp" / "sourcing"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(tmp_dir / f"{ts}-multi-results.json")

            script = Path(__file__).parent / "execution" / "multi_retailer_search.py"
            python = str(Path(__file__).parent / ".venv" / "bin" / "python3")

            cmd = [python, str(script), mode]
            if mode == "search":
                cmd.extend(["--query", query])
            if category:
                cmd.extend(["--category", category])
            cmd.extend([
                "--max-retailers", str(max_retailers),
                "--max-per-retailer", str(max_per_retailer),
                "--min-roi", str(min_roi),
                "--min-profit", str(min_profit),
                "--max-price", str(max_price),
                "--auto-cashback",
                "--output", out_path,
            ])

            q.put({"type": "progress", "step": 1, "total": 3,
                    "message": f"Searching {max_retailers} retailers for '{query or 'clearance'}'..."})

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

            if result.returncode != 0:
                q.put({"type": "done", "result": {"ok": False, "error": result.stderr[-500:]}})
                return

            with open(out_path) as f:
                results = json.load(f)

            q.put({"type": "done", "result": {"ok": True, "data": results}})

        except subprocess.TimeoutExpired:
            q.put({"type": "done", "result": {"ok": False, "error": "Multi-search timed out after 15 minutes."}})
        except Exception as e:
            q.put({"type": "done", "result": {"ok": False, "error": str(e)}})

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def stream():
        while True:
            try:
                event = q.get(timeout=600)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Multi-search timed out.'})}\n\n"
                break

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/sourcing/retailers", methods=["GET"])
def list_retailers_for_query():
    """Dry-run: return which retailers would be searched for a query."""
    query = request.args.get("query", "").strip()
    category = request.args.get("category", "").strip() or None
    max_r = int(request.args.get("max", 15))

    sys.path.insert(0, str(Path(__file__).parent / "execution"))
    from retailer_registry import get_retailers_for_product, detect_category, get_search_url

    categories = detect_category(query) if query else []
    if category:
        categories = [category]

    retailers = get_retailers_for_product(category or query or "General", max_r)

    return jsonify({
        "query": query,
        "detected_categories": categories,
        "retailers": [
            {
                "name": r["name"],
                "key": r["key"],
                "tier": r["tier"],
                "cashback": r.get("cashback_percent", 0),
                "categories": r.get("categories", []),
                "search_url": get_search_url(r, query) if query else r.get("clearance_url"),
            }
            for r in retailers
        ],
        "count": len(retailers),
    })


@app.route("/sourcing/cli", methods=["POST"])
def run_sourcing_cli():
    """Run source.py CLI mode via subprocess. Supports all modes (brand, oos, deals, a2a, finder)."""
    data = request.get_json()
    mode = data.get("mode", "").strip()
    if not mode:
        return jsonify({"error": "Mode is required."}), 400

    # Build CLI args from form data
    cli_args = [mode]
    # Positional args (brand name for 'brand' mode)
    if mode == "brand" and data.get("brand_name"):
        cli_args.append(data["brand_name"])
    if mode == "category" and data.get("category"):
        cli_args.append(data["category"])

    # Named args mapping
    arg_map = {
        "retailers": "--retailers",
        "max": "--max",
        "count": "--count",
        "min_profit": "--min-profit",
        "min_drop": "--min-drop",
        "max_bsr": "--max-bsr",
        "min_reviews": "--min-reviews",
        "min_price": "--min-price",
        "max_price": "--max-price",
        "a2a_type": "--type",
        "min_discount": "--min-discount",
        "price_range": "--price-range",
        "deep_verify": "--deep-verify",
        "category_id": "--category",
    }
    for key, flag in arg_map.items():
        val = data.get(key)
        if val is not None and val != "":
            cli_args.extend([flag, str(val)])

    # Boolean flags
    if data.get("reverse_source"):
        cli_args.append("--reverse-source")

    q = queue.Queue()

    def run():
        try:
            script = Path(__file__).parent / "execution" / "source.py"
            python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
            cmd = [python, str(script)] + cli_args

            q.put({"type": "progress", "step": 1, "total": 2,
                   "message": f"Running {mode} scan..."})

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

            # source.py prints formatted text to stdout, JSON saved to .tmp/
            # Find the most recent results JSON
            tmp_dir = Path(__file__).parent / ".tmp" / "sourcing"
            json_files = sorted(tmp_dir.glob("*_source_results.json"), reverse=True)

            if json_files:
                with open(json_files[0]) as f:
                    results = json.load(f)
                q.put({"type": "done", "result": {
                    "ok": True,
                    "data": results,
                    "stdout": result.stdout[-2000:] if result.stdout else "",
                    "mode": mode,
                }})
            elif result.returncode == 0:
                q.put({"type": "done", "result": {
                    "ok": True, "data": [],
                    "stdout": result.stdout[-2000:] if result.stdout else "No results found.",
                    "mode": mode,
                }})
            else:
                q.put({"type": "done", "result": {
                    "ok": False,
                    "error": (result.stderr or result.stdout or "Unknown error")[-500:],
                }})

        except subprocess.TimeoutExpired:
            q.put({"type": "done", "result": {"ok": False, "error": "Scan timed out after 15 minutes."}})
        except Exception as e:
            q.put({"type": "done", "result": {"ok": False, "error": str(e)}})

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def stream():
        while True:
            try:
                event = q.get(timeout=600)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Scan timed out.'})}\n\n"
                break

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/sourcing/history", methods=["GET"])
def sourcing_history():
    """Query historical sourcing results from SQLite DB."""
    days = int(request.args.get("days", 7))
    verdict = request.args.get("verdict") or None
    min_roi = request.args.get("min_roi")
    mode = request.args.get("mode") or None
    limit = int(request.args.get("limit", 100))

    try:
        from results_db import ResultsDB
        db = ResultsDB()
        results = db.query_results(
            days=days, verdict=verdict,
            min_roi=float(min_roi) if min_roi else None,
            mode=mode, limit=limit,
        )
        stats = db.stats()
        return jsonify({"ok": True, "results": results, "stats": stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Unified Results API (Step 12: alias for /sourcing/history) ───────────────

@app.route("/sourcing/api/results", methods=["GET"])
def sourcing_api_results():
    """Unified results endpoint — queries ALL sourcing modes including storefront.

    Params: mode, verdict, min_roi, days (default 7), limit (default 100)
    """
    return sourcing_history()


# ─── JSON API (service-to-service, used by SaaS scraper-service) ─────────────

@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check for service-to-service calls."""
    try:
        from retailer_registry import RETAILERS
        retailer_count = len(RETAILERS)
    except Exception:
        retailer_count = 0
    return jsonify({
        "status": "ok",
        "retailers": retailer_count,
        "modes": ["url", "brand", "category", "oos", "deals", "a2a", "finder"],
    })


@app.route("/api/sourcing", methods=["POST"])
def api_sourcing():
    """JSON API for sourcing — runs source.py and returns structured results.

    Used by the SaaS scraper-service (nomad_bridge.py) to delegate sourcing.
    Unlike /sourcing/cli (SSE), this returns a single JSON response.
    """
    # C2 — API key auth
    data = request.get_json() or {}
    api_key = request.headers.get("X-API-Key") or data.get("api_key", "")
    expected_key = os.environ.get("SOURCING_API_KEY", "")
    if not expected_key:
        return jsonify({"error": "Server misconfiguration: SOURCING_API_KEY not set"}), 500
    if api_key != expected_key:
        return jsonify({"error": "Unauthorized", "message": "Valid X-API-Key header required"}), 401

    # C3 — Keepa token budget guard
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(app.root_path, "execution"))
        from keepa_client import KeepaClient
        _keepa = KeepaClient(os.environ.get("KEEPA_API_KEY", ""))
        token_status = _keepa.get_token_status()
        tokens_left = token_status.get("tokensLeft", token_status.get("tokens_left", 9999))
        if isinstance(tokens_left, (int, float)) and tokens_left < 50:
            return jsonify({
                "error": "token_budget_low",
                "message": f"Keepa token budget low ({int(tokens_left)} remaining). Try again in a few minutes.",
                "tokens_left": int(tokens_left),
            }), 429
    except Exception as e:
        app.logger.warning(f"Keepa token check failed: {e}")
        return jsonify({
            "error": "token_check_failed",
            "message": "Unable to verify Keepa token budget. Try again shortly.",
        }), 503

    mode = data.get("mode", "").strip()
    if not mode:
        return jsonify({"ok": False, "error": "mode is required"}), 400
    VALID_MODES = {"url", "brand", "category", "oos", "deals", "a2a", "finder", "catalog", "scan"}
    if mode not in VALID_MODES:
        return jsonify({"ok": False, "error": f"Invalid mode. Must be one of: {', '.join(sorted(VALID_MODES))}"}), 400

    # SSRF protection — validate URLs for URL-based modes
    def _validate_external_url(url_str):
        from urllib.parse import urlparse
        parsed = urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname or ""
        blocked = ("localhost", "127.0.0.1", "0.0.0.0", "[::]", "metadata.google.internal")
        if hostname in blocked:
            return False
        if hostname.startswith("169.254.") or hostname.startswith("10."):
            return False
        if hostname.startswith("192.168."):
            return False
        if hostname.startswith("172."):
            parts = hostname.split(".")
            if len(parts) >= 2:
                try:
                    second = int(parts[1])
                    if 16 <= second <= 31:
                        return False
                except ValueError:
                    pass
        return True

    target_url = data.get("url") or data.get("retailer_url", "")
    if mode in ("url", "catalog") and target_url:
        if not _validate_external_url(target_url):
            return jsonify({"ok": False, "error": "URL must be a public HTTP(S) URL"}), 400

    # Build CLI args (same logic as /sourcing/cli)
    cli_args = [mode]

    # Positional args
    if mode == "brand" and data.get("brand_name"):
        cli_args.append(data["brand_name"])
    if mode == "category" and data.get("category"):
        cli_args.append(data["category"])
    if mode == "url" and data.get("url"):
        cli_args.extend(["--url", data["url"]])
    if mode == "catalog" and data.get("retailer_url"):
        cli_args.append(data["retailer_url"])

    # Named args
    arg_map = {
        "retailers": "--retailers", "max": "--max", "count": "--count",
        "min_profit": "--min-profit", "min_drop": "--min-drop",
        "max_bsr": "--max-bsr", "min_reviews": "--min-reviews",
        "min_price": "--min-price", "max_price": "--max-price",
        "a2a_type": "--type", "min_discount": "--min-discount",
        "price_range": "--price-range", "category_id": "--category",
        "min_roi": "--min-roi", "max_products": "--max-products",
        "max_tokens": "--max-tokens", "coupon": "--coupon",
        "limit_scrape": "--limit-scrape",
    }
    for key, flag in arg_map.items():
        val = data.get(key)
        if val is not None and val != "":
            cli_args.extend([flag, str(val)])

    if data.get("deep_verify"):
        cli_args.append("--deep-verify")

    # C9 — Concurrency semaphore: cap parallel Playwright scans
    max_concurrent = int(os.environ.get("MAX_CONCURRENT_SCANS", "3"))
    if not _sourcing_semaphore.acquire(blocking=False):
        return jsonify({
            "error": "capacity_limit",
            "message": f"All {max_concurrent} scan slots are busy. Try again in a moment.",
        }), 429

    try:
        # C4 — Per-scan tmp directory prevents result file collision across concurrent calls
        scan_id = str(uuid.uuid4())[:8]
        scan_tmp = Path(__file__).parent / ".tmp" / "sourcing" / f"scan_{scan_id}"
        scan_tmp.mkdir(parents=True, exist_ok=True)

        script = Path(__file__).parent / "execution" / "source.py"
        python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
        cmd = [python, str(script)] + cli_args

        env = os.environ.copy()
        env["SCAN_TMP_DIR"] = str(scan_tmp)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)

        # Look for results in the scan-scoped directory first, then fall back to shared dir
        json_files = sorted(scan_tmp.glob("*_source_results.json"), reverse=True)
        if not json_files:
            shared_tmp = Path(__file__).parent / ".tmp" / "sourcing"
            json_files = sorted(shared_tmp.glob("*_source_results.json"), reverse=True)

        if json_files:
            with open(json_files[0]) as f:
                results = json.load(f)

            raw_products = results if isinstance(results, list) else results.get("products", results.get("results", []))

            # Run product review agent on all results before returning to student
            try:
                import sys as _sys
                _sys.path.insert(0, os.path.join(app.root_path, "execution"))
                from product_review_agent import batch_review_products

                if raw_products:
                    review_output = batch_review_products(raw_products, use_ai=True)

                    # Only return verified + flagged to students (not rejected)
                    clean_products = review_output["verified"] + review_output["flagged"]

                    review_stats = review_output["stats"]
                    if review_stats.get("rejected_count", 0) > 0:
                        app.logger.info(
                            f"Product review: {review_stats['rejected_count']} rejected, "
                            f"{review_stats['verified_count']} verified, "
                            f"{review_stats['flagged_count']} flagged"
                        )

                    return jsonify({
                        "ok": True,
                        "products": clean_products,
                        "review_stats": review_stats,
                        "rejected_count": review_stats["rejected_count"],
                        "mode": mode,
                        "scan_id": scan_id,
                    })
            except Exception as _e:
                app.logger.warning(f"Product review agent failed (non-fatal): {_e}")
                # Do NOT block results if review agent crashes — pass through unreviewed

            return jsonify({
                "ok": True,
                "products": raw_products,
                "mode": mode,
                "scan_id": scan_id,
            })
        elif result.returncode == 0:
            return jsonify({"ok": True, "products": [], "mode": mode, "scan_id": scan_id})
        else:
            return jsonify({
                "ok": False,
                "error": (result.stderr or result.stdout or "Unknown error")[-500:],
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Scan timed out after 15 minutes."}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        _sourcing_semaphore.release()


@app.route("/sourcing/export", methods=["POST"])
def export_sourcing_csv():
    """Export sourcing results as CSV download."""
    data = request.get_json()
    products = data.get("products", [])

    if not products:
        return jsonify({"error": "No products to export."}), 400

    fieldnames = ["verdict", "name", "retailer", "buy_cost", "amazon_price", "asin",
                  "profit_per_unit", "roi_percent", "estimated_monthly_sales",
                  "estimated_monthly_profit", "match_confidence", "retail_url", "amazon_url"]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for p in products:
        prof = p.get("profitability", {})
        amz = p.get("amazon", {})
        writer.writerow({
            "verdict": prof.get("verdict", ""),
            "name": p.get("name", ""),
            "retailer": p.get("retailer", ""),
            "buy_cost": prof.get("buy_cost", ""),
            "amazon_price": prof.get("sell_price", ""),
            "asin": amz.get("asin", ""),
            "profit_per_unit": prof.get("profit_per_unit", ""),
            "roi_percent": prof.get("roi_percent", ""),
            "estimated_monthly_sales": prof.get("estimated_monthly_sales", ""),
            "estimated_monthly_profit": prof.get("estimated_monthly_profit", ""),
            "match_confidence": amz.get("match_confidence", ""),
            "retail_url": p.get("retail_url", ""),
            "amazon_url": f"https://www.amazon.com/dp/{amz['asin']}" if amz.get("asin") else "",
        })

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sourcing_results.csv"},
    )


# ─── Training Officer Dashboard ──────────────────────────────────────────────

TRAINING_TMP = Path(__file__).parent / ".tmp" / "training-officer"
TRAINING_PROPOSALS = TRAINING_TMP / "proposals"


def _parse_proposal_file(filepath):
    """Parse a proposal YAML into a dict."""
    content = filepath.read_text()
    info = {"file": filepath.name, "id": filepath.stem}
    in_proposed = False
    proposed_lines = []
    for line in content.splitlines():
        if line.startswith("proposed_content:"):
            in_proposed = True
            continue
        elif in_proposed:
            if line.startswith("# RISK") or line.startswith("risk_level:"):
                in_proposed = False
            elif line.startswith("  "):
                proposed_lines.append(line[2:])
            continue
        for key in ("target_agent", "target_file", "upgrade_type", "title", "status", "theme"):
            if line.startswith(f"{key}:"):
                val = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
                info[key.replace("target_", "")] = val
    info["proposed_content"] = "\n".join(proposed_lines).strip()
    return info


@app.route("/group-call")
def group_call():
    return render_template("ai-amazon-group-call-april.html")


# ── Webinar Funnel Routes ──────────────────────────────────────────────────────

@app.route("/webinar")
def webinar_redirect():
    return redirect("/webinar/register")


@app.route("/webinar/register")
def webinar_register():
    return render_template("webinar-registration.html")


@app.route("/webinar/thankyou")
def webinar_thankyou():
    return render_template("webinar-thankyou.html")


@app.route("/webinar/replay")
def webinar_replay():
    return render_template("webinar-replay.html")


@app.route("/webinar/apply")
def webinar_apply():
    return render_template("webinar-application.html")


@app.route("/webinar/expired")
def webinar_expired():
    return render_template("webinar-expired.html")


@app.route("/webinar/exit")
def webinar_exit():
    return render_template("webinar-exit.html")



@app.route("/webinar/slides")
def webinar_slides():
    return render_template("webinar-slides.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/dashboard/api/health")
def dashboard_health():
    health_file = TRAINING_TMP / "agent-health.json"
    if health_file.exists():
        return jsonify(json.loads(health_file.read_text()))
    return jsonify({})


@app.route("/dashboard/api/proposals")
def dashboard_proposals():
    if not TRAINING_PROPOSALS.exists():
        return jsonify([])
    proposals = []
    for f in sorted(TRAINING_PROPOSALS.glob("TP-*.yaml")):
        proposals.append(_parse_proposal_file(f))
    return jsonify(proposals)


@app.route("/dashboard/api/themes")
def dashboard_themes():
    if not TRAINING_PROPOSALS.exists():
        return jsonify({})
    themes = {}
    for f in sorted(TRAINING_PROPOSALS.glob("TP-*.yaml")):
        p = _parse_proposal_file(f)
        if p.get("status") == "pending":
            theme = p.get("theme", "general")
            if theme not in themes:
                themes[theme] = []
            themes[theme].append(p)
    return jsonify(themes)


@app.route("/dashboard/api/quality")
def dashboard_quality():
    qf = TRAINING_TMP / "quality-scores.json"
    if qf.exists():
        return jsonify(json.loads(qf.read_text()))
    return jsonify([])


@app.route("/dashboard/api/learnings")
def dashboard_learnings():
    lf = TRAINING_TMP / "learnings.md"
    if not lf.exists():
        return jsonify([])
    learnings = []
    for line in lf.read_text().splitlines():
        if line.startswith("|") and "Date" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                learnings.append({"date": parts[0], "proposal": parts[1], "reason": parts[2]})
    return jsonify(learnings)


@app.route("/dashboard/api/ownership")
def dashboard_ownership():
    # Import from scan script
    try:
        from training_officer_scan import SKILL_OWNERSHIP
        return jsonify(SKILL_OWNERSHIP)
    except ImportError:
        return jsonify({})


@app.route("/dashboard/api/last-scan")
def dashboard_last_scan():
    lsf = TRAINING_TMP / "last-scan.json"
    if lsf.exists():
        return jsonify(json.loads(lsf.read_text()))
    return jsonify({})


@app.route("/dashboard/api/scan", methods=["POST"])
def dashboard_run_scan():
    try:
        script = Path(__file__).parent / "execution" / "training_officer_scan.py"
        python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
        result = subprocess.run([python, str(script)], capture_output=True, text=True, timeout=300)
        return jsonify({"ok": result.returncode == 0, "message": "Scan complete" if result.returncode == 0 else result.stderr[-200:]})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/dashboard/api/approve/<proposal_id>", methods=["POST"])
def dashboard_approve(proposal_id):
    pf = TRAINING_PROPOSALS / f"{proposal_id}.yaml"
    if not pf.exists():
        return jsonify({"ok": False, "message": "Not found"}), 404
    try:
        script = Path(__file__).parent / "execution" / "apply_proposal.py"
        python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
        result = subprocess.run([python, str(script), "--approve", proposal_id],
                                capture_output=True, text=True, timeout=30)
        return jsonify({"ok": result.returncode == 0, "message": result.stdout[-200:] or "Applied"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/dashboard/api/reject/<proposal_id>", methods=["POST"])
def dashboard_reject(proposal_id):
    data = request.get_json() or {}
    reason = data.get("reason", "Rejected via dashboard")
    pf = TRAINING_PROPOSALS / f"{proposal_id}.yaml"
    if not pf.exists():
        return jsonify({"ok": False, "message": "Not found"}), 404
    try:
        script = Path(__file__).parent / "execution" / "apply_proposal.py"
        python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
        result = subprocess.run([python, str(script), "--reject", proposal_id, "--reason", reason],
                                capture_output=True, text=True, timeout=30)
        return jsonify({"ok": result.returncode == 0, "message": f"Rejected: {reason}"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/dashboard/api/approve-all", methods=["POST"])
def dashboard_approve_all():
    try:
        script = Path(__file__).parent / "execution" / "apply_proposal.py"
        python = str(Path(__file__).parent / ".venv" / "bin" / "python3")
        result = subprocess.run([python, str(script), "--approve-all"],
                                capture_output=True, text=True, timeout=120)
        return jsonify({"ok": result.returncode == 0, "message": result.stdout[-300:] or "All approved"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


# ─── CEO Command Center ─────────────────────────────────────────────────────

import re as _re

BRAIN_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
CHANGELOG_PATH = Path(__file__).parent / "SabboOS" / "CHANGELOG.md"
INBOX_PATH = Path("/Users/Shared/antigravity/inbox")
CEO_TMP = Path(__file__).parent / ".tmp" / "ceo"


def _parse_brain_section(section_name):
    """Extract a section from brain.md by header name."""
    if not BRAIN_PATH.exists():
        return ""
    content = BRAIN_PATH.read_text()
    pattern = rf"## {_re.escape(section_name)}\n(.*?)(?=\n## |\Z)"
    match = _re.search(pattern, content, _re.DOTALL)
    return match.group(1).strip() if match else ""


def _parse_brain_table(section_name, max_rows=20):
    """Extract table rows from a brain.md section."""
    text = _parse_brain_section(section_name)
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and "---" not in line and "Date" not in line.split("|")[1]:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts:
                rows.append(parts)
    return rows[-max_rows:]


@app.route("/ceo")
def ceo_dashboard():
    return render_template("ceo.html")


@app.route("/ceo/api/brain-health")
def ceo_brain_health():
    if not BRAIN_PATH.exists():
        return jsonify({"exists": False, "lines": 0})
    content = BRAIN_PATH.read_text()
    lines = content.count("\n")
    # Extract meta
    meta = _parse_brain_section("Meta")
    sections = len(_re.findall(r"^## ", content, _re.MULTILINE))
    # Check index
    index_path = TRAINING_TMP / "brain-index.json"
    index_data = {}
    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text())
        except Exception:
            pass
    return jsonify({
        "exists": True,
        "lines": lines,
        "sections": sections,
        "last_modified": datetime.fromtimestamp(BRAIN_PATH.stat().st_mtime).isoformat(),
        "index": index_data,
    })


@app.route("/ceo/api/pipeline")
def ceo_pipeline():
    try:
        from pipeline_analytics import export_to_json
        return jsonify(export_to_json(period="weekly"))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/constraint")
def ceo_constraint():
    """Get current constraint from pipeline bottleneck or today's brief."""
    try:
        from pipeline_analytics import find_bottleneck
        for biz in ["agency", "coaching"]:
            bn = find_bottleneck(period="weekly", business=biz)
            if bn and bn.get("step"):
                bn["business"] = biz
                return jsonify(bn)
        return jsonify({"bottleneck": None, "message": "No constraint detected"})
    except Exception:
        # Fall back to today's brief
        today = datetime.now().strftime("%Y-%m-%d")
        brief_path = CEO_TMP / f"brief_{today}.md"
        if brief_path.exists():
            content = brief_path.read_text()
            match = _re.search(r"CONSTRAINT.*?:\s*(.+)", content, _re.IGNORECASE)
            if match:
                return jsonify({"constraint": match.group(1).strip(), "source": "brief"})
        return jsonify({"bottleneck": None, "message": "No data"})


@app.route("/ceo/api/delegations")
def ceo_delegations():
    rows = _parse_brain_table("Delegation History")
    delegations = []
    for r in rows:
        delegations.append({
            "date": r[0] if len(r) > 0 else "",
            "agent": r[1] if len(r) > 1 else "",
            "task": r[2] if len(r) > 2 else "",
            "status": r[3] if len(r) > 3 else "",
            "outcome": r[4] if len(r) > 4 else "",
        })
    return jsonify(delegations)


@app.route("/ceo/api/client-health")
def ceo_client_health():
    try:
        from client_health_monitor import export_json
        return jsonify(export_json())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/student-health")
def ceo_student_health():
    try:
        from student_tracker import export_json
        return jsonify(export_json())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/outreach-stats")
def ceo_outreach_stats():
    try:
        from outreach_sequencer import export_json
        return jsonify(export_json())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/agent-status")
def ceo_agent_status():
    health_file = TRAINING_TMP / "agent-health.json"
    if health_file.exists():
        return jsonify(json.loads(health_file.read_text()))
    return jsonify({})


@app.route("/ceo/api/pending-proposals")
def ceo_pending_proposals():
    if not TRAINING_PROPOSALS.exists():
        return jsonify([])
    proposals = []
    for f in sorted(TRAINING_PROPOSALS.glob("TP-*.yaml")):
        p = _parse_proposal_file(f)
        if p.get("status") == "pending":
            proposals.append(p)
    return jsonify(proposals)


@app.route("/ceo/api/changelog")
def ceo_changelog():
    if not CHANGELOG_PATH.exists():
        return jsonify([])
    entries = []
    for line in CHANGELOG_PATH.read_text().splitlines():
        if line.startswith("|") and "Date" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                entries.append({"date": parts[0], "file": parts[1], "change": parts[2]})
    return jsonify(entries[-15:])


@app.route("/ceo/api/dispatch", methods=["POST"])
def ceo_dispatch():
    """Write a task dispatch to the inbox for async processing."""
    data = request.get_json()
    if not data or not data.get("agent"):
        return jsonify({"ok": False, "message": "Agent is required"}), 400

    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    task = {
        "task_type": "agent_dispatch",
        "agent": data["agent"],
        "constraint": data.get("constraint", ""),
        "kpis": data.get("kpis", {}),
        "brain_context": data.get("context", ""),
        "requested_output": data.get("output", ""),
        "priority": data.get("priority", "high"),
        "created_at": datetime.utcnow().isoformat(),
    }
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    task_path = INBOX_PATH / f"dispatch_{data['agent']}_{ts}.json"
    task_path.write_text(json.dumps(task, indent=2))
    return jsonify({"ok": True, "message": f"Dispatched to {data['agent']}", "file": str(task_path)})


# ─── Project Manager Dashboard ───────────────────────────────────────────────

PM_TMP = Path(__file__).parent / ".tmp" / "projects"


@app.route("/projects")
def projects_dashboard():
    return render_template("projects.html")


@app.route("/projects/api/summary")
def projects_summary():
    try:
        from project_manager import dashboard_data
        data = dashboard_data()
        return jsonify(data.get("summary", {}))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/list")
def projects_list():
    try:
        from project_manager import list_projects, refresh_all_scores
        status = request.args.get("status")
        business = request.args.get("business")
        refresh_all_scores()
        return jsonify(list_projects(status, business))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/detail/<slug>")
def projects_detail(slug):
    try:
        from project_manager import project_detail, get_db
        conn = get_db()
        try:
            project = conn.execute("SELECT name FROM projects WHERE slug = ?", (slug,)).fetchone()
        finally:
            conn.close()
        if not project:
            return jsonify({"error": "Project not found"}), 404
        return jsonify(project_detail(project["name"]))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/at-risk")
def projects_at_risk():
    try:
        from project_manager import get_at_risk
        return jsonify(get_at_risk())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/blockers")
def projects_blockers():
    try:
        from project_manager import list_blockers
        return jsonify(list_blockers(status="open"))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/workload")
def projects_workload():
    try:
        from project_manager import workload
        return jsonify(workload())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/activity")
def projects_activity():
    try:
        from project_manager import get_db
        limit = request.args.get("limit", 15, type=int)
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT a.*, p.name as project_name FROM activity_log a "
                "JOIN projects p ON a.project_id = p.id "
                "ORDER BY a.date DESC, a.id DESC LIMIT ?", (limit,)
            ).fetchall()
            return jsonify([dict(r) for r in rows])
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/congruence")
def projects_congruence():
    try:
        from project_manager import congruence_check
        return jsonify(congruence_check())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/timeline")
def projects_timeline():
    try:
        from project_manager import get_db
        conn = get_db()
        try:
            rows = conn.execute("""
                SELECT m.name as milestone_name, m.status, m.start_date, m.due_date,
                       m.completed_date, p.name as project_name, p.slug as project_slug
                FROM milestones m JOIN projects p ON m.project_id = p.id
                WHERE p.status NOT IN ('completed', 'archived')
                ORDER BY p.name, m.sort_order, m.id
            """).fetchall()
            return jsonify([dict(r) for r in rows])
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/projects/api/refresh", methods=["POST"])
def projects_refresh():
    try:
        from project_manager import refresh_all_scores
        results = refresh_all_scores()
        return jsonify({"ok": True, "refreshed": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/ceo/api/project-status")
def ceo_project_status():
    try:
        from project_manager import briefing_feed
        return jsonify(briefing_feed())
    except Exception as e:
        return jsonify({"error": str(e)})


# ── CSM Student API ──────────────────────────────────────────────────────────

@app.route("/ceo/api/students")
def ceo_students_full():
    """Full student cohort with health scores, milestones, engagement data."""
    try:
        from student_health_monitor import get_db, calculate_health_score
        import json as _json
        conn = get_db()
        students = conn.execute("""
            SELECT s.*,
                   (SELECT score FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as latest_health,
                   (SELECT risk_level FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as latest_risk,
                   (SELECT COUNT(*) FROM engagement_signals WHERE student_id = s.id AND date >= date('now', '-14 days')) as recent_signals,
                   (SELECT mood FROM check_ins WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as latest_mood
            FROM students s WHERE s.status != 'churned'
            ORDER BY s.health_score ASC
        """).fetchall()

        result = []
        for s in students:
            milestones = conn.execute(
                "SELECT milestone, status, completed_date FROM milestones WHERE student_id = ? ORDER BY id",
                (s["id"],)
            ).fetchall()
            result.append({
                "name": s["name"], "email": s["email"], "tier": s["tier"],
                "status": s["status"], "current_milestone": s["current_milestone"],
                "health_score": s["latest_health"] or s["health_score"],
                "risk_level": s["latest_risk"] or "unknown",
                "start_date": s["start_date"], "target_date": s["target_date"],
                "discord_user_id": s["discord_user_id"],
                "recent_signals": s["recent_signals"], "latest_mood": s["latest_mood"],
                "milestones": {m["milestone"]: m["status"] for m in milestones},
            })
        conn.close()

        # Summary stats
        total = len(result)
        risk_dist = {}
        for r in result:
            rl = r["risk_level"]
            risk_dist[rl] = risk_dist.get(rl, 0) + 1
        milestone_dist = {}
        for r in result:
            ms = r["current_milestone"]
            milestone_dist[ms] = milestone_dist.get(ms, 0) + 1

        return jsonify({
            "students": result,
            "total": total,
            "risk_distribution": risk_dist,
            "milestone_distribution": milestone_dist,
            "generated_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/students/at-risk")
def ceo_students_at_risk():
    """At-risk students sorted by severity."""
    try:
        from student_health_monitor import get_db
        conn = get_db()
        students = conn.execute("""
            SELECT s.name, s.email, s.current_milestone, s.status, s.discord_user_id,
                   (SELECT score FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as health,
                   (SELECT risk_level FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as risk
            FROM students s
            WHERE s.status IN ('active', 'at_risk')
            AND (SELECT risk_level FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1)
                IN ('orange', 'red', 'critical')
            ORDER BY (SELECT score FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) ASC
        """).fetchall()
        conn.close()
        return jsonify({"at_risk": [dict(s) for s in students], "count": len(students)})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/students/backend")
def ceo_students_backend():
    """Backend revenue: subscriptions, MRR, conversions."""
    try:
        from student_health_monitor import get_db
        conn = get_db()
        subs = conn.execute("""
            SELECT bs.*, s.name FROM backend_subscriptions bs
            JOIN students s ON s.id = bs.student_id
            ORDER BY bs.start_date DESC
        """).fetchall()
        active_subs = [dict(s) for s in subs if s["status"] == "active"]
        mrr = sum(s["monthly_revenue"] for s in active_subs)

        grad_flows = conn.execute("""
            SELECT gf.*, s.name FROM graduation_flows gf
            JOIN students s ON s.id = gf.student_id
            ORDER BY gf.started_at DESC
        """).fetchall()
        conn.close()

        return jsonify({
            "subscriptions": [dict(s) for s in subs],
            "active_count": len(active_subs),
            "mrr": mrr,
            "graduation_flows": [dict(g) for g in grad_flows],
            "total_flows": len(grad_flows),
            "converted": len([g for g in grad_flows if g["status"] == "converted"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/students/testimonials")
def ceo_students_testimonials():
    """Testimonial pipeline status."""
    try:
        from student_health_monitor import get_db
        conn = get_db()
        testimonials = conn.execute("""
            SELECT t.*, s.name FROM testimonials t
            JOIN students s ON s.id = t.student_id
            ORDER BY t.requested_at DESC
        """).fetchall()
        conn.close()

        by_status = {}
        for t in testimonials:
            st = t["status"]
            by_status[st] = by_status.get(st, 0) + 1

        return jsonify({
            "testimonials": [dict(t) for t in testimonials],
            "total": len(testimonials),
            "by_status": by_status,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ceo/api/students/leaderboard")
def ceo_students_leaderboard():
    """Top students by health score and milestone progress."""
    try:
        from student_health_monitor import get_db
        conn = get_db()
        students = conn.execute("""
            SELECT s.name, s.current_milestone, s.tier,
                   (SELECT score FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as health,
                   (SELECT COUNT(*) FROM engagement_signals WHERE student_id = s.id AND date >= date('now', '-14 days')) as engagement
            FROM students s
            WHERE s.status IN ('active', 'at_risk')
            ORDER BY health DESC, engagement DESC
            LIMIT 20
        """).fetchall()
        conn.close()
        return jsonify({"leaderboard": [dict(s) for s in students]})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── Whop Payment Webhook ───────────────────────────────────────────────────

@app.route("/webhooks/manychat", methods=["POST"])
def manychat_webhook():
    """Handle ManyChat keyword trigger webhooks for AI setter."""
    try:
        from execution.setter.manychat_bridge import handle_manychat_webhook
        payload = request.get_json(force=True, silent=True) or {}
        result = handle_manychat_webhook(payload)
        return jsonify(result), 200 if result["status"] != "error" else 400
    except ImportError:
        return jsonify({"error": "setter module not available"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/webhooks/whop", methods=["POST"])
def whop_webhook():
    """Handle Whop payment events: new members, payments, cancellations."""
    try:
        payload = request.get_json(force=True)
        event = payload.get("action", payload.get("event", ""))
        data = payload.get("data", payload)

        from student_health_monitor import get_db

        # Route by event type
        if event in ("membership.went_valid", "payment.succeeded"):
            # New student or renewal
            member = data.get("member", data)
            email = member.get("email", "")
            name = member.get("name", member.get("username", email.split("@")[0] if email else "Unknown"))
            discord_id = member.get("discord_id", member.get("discord_account_id", ""))

            conn = get_db()
            existing = conn.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone() if email else None

            if not existing and name:
                # New student — register
                conn.execute("""
                    INSERT OR IGNORE INTO students (name, email, discord_user_id, tier, status, start_date, current_milestone)
                    VALUES (?, ?, ?, 'A', 'active', date('now'), 'enrolled')
                """, (name, email, str(discord_id) if discord_id else None))
                conn.execute("""
                    INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
                    VALUES (last_insert_rowid(), 'payment_succeeded', 'whop', 'true', date('now'), ?, datetime('now'))
                """, (json.dumps({"event": event, "email": email}),))
                conn.commit()

                # Auto-onboard via Discord if we have their ID
                if discord_id:
                    try:
                        import subprocess
                        subprocess.Popen([
                            sys.executable, "execution/student_onboarding.py",
                            "onboard", "--name", name, "--discord-id", str(discord_id), "--tier", "A"
                        ], cwd=str(Path(__file__).parent))
                    except Exception:
                        pass
            elif existing:
                conn.execute("""
                    INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
                    VALUES (?, 'payment_succeeded', 'whop', 'true', date('now'), ?, datetime('now'))
                """, (existing["id"], json.dumps({"event": event})))
                conn.commit()
            conn.close()

        elif event == "payment.failed":
            member = data.get("member", data)
            email = member.get("email", "")
            conn = get_db()
            student = conn.execute("SELECT id, name FROM students WHERE email = ?", (email,)).fetchone() if email else None
            if student:
                # Log failed payment + queue intervention
                conn.execute("""
                    INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
                    VALUES (?, 'payment_failed', 'whop', 'true', date('now'), ?, datetime('now'))
                """, (student["id"], json.dumps({"event": event})))
                # Queue a gentle DM
                conn.execute("""
                    INSERT INTO touchpoints (student_id, type, channel, message, status)
                    VALUES (?, 'payment_recovery', 'discord_dm', ?, 'queued')
                """, (student["id"],
                      f"Hey {student['name'].split()[0]}, heads up — your payment didn't go through. "
                      "No worries, these things happen! Just update your payment method and you're good. "
                      "If you need to pause or have questions, just let me know. 🙏"))
                conn.commit()
            conn.close()

        elif event in ("subscription.cancelled", "membership.went_invalid"):
            member = data.get("member", data)
            email = member.get("email", "")
            conn = get_db()
            student = conn.execute("SELECT id, name FROM students WHERE email = ?", (email,)).fetchone() if email else None
            if student:
                conn.execute("UPDATE students SET status = 'churned' WHERE id = ?", (student["id"],))
                conn.execute("""
                    INSERT INTO churn_events (student_id, detected_at, reason)
                    VALUES (?, datetime('now'), 'cancelled')
                """, (student["id"],))
                conn.execute("""
                    INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
                    VALUES (?, 'subscription_cancelled', 'whop', 'true', date('now'), ?, datetime('now'))
                """, (student["id"], json.dumps({"event": event})))
                conn.commit()

                # Trigger exit interview
                try:
                    import subprocess
                    subprocess.Popen([
                        sys.executable, "execution/exit_interview.py",
                        "start", "--student", student["name"]
                    ], cwd=str(Path(__file__).parent))
                except Exception:
                    pass
            conn.close()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def cleanup_old_results():
    """C5 — Delete sourcing result files older than 24 hours."""
    patterns = [
        ".tmp/sourcing/*.json",
        ".tmp/*.json",
    ]
    cutoff = time.time() - 86400  # 24 hours
    deleted = 0
    for pattern in patterns:
        for f in glob.glob(pattern):
            if os.path.getmtime(f) < cutoff:
                try:
                    os.remove(f)
                    deleted += 1
                except OSError:
                    pass
    if deleted:
        print(f"[Startup] Cleaned up {deleted} old result files")


# ── New sourcing routes ───────────────────────────────────────────────────────

@app.route("/sourcing/wholesale", methods=["GET", "POST"])
def sourcing_wholesale():
    """C6 — Wholesale manifest upload and analysis."""
    if request.method == "GET":
        return render_template("sourcing.html", active_tab="wholesale")

    # POST — handle file upload
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    allowed = {".csv", ".xlsx", ".xls"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"error": f"Unsupported file type {ext}. Use CSV or Excel."}), 400

    # Save to tmp
    tmp_dir = ".tmp/wholesale"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"manifest_{int(time.time())}{ext}")
    file.save(tmp_path)

    min_roi = float(request.form.get("min_roi", 30))
    min_profit = float(request.form.get("min_profit", 3.00))

    try:
        sys.path.insert(0, "execution")
        from wholesale_manifest import process_manifest
        results = process_manifest(tmp_path, min_roi=min_roi, min_profit=min_profit)
        return jsonify({
            "success": True,
            "count": len(results),
            "results": results[:100],  # Cap at 100 for response size
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@app.route("/sourcing/watch", methods=["POST"])
def add_price_watch():
    """C7 — Add a price alert watch for an ASIN."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    asin = data.get("asin", "").strip().upper()
    if not asin or len(asin) != 10:
        return jsonify({"error": "Valid 10-character ASIN required"}), 400

    max_cost = float(data.get("max_cost", 0))
    if max_cost <= 0:
        return jsonify({"error": "max_cost must be > 0"}), 400

    student_id = data.get("student_id", "anonymous")
    discord_webhook = data.get("discord_webhook", os.environ.get("DISCORD_WEBHOOK_URL", ""))

    try:
        from results_db import ResultsDB
        db = ResultsDB()
        watch_id = db.add_price_watch(student_id, asin, max_cost, discord_webhook)
        return jsonify({
            "success": True,
            "watch_id": watch_id,
            "message": f"Watching ASIN {asin} — will alert when any retailer drops to ${max_cost:.2f}",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sourcing/watches", methods=["GET"])
def list_price_watches():
    """C7 — List all active price watches."""
    try:
        from results_db import ResultsDB
        db = ResultsDB()
        watches = db.get_active_watches() if hasattr(db, "get_active_watches") else []
        return jsonify({"watches": watches, "count": len(watches)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sourcing/brand-intel", methods=["GET"])
def brand_intel():
    """C8 — Brand intelligence lookup."""
    brand = request.args.get("brand", "").strip()
    if not brand:
        return jsonify({"error": "brand parameter required"}), 400

    try:
        from brand_intel import analyze_brand
        result = analyze_brand(brand)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Receive student outcome feedback for self-improvement."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    asin = data.get("asin", "").strip()
    if not asin:
        return jsonify({"error": "asin required"}), 400

    feedback_type = data.get("feedback_type", "")
    valid_types = {"confirmed_profit", "false_match", "wrong_profit", "couldnt_sell", "confirmed_buy"}
    if feedback_type not in valid_types:
        return jsonify({"error": f"feedback_type must be one of: {valid_types}"}), 400

    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(app.root_path, "execution"))
        from product_review_agent import record_student_outcome
        record_student_outcome(
            asin=asin,
            retailer=data.get("retailer", ""),
            predicted_roi=float(data.get("predicted_roi", 0)),
            actual_roi=float(data.get("actual_roi", 0)),
            feedback_type=feedback_type,
            notes=data.get("notes", ""),
        )

        # If it's a false match, also trigger immediate feedback analysis
        if feedback_type == "false_match":
            try:
                from feedback_engine import generate_improvement_proposals
                proposals = generate_improvement_proposals()
                app.logger.info(
                    f"False match reported for {asin} — generated {len(proposals)} improvement proposals"
                )
            except Exception:
                pass

        return jsonify({"success": True, "message": "Feedback recorded — thank you for helping improve the system"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health/sourcing", methods=["GET"])
def api_sourcing_health():
    """Diagnostic endpoint — sourcing system health + feedback stats."""
    import sys as _sys
    _sys.path.insert(0, os.path.join(app.root_path, "execution"))

    import datetime as _dt
    report = {"timestamp": _dt.datetime.utcnow().isoformat()}

    try:
        from feedback_engine import analyze_rejection_patterns, analyze_retailer_health, analyze_student_outcomes
        report["rejection_analysis"] = analyze_rejection_patterns(days=7)
        report["retailer_health"] = analyze_retailer_health(days=7)
        report["student_outcomes"] = analyze_student_outcomes(days=30)
    except Exception as e:
        report["feedback_error"] = str(e)

    try:
        from keepa_client import KeepaClient
        keepa = KeepaClient(os.environ.get("KEEPA_API_KEY", ""))
        token_status = keepa.get_token_status()
        report["keepa_tokens"] = token_status
    except Exception as e:
        report["keepa_error"] = str(e)

    try:
        from results_db import ResultsDB
        db = ResultsDB()
        report["db_stats"] = db.stats() if hasattr(db, "stats") else "available"
    except Exception as e:
        report["db_error"] = str(e)

    return jsonify(report)


# ── Supplier Finder API ──────────────────────────────────────────────────────

@app.route("/api/supplier-search", methods=["POST"])
def api_supplier_search():
    """Search for wholesale suppliers by category + optional location."""
    api_key = request.headers.get("X-API-Key", "")
    expected = os.environ.get("SOURCING_API_KEY", "")
    if expected and api_key != expected:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    category = (data.get("category") or "").strip()
    if not category:
        return jsonify({"error": "category is required"}), 400

    keywords = data.get("keywords")
    location = data.get("location")
    state = data.get("state")
    max_results = data.get("max_results", 20)
    include_nationwide = data.get("include_nationwide", True)

    sys.path.insert(0, os.path.join(app.root_path, "execution"))
    from wholesale_supplier_finder import search_suppliers, supplier_to_json

    sources = ["google", "thomasnet"]
    if keywords:
        # Prepend keywords to category search
        category = f"{keywords} {category}"

    try:
        results = search_suppliers(
            category=category,
            sources=sources,
            location=location,
            state=state,
            include_nationwide=include_nationwide,
        )
        return jsonify({
            "ok": True,
            "count": len(results),
            "suppliers": [supplier_to_json(s) for s in results[:max_results]],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/supplier-outreach/generate", methods=["POST"])
def api_supplier_outreach_generate():
    """Generate personalized outreach emails for suppliers."""
    api_key = request.headers.get("X-API-Key", "")
    expected = os.environ.get("SOURCING_API_KEY", "")
    if expected and api_key != expected:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    suppliers = data.get("suppliers", [])
    supplier_ids = data.get("supplier_ids", [])
    template_type = data.get("template_type", "intro_inquiry")

    sys.path.insert(0, os.path.join(app.root_path, "execution"))

    if supplier_ids and not suppliers:
        from wholesale_supplier_finder import get_db, supplier_to_json
        conn = get_db()
        try:
            placeholders = ",".join("?" for _ in supplier_ids)
            rows = conn.execute(
                f"SELECT * FROM wholesale_suppliers WHERE id IN ({placeholders})",
                supplier_ids,
            ).fetchall()
            suppliers = [supplier_to_json(dict(r)) for r in rows]
        finally:
            conn.close()

    if not suppliers:
        return jsonify({"error": "No suppliers provided"}), 400

    from supplier_outreach_engine import generate_batch_emails

    try:
        drafts = generate_batch_emails(suppliers, template_type=template_type)
        return jsonify({
            "ok": True,
            "count": len(drafts),
            "drafts": drafts,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/supplier-outreach/send", methods=["POST"])
def api_supplier_outreach_send():
    """Send draft outreach emails via SMTP. Requires smtp_config."""
    api_key = request.headers.get("X-API-Key", "")
    expected = os.environ.get("SOURCING_API_KEY", "")
    if expected and api_key != expected:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    drafts = data.get("emails", [])
    smtp_config = data.get("smtp_config", {})
    dry_run = data.get("dry_run", False)

    if not drafts:
        return jsonify({"error": "No emails provided"}), 400
    if not smtp_config.get("smtp_host") or not smtp_config.get("smtp_user"):
        return jsonify({"error": "smtp_config with smtp_host and smtp_user required"}), 400

    sys.path.insert(0, os.path.join(app.root_path, "execution"))
    from supplier_outreach_engine import send_batch

    try:
        results = send_batch(drafts, smtp_config, dry_run=dry_run)
        sent = len([r for r in results if r["status"] == "sent"])
        failed = len([r for r in results if r["status"] == "failed"])
        return jsonify({
            "ok": True,
            "sent": sent,
            "failed": failed,
            "total": len(results),
            "results": results,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Storefront Stalker ───────────────────────────────────────────────────────

@app.route("/stalker")
def stalker_page():
    return render_template("stalker.html")


@app.route("/stalker/api/storefronts", methods=["GET"])
def stalker_list_storefronts():
    """List all tracked storefronts with accuracy scores and status."""
    from results_db import ResultsDB
    db = ResultsDB()
    storefronts = db.get_tracked_storefronts()
    return jsonify({"ok": True, "storefronts": storefronts})


@app.route("/stalker/api/storefronts", methods=["POST"])
def stalker_add_storefront():
    """Add a seller storefront to the watch list."""
    from results_db import ResultsDB
    data = request.get_json() or {}
    seller_id = (data.get("seller_id") or "").strip()
    seller_name = (data.get("seller_name") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not seller_id:
        return jsonify({"ok": False, "error": "seller_id is required"}), 400
    if not seller_name:
        seller_name = seller_id

    # Basic validation: seller IDs are 13-15 alphanumeric chars
    import re
    if not re.match(r'^[A-Z0-9]{10,16}$', seller_id):
        return jsonify({"ok": False, "error": "Invalid seller ID format. Expected 10-16 alphanumeric characters (e.g., A2VIDQ35RC54UG)"}), 400

    db = ResultsDB()
    row_id = db.add_tracked_storefront(seller_id, seller_name, notes)
    return jsonify({"ok": True, "id": row_id, "seller_id": seller_id})


@app.route("/stalker/api/storefronts/<seller_id>", methods=["DELETE"])
def stalker_remove_storefront(seller_id):
    """Remove a seller from the watch list."""
    from results_db import ResultsDB
    db = ResultsDB()
    db.remove_tracked_storefront(seller_id)
    return jsonify({"ok": True, "removed": seller_id})


@app.route("/stalker/api/alerts", methods=["GET"])
def stalker_alerts():
    """Get recent storefront alerts with optional filters."""
    from results_db import ResultsDB
    db = ResultsDB()
    limit = request.args.get("limit", 50, type=int)
    grade = request.args.get("grade")
    seller_id = request.args.get("seller_id")
    since_id = request.args.get("since_id", type=int)
    alerts = db.get_storefront_alerts(limit=limit, grade=grade, seller_id=seller_id, since_id=since_id)
    return jsonify({"ok": True, "alerts": alerts})


@app.route("/stalker/api/trigger", methods=["POST"])
def stalker_trigger():
    """Manually trigger a monitor cycle in a background thread."""
    def _run():
        try:
            from storefront_monitor import run_monitor_cycle
            run_monitor_cycle()
        except Exception as e:
            app.logger.error("Stalker trigger error: %s", e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Monitor cycle started in background"})


@app.route("/stalker/api/stats", methods=["GET"])
def stalker_stats():
    """Dashboard stats for the storefront stalker."""
    from results_db import ResultsDB
    db = ResultsDB()
    stats = db.get_stalker_stats()
    return jsonify({"ok": True, "stats": stats})


@app.route("/stalker/api/feedback", methods=["POST"])
def stalker_feedback():
    """Submit accuracy feedback for a storefront alert (bought / skipped)."""
    from results_db import ResultsDB
    data = request.get_json() or {}
    seller_id = data.get("seller_id")
    was_profitable = data.get("was_profitable", False)

    if not seller_id:
        return jsonify({"ok": False, "error": "seller_id is required"}), 400

    db = ResultsDB()
    db.update_storefront_accuracy(seller_id, was_profitable)
    return jsonify({"ok": True, "seller_id": seller_id, "was_profitable": was_profitable})


# ── Keepa Token Monitor ──────────────────────────────────────────────────────

@app.route("/api/keepa/tokens", methods=["GET"])
def keepa_tokens():
    """Check Keepa API token balance."""
    try:
        from keepa_client import KeepaClient
        kc = KeepaClient()
        info = kc.check_tokens()
        if info:
            return jsonify({"ok": True, **info})
        return jsonify({"ok": False, "error": "Could not reach Keepa API"}), 503
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Nova Unified Chatbot API ─────────────────────────────────────────────────
# Shared brain for Discord bot, 247profits.org, and 247growth.org.
# Auth: X-Nova-Secret header must match NOVA_API_SECRET in .env.

from dotenv import load_dotenv
load_dotenv()

NOVA_API_SECRET = os.environ.get("NOVA_API_SECRET", "")
_NOVA_DEV_MODE = os.environ.get("FLASK_ENV") == "development" or os.environ.get("NOVA_DEV_MODE") == "1"

# Rate limiter for /nova/* routes — 30 req/min per IP
from collections import defaultdict as _ddict
import time as _nova_time
_nova_rate_windows: dict[str, list[float]] = _ddict(list)
_NOVA_RATE_LIMIT = 30
_NOVA_RATE_WINDOW = 60


def _nova_auth():
    """Validate Nova API secret + rate limit. Returns error response or None if OK."""
    # Auth check — require secret unless dev mode
    if not NOVA_API_SECRET and not _NOVA_DEV_MODE:
        return jsonify({"error": "NOVA_API_SECRET not configured"}), 401
    if NOVA_API_SECRET:
        secret = request.headers.get("X-Nova-Secret", "")
        if secret != NOVA_API_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    # Content-Type check on POST (CSRF defense-in-depth)
    if request.method == "POST":
        ct = request.content_type or ""
        if "application/json" not in ct:
            return jsonify({"error": "Content-Type must be application/json"}), 415

    # Rate limiting per IP
    ip = request.remote_addr or "unknown"
    now = _nova_time.time()
    _nova_rate_windows[ip] = [t for t in _nova_rate_windows[ip] if now - t < _NOVA_RATE_WINDOW]
    if len(_nova_rate_windows[ip]) >= _NOVA_RATE_LIMIT:
        return jsonify({"error": "Rate limited"}), 429
    _nova_rate_windows[ip].append(now)

    # Prevent unbounded memory growth in rate limiter
    if len(_nova_rate_windows) > 10000:
        oldest_ip = min(_nova_rate_windows.keys(), key=lambda k: _nova_rate_windows[k][0] if _nova_rate_windows[k] else 0)
        _nova_rate_windows.pop(oldest_ip, None)

    return None


@app.route("/nova/prompt", methods=["POST"])
def nova_prompt():
    """Build platform-specific system prompt."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    platform = data.get("platform", "discord")
    context = data.get("context", {})

    from nova_core.prompts import build_prompt
    from nova_core.knowledge import get_relevant_faq

    # Get relevant FAQ entries if a query is provided
    faq_entries = None
    query = data.get("query", "")
    if query:
        faq_entries = get_relevant_faq(query, limit=3)

    prompt = build_prompt(platform, faq_entries=faq_entries, platform_context=context)
    return jsonify({"prompt": prompt})


@app.route("/nova/check", methods=["POST"])
def nova_check():
    """Run input through security pipeline."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    text = data.get("text", "")
    platform = data.get("platform", "discord")
    user_id = data.get("user_id", "")

    from nova_core.security import check_input

    result = check_input(text, platform, user_id)
    return jsonify({
        "safe": result.safe,
        "severity": result.severity,
        "sanitized": result.sanitized,
        "blocked": result.blocked,
    })


@app.route("/nova/filter", methods=["POST"])
def nova_filter():
    """Run output through leak detection."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    text = data.get("text", "")
    platform = data.get("platform", "discord")

    from nova_core.security import filter_output

    filtered, leak_detected = filter_output(text, platform)
    return jsonify({"filtered": filtered, "leak_detected": leak_detected})


@app.route("/nova/feedback", methods=["POST"])
def nova_feedback():
    """Store feedback from any platform."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}

    from nova_core.feedback import store_feedback

    fid = store_feedback(
        platform=data.get("platform", "unknown"),
        user_id=data.get("user_id", ""),
        rating=data.get("rating", 5),
        question_text=data.get("question", ""),
        answer_text=data.get("answer", ""),
        comment=data.get("comment", ""),
        conversation_id=data.get("conversation_id", ""),
        message_id=data.get("message_id", ""),
    )
    return jsonify({"id": fid, "ok": True})


@app.route("/nova/knowledge", methods=["GET"])
def nova_knowledge():
    """Get relevant FAQ entries for a query."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    query = request.args.get("query", "")
    try:
        limit = min(int(request.args.get("limit", "3")), 20)
    except (ValueError, TypeError):
        limit = 3

    from nova_core.knowledge import get_relevant_faq

    entries = get_relevant_faq(query, limit=limit)
    return jsonify({"entries": entries})


@app.route("/nova/digest", methods=["GET"])
def nova_digest():
    """Cross-platform daily digest for morning briefing."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    hours = int(request.args.get("hours", "24"))

    from nova_core.feedback import get_digest

    digest = get_digest(hours)
    return jsonify(digest)


# ── Nova Cross-Platform Sync API ─────────────────────────────────────────────

_DISCORD_BOT_DB = str(Path(__file__).parent / ".tmp" / "discord" / "discord_bot.db")
_STUDENT_LEARNING_DB = str(Path(__file__).parent / ".tmp" / "discord" / "nova_student_learning.db")
_COACHING_DB = str(Path(__file__).parent / ".tmp" / "coaching" / "students.db")


@app.route("/nova/faq", methods=["GET"])
def nova_faq():
    """Return all approved FAQ entries from the Discord knowledge base."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    import sqlite3 as _sq
    try:
        conn = _sq.connect(_DISCORD_BOT_DB, timeout=5)
        conn.row_factory = _sq.Row
        rows = conn.execute(
            "SELECT id, question, answer, source, upvotes, downvotes "
            "FROM knowledge_base WHERE approved = 1 ORDER BY upvotes DESC, id ASC"
        ).fetchall()
        conn.close()
        entries = [
            {
                "id": r["id"],
                "question": r["question"],
                "answer": r["answer"],
                "source": r["source"],
                "upvotes": r["upvotes"],
                "downvotes": r["downvotes"],
            }
            for r in rows
        ]
        return jsonify({"entries": entries, "count": len(entries)})
    except Exception as e:
        return jsonify({"error": str(e), "entries": [], "count": 0}), 500


@app.route("/nova/log", methods=["POST"])
def nova_log():
    """Log a SaaS conversation turn into the learning engine for Discord cross-ref."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    data = request.get_json() or {}
    user_id = data.get("user_id", "")
    question = data.get("question", "")
    answer = data.get("answer", "")
    platform = data.get("platform", "profits")
    email = data.get("email", "")

    if not question:
        return jsonify({"ok": False, "error": "question is required"}), 400

    import sqlite3 as _sq

    # Resolve student name from email via coaching students.db
    user_name = email or user_id
    if email:
        try:
            sconn = _sq.connect(_COACHING_DB, timeout=5)
            row = sconn.execute(
                "SELECT name FROM students WHERE email = ? LIMIT 1", (email,)
            ).fetchone()
            sconn.close()
            if row:
                user_name = row[0]
        except Exception:
            pass

    # Extract topic keywords
    from nova_core.knowledge import extract_keywords, detect_category
    topic = detect_category(question)
    keywords = extract_keywords(question)

    try:
        conn = _sq.connect(_STUDENT_LEARNING_DB, timeout=5)
        conn.execute(
            "INSERT INTO interactions (user_id, user_name, question, answer, topic, tokens_in, tokens_out, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, 0, datetime('now'))",
            (user_id, user_name, question[:2000], answer[:4000], topic),
        )
        # Update topic_patterns
        existing = conn.execute(
            "SELECT id, question_count, sample_questions FROM topic_patterns WHERE topic = ?",
            (topic,),
        ).fetchone()
        if existing:
            count = (existing[1] or 0) + 1
            samples = existing[2] or ""
            # Keep last 5 sample questions
            sample_list = [s for s in samples.split("|||") if s][-4:]
            sample_list.append(question[:200])
            conn.execute(
                "UPDATE topic_patterns SET question_count = ?, last_asked = datetime('now'), sample_questions = ? WHERE id = ?",
                (count, "|||".join(sample_list), existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO topic_patterns (topic, question_count, last_asked, sample_questions) VALUES (?, 1, datetime('now'), ?)",
                (topic, question[:200]),
            )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/nova/recent-activity", methods=["GET"])
def nova_recent_activity():
    """Return recent Discord/SaaS activity for a student by email."""
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"error": "email parameter required"}), 400

    import sqlite3 as _sq

    # Find user_id(s) for this email in coaching DB
    user_ids = []
    try:
        sconn = _sq.connect(_COACHING_DB, timeout=5)
        rows = sconn.execute(
            "SELECT discord_user_id FROM students WHERE email = ? AND discord_user_id IS NOT NULL",
            (email,),
        ).fetchall()
        sconn.close()
        user_ids = [r[0] for r in rows if r[0]]
    except Exception:
        pass

    # Also check learning DB by email-as-user_id (SaaS logs use supabase UUID or email)
    result = {
        "discord_topics": [],
        "discord_last_question": "",
        "discord_interactions": 0,
        "saas_topics": [],
        "saas_interactions": 0,
    }

    try:
        conn = _sq.connect(_STUDENT_LEARNING_DB, timeout=5)

        # Build user_id match set (discord IDs + email + supabase UUID patterns)
        id_placeholders = ",".join("?" for _ in user_ids) if user_ids else "'__none__'"
        id_params = list(user_ids)

        # Get interactions by discord user_ids
        if user_ids:
            discord_rows = conn.execute(
                f"SELECT question, topic, created_at FROM interactions "
                f"WHERE user_id IN ({id_placeholders}) ORDER BY created_at DESC LIMIT 20",
                id_params,
            ).fetchall()
        else:
            discord_rows = []

        # Get interactions logged from SaaS (user_name = email)
        saas_rows = conn.execute(
            "SELECT question, topic, created_at FROM interactions "
            "WHERE user_name = ? OR user_id = ? ORDER BY created_at DESC LIMIT 20",
            (email, email),
        ).fetchall()

        conn.close()

        # Process discord interactions
        discord_topics = set()
        for r in discord_rows:
            if r[1]:
                discord_topics.add(r[1])
        result["discord_topics"] = list(discord_topics)
        result["discord_interactions"] = len(discord_rows)
        if discord_rows:
            result["discord_last_question"] = discord_rows[0][0][:200] if discord_rows[0][0] else ""

        # Process SaaS interactions
        saas_topics = set()
        for r in saas_rows:
            if r[1]:
                saas_topics.add(r[1])
        result["saas_topics"] = list(saas_topics)
        result["saas_interactions"] = len(saas_rows)

    except Exception:
        pass

    return jsonify(result)


@app.route("/nova/students", methods=["GET"])
def nova_students():
    """Return real student data from Supabase for owner/admin queries.

    Query params:
        limit (int): max students to return (default 20)
        sort (str): 'newest', 'at_risk', 'top' (default 'newest')
        name (str): search by name (partial match)
    """
    auth_err = _nova_auth()
    if auth_err:
        return auth_err

    import requests as _req

    supabase_url = os.environ.get("PROFITS_SUPABASE_URL", "")
    supabase_key = os.environ.get("PROFITS_SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        return jsonify({"error": "Supabase not configured", "students": []}), 500

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    limit = min(int(request.args.get("limit", 20)), 50)
    sort = request.args.get("sort", "newest")
    name_filter = request.args.get("name", "").strip()

    try:
        # Fetch users with student role
        users_url = f"{supabase_url}/rest/v1/users?select=id,email,full_name,student_tier,plan,subscription_status,created_at,last_signed_in,avatar_url&role=eq.student&order=created_at.desc&limit={limit}"
        if name_filter:
            users_url += f"&full_name=ilike.%25{name_filter}%25"
        users_resp = _req.get(users_url, headers=headers, timeout=10)
        users = users_resp.json() if users_resp.ok else []

        if not users:
            return jsonify({"students": [], "count": 0})

        user_ids = [u["id"] for u in users]

        # Fetch student_profiles for these users
        profiles_url = f"{supabase_url}/rest/v1/student_profiles?select=user_id,struggles,experience_level,capital_available,preferred_schedule,detailed_goals,onboarding_completed,onboarding_step,location,bio&user_id=in.({','.join(user_ids)})"
        profiles_resp = _req.get(profiles_url, headers=headers, timeout=10)
        profiles = {p["user_id"]: p for p in (profiles_resp.json() if profiles_resp.ok else [])}

        # Fetch milestones
        milestones_url = f"{supabase_url}/rest/v1/academy_milestones?select=user_id,milestone&user_id=in.({','.join(user_ids)})"
        milestones_resp = _req.get(milestones_url, headers=headers, timeout=10)
        milestones_by_user = {}
        for m in (milestones_resp.json() if milestones_resp.ok else []):
            milestones_by_user.setdefault(m["user_id"], []).append(m["milestone"])

        # Build response
        students = []
        for u in users:
            uid = u["id"]
            profile = profiles.get(uid, {})
            student = {
                "name": u.get("full_name") or u.get("email", "").split("@")[0],
                "email": u.get("email"),
                "tier": u.get("student_tier") or u.get("plan"),
                "joined": u.get("created_at", "")[:10],
                "last_active": u.get("last_signed_in", "")[:10] if u.get("last_signed_in") else "never",
                "subscription": u.get("subscription_status"),
                "onboarding_completed": profile.get("onboarding_completed", False),
                "onboarding_step": profile.get("onboarding_step", 0),
                "experience_level": profile.get("experience_level"),
                "capital_available": profile.get("capital_available"),
                "struggles": profile.get("struggles"),
                "goals": profile.get("detailed_goals"),
                "location": profile.get("location"),
                "schedule": profile.get("preferred_schedule"),
                "milestones": milestones_by_user.get(uid, []),
            }
            students.append(student)

        return jsonify({"students": students, "count": len(students)})

    except Exception as e:
        return jsonify({"error": str(e), "students": []}), 500


# ── Product Review Queue API ─────────────────────────────────────────────────

PRODUCT_CHANNEL_ID = "1352031282799837237"  # 🔎┃new-product-lead

@app.route("/api/product-queue/pending", methods=["GET"])
def product_queue_pending():
    """List pending products for admin review."""
    try:
        from execution.sourcing_review_queue import get_db, review_pending, get_status
        conn = get_db()
        products = review_pending(conn)
        stats = get_status(conn)
        conn.close()
        return jsonify({"products": products, "stats": stats})
    except Exception as e:
        return jsonify({"products": [], "error": str(e)}), 500


@app.route("/api/product-queue/approve", methods=["POST"])
def product_queue_approve():
    """Approve products for Discord delivery."""
    try:
        from execution.sourcing_review_queue import get_db, approve_products
        data = request.get_json() or {}
        ids = data.get("ids")
        conn = get_db()
        if ids:
            count = approve_products(conn, [int(i) for i in ids])
        else:
            count = approve_products(conn)
        conn.close()
        return jsonify({"approved": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/product-queue/reject", methods=["POST"])
def product_queue_reject():
    """Reject products with reason."""
    try:
        from execution.sourcing_review_queue import get_db, reject_products
        data = request.get_json() or {}
        ids = data.get("ids", [])
        reason = data.get("reason", "")
        conn = get_db()
        count = reject_products(conn, [int(i) for i in ids], reason)
        conn.close()
        return jsonify({"rejected": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/product-queue/send", methods=["POST"])
def product_queue_send():
    """Send approved products to Discord #new-product-lead channel."""
    try:
        from execution.sourcing_review_queue import get_db, send_to_discord
        conn = get_db()
        sent = send_to_discord(conn, PRODUCT_CHANNEL_ID)
        conn.close()
        return jsonify({"sent": sent})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/product-queue/ingest", methods=["POST"])
def product_queue_ingest():
    """Ingest new products from sourcing results into the review queue."""
    try:
        from execution.sourcing_review_queue import get_db, ingest_dir
        conn = get_db()
        count = ingest_dir(conn)
        conn.close()
        return jsonify({"ingested": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── GHL Webhook Routes (Zapier replacement) ───

@app.route("/webhooks/<slug>", methods=["POST"])
def ghl_webhook(slug):
    """Generic GHL webhook handler — routes by slug to the right Discord channel."""
    try:
        from execution.ghl_automations import WEBHOOK_HANDLERS
        handler = WEBHOOK_HANDLERS.get(slug)
        if not handler:
            return jsonify({"error": f"Unknown webhook: {slug}", "available": list(WEBHOOK_HANDLERS.keys())}), 404
        data = request.get_json(force=True, silent=True) or {}
        result = handler(data)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"[webhook/{slug}] {e}")
        return jsonify({"error": str(e)}), 500


# ─── Automation Engine (used by 247growth.org Automation Builder) ───

@app.route("/automations/execute", methods=["POST"])
def run_automation():
    """Execute an automation's action chain from the Automation Builder UI."""
    # Auth: shared secret or localhost only
    secret = os.environ.get("AUTOMATION_ENGINE_SECRET", "")
    if secret:
        provided = request.headers.get("X-Automation-Secret", "")
        if provided != secret:
            return jsonify({"error": "Invalid secret"}), 401

    try:
        data = request.get_json(force=True, silent=True) or {}
        automation_id = data.get("automation_id", "unknown")
        actions = data.get("actions", [])
        trigger_data = data.get("trigger_data", {})
        dry_run = data.get("dry_run", False)

        if not actions:
            return jsonify({"error": "No actions provided"}), 400

        from execution.automation_engine import execute_automation
        result = execute_automation(automation_id, actions, trigger_data, dry_run=dry_run)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"[automation-engine] {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    cleanup_old_results()
    app.run(debug=True, port=5050)
