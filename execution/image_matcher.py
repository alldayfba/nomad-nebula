#!/usr/bin/env python3
"""
Script: image_matcher.py
Purpose: Image-based product match verification using perceptual hashing.
         Catches matches that title-based fuzzy matching misses, and reduces
         false positives from similar-but-different products.

Inspired by Tactical Arbitrage's AI image matching — their key differentiator.

Strategy (tiered):
  1. Perceptual hash (pHash) — FREE, local, ~100ms per comparison
  2. Claude Haiku vision fallback — ~$0.01/comparison, for ambiguous cases

Dependencies:
  pip install imagehash Pillow requests

Usage:
  from image_matcher import compute_image_match_score

  score = compute_image_match_score(
      retail_image_url="https://target.com/product.jpg",
      amazon_image_url="https://m.media-amazon.com/images/I/product.jpg"
  )
  # Returns 0.0-1.0 confidence score

CLI:
  python execution/image_matcher.py --retail-url "..." --amazon-url "..."
  python execution/image_matcher.py --retail-file img1.jpg --amazon-file img2.jpg
"""

import argparse
import io
import os
import sys
import tempfile
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Perceptual Hash Matching ─────────────────────────────────────────────────

def _download_image(url, timeout=10):
    """Download image from URL and return PIL Image object."""
    if not url or not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return None

    try:
        from PIL import Image
    except ImportError:
        print("[image_matcher] ERROR: Pillow not installed. Run: pip install Pillow",
              file=sys.stderr)
        return None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if r.status_code != 200:
            return None
        return Image.open(io.BytesIO(r.content))
    except Exception as e:
        print(f"[image_matcher] Download failed for {url[:80]}: {e}", file=sys.stderr)
        return None


def _compute_phash(image, hash_size=8):
    """Compute perceptual hash for an image."""
    try:
        import imagehash
    except ImportError:
        print("[image_matcher] ERROR: imagehash not installed. Run: pip install imagehash",
              file=sys.stderr)
        return None

    try:
        return imagehash.phash(image, hash_size=hash_size)
    except Exception as e:
        print(f"[image_matcher] Hash computation failed: {e}", file=sys.stderr)
        return None


def _compute_dhash(image, hash_size=8):
    """Compute difference hash for an image (complementary to pHash)."""
    try:
        import imagehash
    except ImportError:
        return None

    try:
        return imagehash.dhash(image, hash_size=hash_size)
    except Exception:
        return None


def phash_match_score(img1, img2):
    """Compare two PIL images using perceptual hashing.

    Returns a 0.0-1.0 confidence score.
    - 1.0 = identical images
    - 0.8+ = very likely same product
    - 0.6-0.8 = possibly same product (different angle/lighting)
    - <0.6 = likely different products
    """
    phash1 = _compute_phash(img1)
    phash2 = _compute_phash(img2)

    if phash1 is None or phash2 is None:
        return None

    # Hamming distance: 0 = identical, 64 = completely different (for 8x8 hash)
    hamming = phash1 - phash2

    # Also compute dHash for cross-validation
    dhash1 = _compute_dhash(img1)
    dhash2 = _compute_dhash(img2)
    d_hamming = (dhash1 - dhash2) if (dhash1 is not None and dhash2 is not None) else hamming

    # Average both hash distances
    avg_hamming = (hamming + d_hamming) / 2.0

    # Convert to 0-1 score (64 possible bits)
    max_distance = 64
    score = max(0.0, 1.0 - (avg_hamming / max_distance))

    return round(score, 3)


# ── Claude Vision Fallback ───────────────────────────────────────────────────

