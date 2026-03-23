#!/usr/bin/env python3
"""
Split sales call transcript files into individual call files.
Parses Fathom-style transcripts using VIEW RECORDING as the universal delimiter.

Usage:
    python execution/split_sales_transcripts.py

Output:
    .tmp/sales-audit/calls/call_NNN_<name>_<date>.txt
    .tmp/sales-audit/manifest.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

# Transcript source files (ordered)
TRANSCRIPT_FILES = [
    "/Users/sabbojb/Downloads/Sales calls.txt",
    "/Users/sabbojb/Downloads/Sales Calls 2.txt",
    "/Users/sabbojb/Downloads/Sales Calls 3 (1).txt",
    "/Users/sabbojb/Downloads/Sales Calls 4 (1).txt",
    "/Users/sabbojb/Downloads/Sales calls 5.txt",
    "/Users/sabbojb/Downloads/sales calls 6.txt",
    "/Users/sabbojb/Downloads/Untitled document (14).txt",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "calls")
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "manifest.json")

# Known closer identifiers
CLOSERS = {
    "AllDay FBA": "Sabbo",
    "alldayfbaofficial": "Sabbo",
    "Rocky Yadav": "Rocky",
    "rockyyad001": "Rocky",
}


def clean_text(text: str) -> str:
    """Remove BOM and normalize whitespace."""
    text = text.lstrip("\ufeff")
    return text


def slugify(text: str) -> str:
    """Convert text to a safe filename slug."""
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "_", text).strip("_")
    return text[:50]


def extract_duration(view_line: str) -> int:
    """Extract minutes from VIEW RECORDING line."""
    m = re.search(r"(\d+)\s*mins?", view_line)
    return int(m.group(1)) if m else 0


def extract_title_and_date(header_lines: list[str]) -> tuple[str, str]:
    """Extract meeting title and date from lines before VIEW RECORDING."""
    title = ""
    date = ""
    for line in header_lines:
        line = line.strip()
        if not line or "VIEW RECORDING" in line:
            continue
        # Skip "Call N" lines or "(wifi ...)" annotations
        if re.match(r"^Call \d+", line):
            continue
        title = line

    # Try to extract date from title
    # Pattern: "Name and Name - Role - Month DD" or "Impromptu Google Meet Meeting - Month DD"
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})",
        title
    )
    if date_match:
        date = f"{date_match.group(1)} {date_match.group(2)}"

    return title, date


def detect_closer(transcript_text: str) -> str:
    """Detect which closer is on this call."""
    closers_found = set()
    for identifier, closer_name in CLOSERS.items():
        if identifier in transcript_text:
            closers_found.add(closer_name)

    # If both are present (rare), check who speaks more
    if "Sabbo" in closers_found and "Rocky" in closers_found:
        sabbo_count = len(re.findall(r"AllDay FBA", transcript_text))
        rocky_count = len(re.findall(r"Rocky Yadav", transcript_text))
        return "Both" if abs(sabbo_count - rocky_count) < 5 else ("Sabbo" if sabbo_count > rocky_count else "Rocky")

    if "Sabbo" in closers_found:
        return "Sabbo"
    if "Rocky" in closers_found:
        return "Rocky"
    return "Unknown"


def extract_prospect_name(transcript_text: str, title: str) -> str:
    """Extract prospect name from speaker lines (the non-closer speaker)."""
    # First try title patterns with names: "Name and Sabbo" or "Name and Rocky"
    for pattern in [
        r"^(.+?)\s+and\s+(Sabbo|Rocky)",
        r"^(.+?)\s*[&+]\s*(Sabbo|Rocky|Small Offices)",
        r"^(.+?)\s*-\s*Founder\s*-",
    ]:
        title_match = re.match(pattern, title, re.IGNORECASE)
        if title_match:
            name = title_match.group(1).strip()
            # Make sure it's not a generic meeting title
            if "Impromptu" not in name and "Google Meet" not in name:
                return name

    # For titled calls like "Jessica Mena Monroy & Small Offices"
    if " & " in title and "Impromptu" not in title and "Google Meet" not in title:
        name = title.split(" & ")[0].strip()
        if name:
            return name

    # For titled calls like "Mahir and Sabbo - Founder - December 04"
    if " and " in title.lower() and "Impromptu" not in title:
        parts = re.split(r"\s+and\s+", title, flags=re.IGNORECASE)
        if parts:
            name = parts[0].strip()
            if name and "Impromptu" not in name:
                return name

    # Always fall back to finding non-closer speakers in transcript
    # This is the most reliable method
    speaker_counts = {}
    for line in transcript_text.split("\n"):
        sm = re.match(r"@[\d:]+ - (.+?)(?:\s*\(|$)", line)
        if sm:
            name = sm.group(1).strip()
            if name and name not in ("AllDay FBA", "Rocky Yadav") and len(name) < 50:
                speaker_counts[name] = speaker_counts.get(name, 0) + 1
    if speaker_counts:
        return max(speaker_counts, key=speaker_counts.get)

    return "Unknown"


def split_file(filepath: str) -> list[dict]:
    """Split a single transcript file into individual calls."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = clean_text(f.read())

    lines = content.split("\n")

    # Find all VIEW RECORDING line indices
    view_indices = []
    for i, line in enumerate(lines):
        if "VIEW RECORDING" in line:
            view_indices.append(i)

    if not view_indices:
        print(f"  WARNING: No VIEW RECORDING found in {os.path.basename(filepath)}")
        return []

    calls = []
    for idx, view_line_idx in enumerate(view_indices):
        # Header is the lines before this VIEW RECORDING, back to either:
        # - the end of previous call's content, or
        # - start of file
        if idx == 0:
            header_start = 0
        else:
            # Previous call's content ends somewhere between previous VIEW RECORDING and this one
            # Look backwards from current VIEW RECORDING for blank-line-separated header
            header_start = view_line_idx
            for j in range(view_line_idx - 1, view_indices[idx - 1], -1):
                if lines[j].strip() == "" and j < view_line_idx - 1:
                    # Check if the next non-empty line before us looks like a header
                    continue
                header_start = j
                # Keep going back until we hit actual call content (@ timestamps)
                if re.match(r"@\d+:\d+", lines[j].strip()):
                    header_start = j + 1
                    break

        header_lines = lines[header_start:view_line_idx + 1]

        # Content starts after VIEW RECORDING + blank lines
        content_start = view_line_idx + 1
        while content_start < len(lines) and lines[content_start].strip() == "":
            content_start += 1

        # Content ends at next call's header or end of file
        if idx + 1 < len(view_indices):
            # Find where next call's header begins (look for the title line before next VIEW RECORDING)
            next_view = view_indices[idx + 1]
            content_end = next_view
            # Walk backwards from next VIEW RECORDING to find header start
            for j in range(next_view - 1, content_start, -1):
                line = lines[j].strip()
                if line == "":
                    continue
                if re.match(r"@\d+:\d+", line) or re.match(r"^ACTION ITEM:", line):
                    content_end = j + 1
                    break
                # This is a header/title line
                content_end = j
        else:
            content_end = len(lines)

        transcript = "\n".join(lines[content_start:content_end]).strip()
        duration = extract_duration(lines[view_line_idx])
        title, date = extract_title_and_date(header_lines)
        closer = detect_closer(transcript)
        prospect = extract_prospect_name(transcript, title)

        calls.append({
            "source_file": os.path.basename(filepath),
            "title": title,
            "date": date,
            "duration_min": duration,
            "closer": closer,
            "prospect_name": prospect,
            "transcript": transcript,
            "view_recording_line": lines[view_line_idx].strip(),
        })

    return calls


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_calls = []
    global_idx = 0

    for filepath in TRANSCRIPT_FILES:
        if not os.path.exists(filepath):
            print(f"SKIP: {filepath} not found")
            continue

        print(f"Processing: {os.path.basename(filepath)}")
        calls = split_file(filepath)
        print(f"  Found {len(calls)} calls")

        for call in calls:
            global_idx += 1
            call["call_id"] = global_idx

            # Build filename
            prospect_slug = slugify(call["prospect_name"])
            date_slug = slugify(call["date"]) if call["date"] else "nodate"
            filename = f"call_{global_idx:03d}_{prospect_slug}_{date_slug}.txt"
            call["filename"] = filename

            # Write individual call file
            outpath = os.path.join(OUTPUT_DIR, filename)
            with open(outpath, "w", encoding="utf-8") as f:
                f.write(f"# Call {global_idx}\n")
                f.write(f"# Title: {call['title']}\n")
                f.write(f"# Date: {call['date']}\n")
                f.write(f"# Duration: {call['duration_min']} min\n")
                f.write(f"# Closer: {call['closer']}\n")
                f.write(f"# Prospect: {call['prospect_name']}\n")
                f.write(f"# Source: {call['source_file']}\n")
                f.write(f"# {call['view_recording_line']}\n")
                f.write(f"\n---\n\n")
                f.write(call["transcript"])

            # Don't store transcript in manifest (too large)
            manifest_entry = {k: v for k, v in call.items() if k != "transcript"}
            manifest_entry["char_count"] = len(call["transcript"])
            all_calls.append(manifest_entry)

    # Write manifest
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "total_calls": len(all_calls),
            "total_duration_min": sum(c["duration_min"] for c in all_calls),
            "closers": {
                "Sabbo": sum(1 for c in all_calls if c["closer"] == "Sabbo"),
                "Rocky": sum(1 for c in all_calls if c["closer"] == "Rocky"),
                "Both": sum(1 for c in all_calls if c["closer"] == "Both"),
                "Unknown": sum(1 for c in all_calls if c["closer"] == "Unknown"),
            },
            "calls": all_calls,
        }, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}")
    print(f"TOTAL: {len(all_calls)} calls split")
    print(f"Total duration: {sum(c['duration_min'] for c in all_calls)} minutes")
    print(f"Closers: Sabbo={sum(1 for c in all_calls if c['closer'] == 'Sabbo')}, "
          f"Rocky={sum(1 for c in all_calls if c['closer'] == 'Rocky')}, "
          f"Both={sum(1 for c in all_calls if c['closer'] == 'Both')}, "
          f"Unknown={sum(1 for c in all_calls if c['closer'] == 'Unknown')}")
    print(f"Files written to: {OUTPUT_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
