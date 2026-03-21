#!/usr/bin/env python3
"""
Test suite for the sourcing pipeline.
Covers schema adapter, results DB, retailer registry, and match confidence.
All tests use mocked data — no real API calls.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add execution/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "execution"))


class TestSchemaAdapter(unittest.TestCase):
    """Test schema conversion between A, B, and C formats."""

    def setUp(self):
        from schema_adapter import schema_b_to_a, schema_c_to_a, normalize_result, wrap_for_export
        self.schema_b_to_a = schema_b_to_a
        self.schema_c_to_a = schema_c_to_a
        self.normalize_result = normalize_result
        self.wrap_for_export = wrap_for_export

    def test_schema_b_to_a_basic(self):
        """Schema B (source.py) → Schema A (pipeline) conversion."""
        b = {
            "asin": "B08TEST123",
            "amazon_title": "Test Product 5oz",
            "amazon_price": 19.99,
            "source_retailer": "target",
            "source_url": "https://target.com/test",
            "buy_cost": 9.99,
            "estimated_profit": 5.50,
            "estimated_roi": 55.0,
            "verdict": "BUY",
            "match_confidence": 0.85,
            "bsr": 12345,
            "profitability": {
                "verdict": "BUY",
                "buy_cost": 9.99,
                "sell_price": 19.99,
                "profit_per_unit": 5.50,
                "roi_percent": 55.0,
            },
        }
        a = self.schema_b_to_a(b)
        self.assertEqual(a["amazon"]["asin"], "B08TEST123")
        self.assertEqual(a["profitability"]["verdict"], "BUY")
        self.assertEqual(a["profitability"]["buy_cost"], 9.99)
        self.assertEqual(a["retailer"], "target")
        self.assertIn("name", a)

    def test_schema_b_to_a_empty(self):
        """Empty dict converts without error (may return empty or minimal structure)."""
        a = self.schema_b_to_a({})
        self.assertIsInstance(a, dict)

    def test_schema_c_to_a(self):
        """Schema C (deal_scanner) → Schema A conversion."""
        c = {
            "asin": "B08DEAL456",
            "title": "Deal Product",
            "current_price": 14.99,
            "historical_avg": 24.99,
            "deal_type": "price_drop",
            "deal_score": 85,
        }
        a = self.schema_c_to_a(c)
        self.assertEqual(a["amazon"]["asin"], "B08DEAL456")
        self.assertIn("profitability", a)

    def test_normalize_result_autodetects_schema_b(self):
        """normalize_result should autodetect Schema B and convert."""
        b = {"asin": "B123", "amazon_title": "Test", "verdict": "BUY",
             "buy_cost": 5.0, "estimated_profit": 3.0}
        result = self.normalize_result(b)
        self.assertIn("amazon", result)

    def test_wrap_for_export(self):
        """wrap_for_export should produce full export structure."""
        results = [
            {"asin": "B001", "verdict": "BUY", "buy_cost": 10, "estimated_profit": 5,
             "estimated_roi": 50, "amazon_title": "Test1", "amazon_price": 20},
            {"asin": "B002", "verdict": "MAYBE", "buy_cost": 15, "estimated_profit": 2,
             "estimated_roi": 13, "amazon_title": "Test2", "amazon_price": 22},
        ]
        export = self.wrap_for_export(results, mode_name="Brand: Test")
        self.assertIn("products", export)
        self.assertIn("summary", export)
        self.assertEqual(len(export["products"]), 2)
        self.assertIn("timestamp", export)


class TestResultsDB(unittest.TestCase):
    """Test SQLite results database."""

    def setUp(self):
        from results_db import ResultsDB
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_results.db"
        self.db = ResultsDB(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_query(self):
        """Save results and query them back."""
        results = [
            {"asin": "B001", "verdict": "BUY", "buy_cost": 10, "amazon_price": 20,
             "estimated_profit": 5, "estimated_roi": 50, "name": "Product 1"},
            {"asin": "B002", "verdict": "SKIP", "buy_cost": 15, "amazon_price": 18,
             "estimated_profit": 0.5, "estimated_roi": 3, "name": "Product 2"},
        ]
        saved = self.db.save_results("test_scan_1", "brand", results)
        self.assertEqual(saved, 2)

        rows = self.db.query_results(days=1)
        self.assertEqual(len(rows), 2)

    def test_query_verdict_filter(self):
        """Filter query by verdict."""
        results = [
            {"asin": "B001", "verdict": "BUY", "name": "Buy Product"},
            {"asin": "B002", "verdict": "SKIP", "name": "Skip Product"},
        ]
        self.db.save_results("scan_2", "category", results)

        buys = self.db.query_results(days=1, verdict="BUY")
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0]["asin"], "B001")

    def test_is_recent_duplicate(self):
        """Duplicate detection by ASIN."""
        results = [{"asin": "B001", "verdict": "BUY", "name": "Test"}]
        self.db.save_results("scan_3", "brand", results)

        self.assertTrue(self.db.is_recent_duplicate("B001", days=1))
        self.assertFalse(self.db.is_recent_duplicate("B999", days=1))
        self.assertFalse(self.db.is_recent_duplicate("", days=1))

    def test_stats(self):
        """Stats returns correct counts."""
        results = [
            {"asin": "B001", "verdict": "BUY", "estimated_roi": 50, "name": "A"},
            {"asin": "B002", "verdict": "BUY", "estimated_roi": 30, "name": "B"},
            {"asin": "B003", "verdict": "SKIP", "name": "C"},
        ]
        self.db.save_results("scan_4", "deals", results)

        s = self.db.stats()
        self.assertEqual(s["total_results"], 3)
        self.assertEqual(s["buy_count"], 2)
        self.assertIn("avg_buy_roi", s)

    def test_empty_save(self):
        """Saving empty list returns 0."""
        self.assertEqual(self.db.save_results("scan_5", "brand", []), 0)


class TestRetailerRegistry(unittest.TestCase):
    """Test retailer registry lookups."""

    def test_get_retailer(self):
        """get_retailer returns valid retailer config."""
        from retailer_registry import get_retailer
        target = get_retailer("target")
        self.assertIsNotNone(target)
        self.assertEqual(target["key"], "target")
        self.assertIn("search_url", target)

    def test_get_retailer_missing(self):
        """Unknown retailer returns None."""
        from retailer_registry import get_retailer
        result = get_retailer("nonexistent_retailer_xyz")
        self.assertIsNone(result)

    def test_get_retailers_for_product(self):
        """Category-based retailer selection returns list."""
        from retailer_registry import get_retailers_for_product
        retailers = get_retailers_for_product("Grocery", max_retailers=5)
        self.assertIsInstance(retailers, list)
        self.assertGreater(len(retailers), 0)
        self.assertLessEqual(len(retailers), 5)

    def test_detect_category(self):
        """Category detection from product name."""
        from retailer_registry import detect_category
        cats = detect_category("protein powder whey")
        self.assertIsInstance(cats, list)


class TestMatchConfidence(unittest.TestCase):
    """Test compute_match_confidence scoring."""

    def setUp(self):
        from source import compute_match_confidence
        self.compute = compute_match_confidence

    def test_identical_titles(self):
        """Identical titles should score high."""
        score = self.compute(
            "CeraVe Moisturizing Cream 19 oz",
            "CeraVe Moisturizing Cream 19 oz",
        )
        self.assertGreater(score, 0.8)

    def test_different_products(self):
        """Totally different products should score low."""
        score = self.compute(
            "Nike Running Shoes Size 10",
            "Organic Green Tea Bags 100 Count",
        )
        self.assertLess(score, 0.3)

    def test_empty_inputs(self):
        """Empty inputs should return 0."""
        self.assertEqual(self.compute("", ""), 0.0)
        self.assertEqual(self.compute("Something", ""), 0.0)
        self.assertEqual(self.compute("", "Something"), 0.0)

    def test_partial_match(self):
        """Partial brand/product match should give moderate score."""
        score = self.compute(
            "CeraVe Hydrating Face Wash 16 oz",
            "CeraVe Hydrating Facial Cleanser 16 oz",
        )
        self.assertGreater(score, 0.5)

    def test_pack_mismatch_caps_score(self):
        """Pack count mismatch should cap confidence low."""
        score = self.compute(
            "Colgate Toothpaste 6oz 2-Pack",
            "Colgate Toothpaste 6oz 6-Pack",
        )
        # Both have extractable pack counts (>=2), they differ → hard cap at 0.30
        self.assertLessEqual(score, 0.35)


class TestProxyManager(unittest.TestCase):
    """Test proxy manager initialization and rotation."""

    def test_none_provider(self):
        """Provider 'none' returns no proxies."""
        from proxy_manager import ProxyManager
        pm = ProxyManager(provider="none")
        self.assertIsNone(pm.next())
        self.assertFalse(pm.is_configured)

    def test_stats(self):
        """Stats returns expected structure."""
        from proxy_manager import ProxyManager
        pm = ProxyManager(provider="none")
        s = pm.stats()
        self.assertEqual(s["provider"], "none")
        self.assertEqual(s["total_proxies"], 0)

    def test_captcha_detection(self):
        """CAPTCHA detection catches known patterns."""
        from proxy_manager import detect_captcha
        self.assertTrue(detect_captcha("Please verify you are human"))
        self.assertTrue(detect_captcha("<div class='captcha'>Solve this</div>"))
        self.assertFalse(detect_captcha("Welcome to our store!"))
        self.assertFalse(detect_captcha(""))
        self.assertFalse(detect_captcha(None))


class TestCheckpointResumeHelpers(unittest.TestCase):
    """Test checkpoint save/load/clear functions."""

    def test_checkpoint_roundtrip(self):
        """Save and load checkpoint data."""
        from source import _save_checkpoint, _load_checkpoint, _clear_checkpoint, _checkpoint_path
        import source
        # Use a temp scan ID
        source._checkpoint_scan_id = "test_checkpoint"
        try:
            processed = {"Product A", "Product B"}
            results = [{"asin": "B001", "verdict": "BUY"}]
            _save_checkpoint(processed, results)

            loaded_processed, loaded_results = _load_checkpoint()
            self.assertEqual(loaded_processed, processed)
            self.assertEqual(len(loaded_results), 1)
            self.assertEqual(loaded_results[0]["asin"], "B001")

            _clear_checkpoint()
            cp = _checkpoint_path()
            self.assertFalse(cp.exists())
        finally:
            source._checkpoint_scan_id = None


if __name__ == "__main__":
    unittest.main()