def vision_match_score(img1_url, img2_url):
    """Use Claude Haiku vision to compare two product images.

    Returns a 0.0-1.0 confidence score.
    Cost: ~$0.01 per comparison.

    Only use for ambiguous cases (pHash score 0.5-0.8).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[image_matcher] No ANTHROPIC_API_KEY — skipping vision fallback.",
              file=sys.stderr)
        return None

    try:
        import anthropic
    except ImportError:
        print("[image_matcher] anthropic SDK not installed — skipping vision fallback.",
              file=sys.stderr)
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": img1_url},
                    },
                    {
                        "type": "image",
                        "source": {"type": "url", "url": img2_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Are these images of the same product? Consider brand, "
                            "packaging, size, color, and model. Respond with ONLY one "
                            "word: MATCH, LIKELY, UNLIKELY, or NOMATCH."
                        ),
                    },
                ],
            }],
        )

        response = message.content[0].text.strip().upper()
        score_map = {
            "MATCH": 0.95,
            "LIKELY": 0.75,
            "UNLIKELY": 0.35,
            "NOMATCH": 0.05,
        }
        # Find best match in response
        for keyword, score in score_map.items():
            if keyword in response:
                return score
        return 0.5  # Ambiguous response

    except Exception as e:
        print(f"[image_matcher] Vision API error: {e}", file=sys.stderr)
        return None


# ── Main API ─────────────────────────────────────────────────────────────────

def compute_image_match_score(retail_image_url=None, amazon_image_url=None,
                              retail_image=None, amazon_image=None,
                              use_vision_fallback=True):
    """Compute image match confidence between a retail and Amazon product image.

    Pass either URLs or PIL Image objects.

    Args:
        retail_image_url: URL of retail product image
        amazon_image_url: URL of Amazon product image
        retail_image: PIL Image object (alternative to URL)
        amazon_image: PIL Image object (alternative to URL)
        use_vision_fallback: If True, use Claude vision for ambiguous cases

    Returns:
        dict with score (0.0-1.0), method ("phash", "vision", or "combined"), detail
    """
    # Download images if URLs provided
    if retail_image is None and retail_image_url:
        retail_image = _download_image(retail_image_url)
    if amazon_image is None and amazon_image_url:
        amazon_image = _download_image(amazon_image_url)

    if retail_image is None or amazon_image is None:
        return {"score": None, "method": "failed", "detail": "Could not load one or both images"}

    # Step 1: Perceptual hash comparison (free, fast)
    phash_score = phash_match_score(retail_image, amazon_image)

    if phash_score is None:
        return {"score": None, "method": "failed", "detail": "Hash computation failed"}

    # Step 2: If ambiguous (0.5-0.8) and vision fallback enabled, use Claude
    if use_vision_fallback and 0.45 <= phash_score <= 0.80:
        if retail_image_url and amazon_image_url:
            vision_score = vision_match_score(retail_image_url, amazon_image_url)
            if vision_score is not None:
                # Weight: 40% phash + 60% vision (vision is more accurate)
                combined = round(0.4 * phash_score + 0.6 * vision_score, 3)
                return {
                    "score": combined,
                    "method": "combined",
                    "phash_score": phash_score,
                    "vision_score": vision_score,
                    "detail": f"pHash={phash_score}, vision={vision_score}",
                }

    # Return pHash score only
    confidence = "high" if phash_score >= 0.8 else "medium" if phash_score >= 0.6 else "low"
    return {
        "score": phash_score,
        "method": "phash",
        "detail": f"Perceptual hash similarity ({confidence} confidence)",
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Image-based product match verification")
    parser.add_argument("--retail-url", help="URL of retail product image")
    parser.add_argument("--amazon-url", help="URL of Amazon product image")
    parser.add_argument("--retail-file", help="Path to retail product image file")
    parser.add_argument("--amazon-file", help="Path to Amazon product image file")
    parser.add_argument("--no-vision", action="store_true",
                        help="Disable Claude vision fallback")

    args = parser.parse_args()

    retail_img = None
    amazon_img = None

    if args.retail_file or args.amazon_file:
        try:
            from PIL import Image
            if args.retail_file:
                safe_path = Path(args.retail_file).resolve()
                if ".." in str(safe_path) or not safe_path.is_file():
                    print("ERROR: Invalid retail image path", file=sys.stderr)
                    sys.exit(1)
                retail_img = Image.open(safe_path)
            if args.amazon_file:
                safe_path = Path(args.amazon_file).resolve()
                if ".." in str(safe_path) or not safe_path.is_file():
                    print("ERROR: Invalid amazon image path", file=sys.stderr)
                    sys.exit(1)
                amazon_img = Image.open(safe_path)
        except ImportError:
            print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
            sys.exit(1)

    result = compute_image_match_score(
        retail_image_url=args.retail_url,
        amazon_image_url=args.amazon_url,
        retail_image=retail_img,
        amazon_image=amazon_img,
        use_vision_fallback=not args.no_vision,
    )

    print(f"\nImage Match Result:")
    print(f"  Score:  {result['score']}")
    print(f"  Method: {result['method']}")
    print(f"  Detail: {result['detail']}")

    if result["score"] is not None:
        if result["score"] >= 0.8:
            print(f"  Verdict: MATCH (high confidence)")
        elif result["score"] >= 0.6:
            print(f"  Verdict: LIKELY MATCH (verify manually)")
        elif result["score"] >= 0.4:
            print(f"  Verdict: UNCERTAIN (needs manual review)")
        else:
            print(f"  Verdict: NO MATCH")


if __name__ == "__main__":
    main()
