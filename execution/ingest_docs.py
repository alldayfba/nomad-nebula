#!/usr/bin/env python3
"""
Script: ingest_docs.py
Purpose: Process new business docs (SOPs, brand guides, style docs) from uploads/ into agent memory
Inputs:  Files dropped into /Users/Shared/antigravity/memory/uploads/ (.md, .txt, .pdf)
Outputs: Key extracts appended to the relevant references.md in memory/
"""

import argparse
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path("/Users/Shared/antigravity/memory")
UPLOADS_DIR = MEMORY_ROOT / "uploads"
PROCESSED_DIR = UPLOADS_DIR / "processed"

BUCKET_KEYWORDS = {
    "agency": ["agency", "growth", "retainer", "b2b", "cac", "ltv", "ads", "funnel", "client", "marketing"],
    "amazon": ["amazon", "fba", "product research", "ppc", "acos", "listing", "supplier", "alibaba", "seller"],
}


def detect_bucket(content: str, filename: str) -> str:
    """Determine which memory bucket a doc belongs to."""
    text = (content + filename).lower()
    scores = {bucket: 0 for bucket in BUCKET_KEYWORDS}
    for bucket, keywords in BUCKET_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[bucket] += 1
    best = max(scores, key=lambda b: scores[b])
    return best if scores[best] > 0 else "global"


def read_file(path: Path) -> str:
    """Read file content. Supports .md, .txt. PDF requires pypdf (optional)."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="ignore")
    elif suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            print("[ingest] WARNING: pypdf not installed. Install with: pip install pypdf")
            print("[ingest] Skipping PDF — install pypdf to support PDF ingestion.")
            return ""
    else:
        print(f"[ingest] Unsupported file type: {suffix} — skipping {path.name}")
        return ""


def format_entry(filename: str, bucket: str, content: str) -> str:
    """Format a doc entry for appending to references.md."""
    date = datetime.now().strftime("%Y-%m-%d")
    # Take first 3000 chars as summary — enough context without overwhelming
    preview = content[0:3000].strip()
    if len(content) > 3000:
        preview += "\n\n[... truncated — full doc at uploads/processed/" + filename + "]"
    return f"""
---

## [{filename}] — Ingested {date}

**Detected bucket:** {bucket}

{preview}
"""


def ingest_file(path: Path) -> bool:
    """Process a single file into the appropriate memory bucket."""
    print(f"[ingest] Processing: {path.name}")
    content = read_file(path)
    if not content.strip():
        print(f"[ingest] Empty content — skipping {path.name}")
        return False

    bucket = detect_bucket(content, path.name)
    references_file = MEMORY_ROOT / bucket / "references.md"

    if not references_file.exists():
        print(f"[ingest] ERROR: references.md not found for bucket '{bucket}' at {references_file}")
        return False

    entry = format_entry(path.name, bucket, content)
    with open(references_file, "a", encoding="utf-8") as f:
        f.write(entry)

    # Move to processed/
    PROCESSED_DIR.mkdir(exist_ok=True)
    os.chmod(PROCESSED_DIR, 0o770)
    dest = PROCESSED_DIR / path.name
    shutil.move(str(path), str(dest))

    print(f"[ingest] ✓ {path.name} → memory/{bucket}/references.md")
    print(f"[ingest]   Archived to: uploads/processed/{path.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Ingest business docs into agent memory")
    parser.add_argument("--file", help="Process a specific file (default: process all in uploads/)")
    parser.add_argument("--watch", action="store_true", help="Watch uploads/ continuously (runs as daemon)")
    args = parser.parse_args()

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(UPLOADS_DIR, 0o770)

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"[ingest] ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        ingest_file(path)
        return

    if args.watch:
        import time
        print(f"[ingest] Watching {UPLOADS_DIR} for new files... (Ctrl+C to stop)")
        seen = set()
        while True:
            for f in UPLOADS_DIR.iterdir():
                if f.is_file() and f.name not in seen and not f.name.startswith("."):
                    seen.add(f.name)
                    ingest_file(f)
            time.sleep(5)
        return

    # Default: process everything currently in uploads/
    files = [f for f in UPLOADS_DIR.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not files:
        print(f"[ingest] No files found in {UPLOADS_DIR}")
        print(f"[ingest] Drop .md, .txt, or .pdf files there and run again.")
        sys.exit(0)

    count = 0
    for f in sorted(files):
        if ingest_file(f):
            count += 1
    print(f"[ingest] Done. {count}/{len(files)} files ingested.")


if __name__ == "__main__":
    main()
