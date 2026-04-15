"""Tests for nova_core.asin_extractor.

Cases use real strings pulled from the Nova chat log (266 messages reviewed),
so a passing suite confirms the extractor handles the patterns students
actually use in production.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "execution"))

from nova_core.asin_extractor import (  # noqa: E402
    MAX_ASINS_PER_MESSAGE,
    extract_all,
    extract_amazon_urls,
    extract_asins,
    extract_buy_cost,
    extract_moq,
    extract_retailer_urls,
)


class TestExtractAsins:
    def test_bare_asin(self):
        assert extract_asins("can you check out this asin i just found this B0DM3R7XJX") == ["B0DM3R7XJX"]

    def test_dp_url(self):
        text = "analyze this product https://www.amazon.com/dp/B0B3KHDL5T/?th=1"
        assert extract_asins(text) == ["B0B3KHDL5T"]

    def test_gp_product_url(self):
        text = "https://www.amazon.com/gp/product/B00O0A7X9M"
        assert extract_asins(text) == ["B00O0A7X9M"]

    def test_asin_with_trailing_punctuation(self):
        text = "3.99 and B0B4HWPJ56"
        assert extract_asins(text) == ["B0B4HWPJ56"]

    def test_multiple_asins_dedupes_and_preserves_order(self):
        text = "B00BGGEEZE and B0014ZWHO2 and B00BGGEEZE again"
        assert extract_asins(text) == ["B00BGGEEZE", "B0014ZWHO2"]

    def test_caps_at_max(self):
        asins = ["B00000000" + c for c in "ABCDEFGHIJ"]
        text = " ".join(asins)
        result = extract_asins(text)
        assert len(result) == MAX_ASINS_PER_MESSAGE
        assert result == asins[:MAX_ASINS_PER_MESSAGE]

    def test_no_false_positive_on_random_text(self):
        assert extract_asins("I'm buying at $10 and making $5 profit") == []

    def test_no_false_positive_on_short_codes(self):
        # ISBNs and short codes should NOT trigger (must start with B + 9 alnum)
        assert extract_asins("978-0140186406 ISBN") == []

    def test_url_beats_bare_match(self):
        # If the same ASIN appears in a URL and as bare text, order-preserving
        # dedupe keeps the first occurrence but doesn't double-count.
        text = "see https://www.amazon.com/dp/B00BGGEEZE and B00BGGEEZE"
        assert extract_asins(text) == ["B00BGGEEZE"]


class TestExtractAmazonUrls:
    def test_amazon_com(self):
        urls = extract_amazon_urls("analyze https://www.amazon.com/dp/B0B3KHDL5T/?th=1")
        assert urls == ["https://www.amazon.com/dp/B0B3KHDL5T/?th=1"]

    def test_rejects_non_amazon(self):
        assert extract_amazon_urls("https://evil.com/dp/B0B3KHDL5T") == []

    def test_rejects_file_scheme(self):
        # SSRF defense — no file://
        assert extract_amazon_urls("file:///etc/passwd") == []

    def test_rejects_localhost(self):
        assert extract_amazon_urls("http://localhost/dp/B0B3KHDL5T") == []

    def test_rejects_private_ip(self):
        assert extract_amazon_urls("http://192.168.1.1/dp/B0B3KHDL5T") == []
        assert extract_amazon_urls("http://127.0.0.1/dp/B0B3KHDL5T") == []
        assert extract_amazon_urls("http://10.0.0.1/dp/B0B3KHDL5T") == []


class TestExtractRetailerUrls:
    def test_walmart(self):
        text = "https://www.walmart.com/ip/Athletic-Works-Women-s-Knit-Pants/5453314476 whats the best way"
        urls = extract_retailer_urls(text)
        assert len(urls) == 1
        assert "walmart.com" in urls[0]

    def test_target(self):
        text = "Source link: https://www.target.com/p/slaughterhouse-five-modern-library-100-best-novels-by-kurt-vonnegut-paperback/-/A-88890698#lnk=sametab"
        urls = extract_retailer_urls(text)
        assert len(urls) == 1
        assert "target.com" in urls[0]

    def test_rejects_unknown_retailer(self):
        assert extract_retailer_urls("https://randomshop.biz/product/123") == []

    def test_rejects_ssrf(self):
        assert extract_retailer_urls("http://169.254.169.254/latest/meta-data") == []


class TestExtractBuyCost:
    def test_purchasing_at(self):
        assert extract_buy_cost("B0014ZWHO2 purchasing at 9.04$ MOQ 320") == 9.04

    def test_im_buying_at(self):
        assert extract_buy_cost("im buying at 16.3") == 16.3

    def test_bought_at(self):
        assert extract_buy_cost("B00O0A7X9M purchased at 10.99$ MOQ of 320") == 10.99

    def test_buy_cost_dollar_prefix(self):
        assert extract_buy_cost("3.99 and B0B4HWPJ56") == 3.99

    def test_ignores_implausible_value(self):
        assert extract_buy_cost("Profit of $9999999") is None

    def test_none_when_missing(self):
        assert extract_buy_cost("just bare asin B0DM3R7XJX") is None


class TestExtractMoq:
    def test_moq_with_digits(self):
        assert extract_moq("B0014ZWHO2 purchasing at 9.04$ MOQ 320") == 320

    def test_moq_of(self):
        assert extract_moq("purchased at 10.99$ MOQ of 320") == 320

    def test_qty(self):
        assert extract_moq("qty 150") == 150

    def test_units(self):
        assert extract_moq("buying 420 units") == 420

    def test_none_when_missing(self):
        assert extract_moq("bare text no quantity") is None


class TestExtractAll:
    def test_real_chat_log_example(self):
        # Pulled verbatim from Nova chat_log on 2026-04-15
        text = "B0014ZWHO2 purchasing at 9.04$ MOQ 320"
        result = extract_all(text)
        assert result["asins"] == ["B0014ZWHO2"]
        assert result["buy_cost"] == 9.04
        assert result["moq"] == 320

    def test_source_link_plus_asin_example(self):
        text = (
            "Asin: B00BGGEEZE\n"
            "Source link: https://www.target.com/p/slaughterhouse-five/-/A-88890698\n"
            "Buy cost: 6.49"
        )
        result = extract_all(text)
        assert result["asins"] == ["B00BGGEEZE"]
        assert len(result["retailer_urls"]) == 1
        assert result["buy_cost"] == 6.49

    def test_ssrf_payload_stripped(self):
        text = "Analyze B0B3KHDL5T file:///etc/passwd http://localhost/dp/B000"
        result = extract_all(text)
        assert "B0B3KHDL5T" in result["asins"]
        assert result["amazon_urls"] == []
        assert result["retailer_urls"] == []
