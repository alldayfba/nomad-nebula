#!/usr/bin/env python3
"""
Script: codesec_scan.py
Purpose: Scan the ecosystem for security vulnerabilities, code quality issues,
         and infrastructure integrity problems. Generate CodeSec Reports (CSRs).

Usage:
  python execution/codesec_scan.py              # Full scan
  python execution/codesec_scan.py --security   # Security scan only
  python execution/codesec_scan.py --quality    # Code quality scan only
  python execution/codesec_scan.py --infra      # Infrastructure integrity only
  python execution/codesec_scan.py --file path  # Scan specific file
  python execution/codesec_scan.py --list-pending   # List pending CSRs
  python execution/codesec_scan.py --show CSR-ID    # Show specific CSR
  python execution/codesec_scan.py --dry-run    # Scan only, no CSRs written
  python execution/codesec_scan.py --full       # Ignore change detection, scan all
  python execution/codesec_scan.py --stats      # Findings summary

100% deterministic — no LLM API calls. Zero cost to run.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import py_compile
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))
SHARED_ROOT = Path("/Users/Shared/antigravity")

# Output directories
TMP_DIR = PROJECT_ROOT / ".tmp" / "codesec"
REPORTS_DIR = TMP_DIR / "reports"
SCANS_DIR = TMP_DIR / "scans"
LAST_SCAN_FILE = TMP_DIR / "last-scan.json"
FINDINGS_INDEX = TMP_DIR / "findings-index.json"

# Brain
BRAIN_FILE = SHARED_ROOT / "memory" / "ceo" / "brain.md"

# Monitored directories
MONITORED_DIRS = [
    PROJECT_ROOT / "directives",
    PROJECT_ROOT / "execution",
    PROJECT_ROOT / "SabboOS" / "Agents",
    PROJECT_ROOT / "SabboOS",
    PROJECT_ROOT / "bots",
    PROJECT_ROOT / "clients",
    SHARED_ROOT / "memory",
]

MONITORED_EXTS = {".md", ".py", ".yaml", ".yml", ".json", ".sh", ".env"}

# Files to always scan regardless of extension
MONITORED_FILES = [
    PROJECT_ROOT / ".env",
]

# ─── Script-to-Agent Map ─────────────────────────────────────────────────────

SCRIPT_AGENT_MAP = {
    "run_scraper.py": "lead-gen",
    "scrape_retail_products.py": "sourcing",
    "match_amazon_products.py": "sourcing",
    "calculate_fba_profitability.py": "sourcing",
    "run_sourcing_pipeline.py": "sourcing",
    "reverse_sourcing.py": "sourcing",
    "price_tracker.py": "sourcing",
    "scheduled_sourcing.py": "sourcing",
    "sourcing_alerts.py": "sourcing",
    "export_to_sheets.py": "CEO",
    "scrape_cardbear.py": "sourcing",
    "batch_asin_checker.py": "sourcing",
    "storefront_stalker.py": "sourcing",
    "inventory_tracker.py": "sourcing",
    "training_officer_scan.py": "TrainingOfficer",
    "agent_quality_tracker.py": "TrainingOfficer",
    "brain_maintenance.py": "CEO",
    "update_ceo_brain.py": "CEO",
    "watch_inbox.py": "CEO",
    "codesec_scan.py": "CodeSec",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY RULES (SEC-001 through SEC-010)
# ═══════════════════════════════════════════════════════════════════════════════

SECURITY_RULES: Dict[str, Dict[str, Any]] = {
    "SEC-001": {
        "name": "Hardcoded Secrets",
        "severity": "critical",
        "description": "API keys, tokens, or passwords hardcoded outside .env",
        "patterns": [
            # Anthropic keys
            r'["\']sk-ant-api\d+-[A-Za-z0-9_-]{20,}["\']',
            # GitHub tokens
            r'["\']ghp_[A-Za-z0-9]{36,}["\']',
            # Slack tokens
            r'["\']xox[bsp]-[A-Za-z0-9-]{20,}["\']',
            # Google API keys
            r'["\']AIza[A-Za-z0-9_-]{35}["\']',
            # AWS access keys
            r'["\']AKIA[A-Z0-9]{16}["\']',
            # Generic password/secret assignments
            r'(?:password|passwd|secret|api_key|apikey|api_secret)\s*=\s*["\'][^"\']{8,}["\']',
        ],
        "exclude_files": [".env", ".env.example", ".env.template"],
        "risk": "Credentials exposed in source code can be scraped, leaked, or committed to version control",
    },
    "SEC-002": {
        "name": "SQL Injection",
        "severity": "high",
        "description": "String formatting used in SQL queries",
        "patterns": [
            r'execute\(\s*f["\']',
            r'execute\(\s*["\'].*%s',
            r'execute\(\s*["\'].*\.format\(',
            r'cursor\.\w+\(\s*f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)',
        ],
        "risk": "Attacker-controlled input could modify database queries",
    },
    "SEC-003": {
        "name": "Command Injection",
        "severity": "high",
        "description": "Unsanitized input in shell commands",
        "patterns": [
            r'subprocess\.\w+\([^)]*shell\s*=\s*True',
            r'os\.system\(\s*f["\']',
            r'os\.popen\(\s*f["\']',
            r'subprocess\.call\(\s*f["\']',
            r'subprocess\.run\(\s*f["\']',
        ],
        "risk": "Attacker-controlled input could execute arbitrary system commands",
    },
    "SEC-004": {
        "name": "Insecure Deserialization",
        "severity": "medium",
        "description": "Unsafe deserialization of untrusted data",
        "patterns": [
            r'pickle\.loads?\(',
            r'yaml\.load\([^)]*\)(?!\s*#\s*safe)',
            r'yaml\.load\(\s*[^,)]+\s*\)(?!.*Loader)',
        ],
        "risk": "Deserialization of untrusted data can lead to remote code execution",
    },
    "SEC-005": {
        "name": "Path Traversal",
        "severity": "high",
        "description": "User input used in file paths without sanitization",
        "patterns": [
            r'open\(\s*(?:request|user_input|params|args)\.',
            r'Path\(\s*(?:request|user_input|params)\.',
            r'os\.path\.join\([^,]+,\s*(?:request|user_input|params)\.',
        ],
        "risk": "Attacker could access files outside intended directory",
    },
    "SEC-006": {
        "name": "SSRF",
        "severity": "medium",
        "description": "User-controlled URLs in HTTP requests",
        "patterns": [
            r'requests\.(?:get|post|put|delete|patch)\(\s*(?:url|user_url|target)',
        ],
        "risk": "Attacker could make the server request internal/restricted resources",
    },
    "SEC-007": {
        "name": "Debug Leftovers",
        "severity": "low",
        "description": "Debug flags or sensitive data in print statements",
        "patterns": [
            r'debug\s*=\s*True',
            r'print\(.*(?:password|secret|api_key|token|credential)',
            r'#\s*TODO.*(?:password|secret|key|token)',
        ],
        "risk": "Debug artifacts could leak sensitive information in production",
    },
    "SEC-008": {
        "name": "Insecure File Permissions",
        "severity": "medium",
        "description": "World-writable file permissions",
        "patterns": [
            r'os\.chmod\([^,]+,\s*0o777\)',
            r'os\.chmod\([^,]+,\s*0o666\)',
            r'chmod\s+777\s',
            r'chmod\s+666\s',
        ],
        "risk": "Any user on the system could read/write/execute the file",
    },
    "SEC-009": {
        "name": "Credential Logging",
        "severity": "high",
        "description": "Sensitive data passed to logging calls",
        "patterns": [
            r'logging\.(?:info|debug|warning|error|critical)\(.*(?:password|secret|api_key|token|credential)',
            r'logger\.(?:info|debug|warning|error|critical)\(.*(?:password|secret|api_key|token|credential)',
        ],
        "risk": "Credentials could appear in log files accessible to unauthorized users",
    },
    "SEC-010": {
        "name": "Weak Crypto",
        "severity": "medium",
        "description": "Weak hash algorithms used for security purposes",
        "patterns": [
            r'hashlib\.md5\(',
            r'hashlib\.sha1\(',
        ],
        "risk": "MD5 and SHA1 are cryptographically broken for security use",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# CODE QUALITY RULES (CQ-001 through CQ-007)
# ═══════════════════════════════════════════════════════════════════════════════

def check_bare_excepts(content: str, filepath: str) -> List[Dict]:
    """CQ-001: Find bare except clauses."""
    findings = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped == "except:" or re.match(r'^except\s*:\s*$', stripped):
            findings.append({
                "rule_id": "CQ-001",
                "category": "code-quality",
                "severity": "medium",
                "title": "Bare except clause",
                "description": "Catching all exceptions hides bugs and makes debugging harder",
                "target_file": filepath,
                "line_number": i,
                "code_snippet": stripped,
                "proposed_fix": "except Exception as e:  # Specify the exception type",
                "risk_if_ignored": "Silently swallows errors including KeyboardInterrupt and SystemExit",
            })
    return findings


def check_mutable_defaults(content: str, filepath: str) -> List[Dict]:
    """CQ-003: Find mutable default arguments."""
    findings = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if default is None:
                    continue
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    type_name = type(default).__name__.lower()
                    findings.append({
                        "rule_id": "CQ-003",
                        "category": "code-quality",
                        "severity": "medium",
                        "title": f"Mutable default argument ({type_name}) in {node.name}()",
                        "description": "Mutable defaults are shared across all calls, causing unexpected behavior",
                        "target_file": filepath,
                        "line_number": node.lineno,
                        "code_snippet": f"def {node.name}(... = {type_name})",
                        "proposed_fix": f"Use None as default, then `arg = arg or {type_name}()` inside function",
                        "risk_if_ignored": "Shared mutable state between function calls leads to hard-to-find bugs",
                    })
    return findings


def check_missing_error_handling(content: str, filepath: str) -> List[Dict]:
    """CQ-004: External calls without try/except."""
    findings = []
    lines = content.splitlines()
    patterns = [
        (r'requests\.(?:get|post|put|delete|patch)\(', "HTTP request"),
        (r'subprocess\.(?:run|call|check_output|Popen)\(', "subprocess call"),
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern, desc in patterns:
            if re.search(pattern, stripped):
                # Check if inside try block (look back up to 10 lines for 'try:')
                in_try = False
                for j in range(max(0, i - 11), i - 1):
                    if "try:" in lines[j]:
                        in_try = True
                        break
                if not in_try:
                    findings.append({
                        "rule_id": "CQ-004",
                        "category": "code-quality",
                        "severity": "medium",
                        "title": f"Unhandled {desc} call",
                        "description": f"{desc} without try/except could crash on network/process errors",
                        "target_file": filepath,
                        "line_number": i,
                        "code_snippet": stripped[:120],
                        "proposed_fix": f"Wrap in try/except to handle potential errors from {desc}",
                        "risk_if_ignored": "Unhandled exceptions from external calls crash the script",
                    })
    return findings


def check_hardcoded_paths(content: str, filepath: str) -> List[Dict]:
    """CQ-005: Absolute paths that should be configurable."""
    findings = []
    # Skip files that define PROJECT_ROOT (they're the ones setting it)
    if "PROJECT_ROOT" in content and "os.environ.get" in content:
        return findings

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Find hardcoded /Users/ paths in string literals
        matches = re.findall(r'["\'](/Users/[^"\']+)["\']', stripped)
        for match in matches:
            # Skip if it's inside a comment or docstring
            if "PROJECT_ROOT" in stripped or "NOMAD_NEBULA_ROOT" in stripped:
                continue
            # Skip if it's in an environ.get default (that's the fallback pattern)
            if "os.environ.get" in stripped:
                continue
            findings.append({
                "rule_id": "CQ-005",
                "category": "code-quality",
                "severity": "low",
                "title": f"Hardcoded path: {match[:60]}",
                "description": "Absolute paths reduce portability and break on different systems",
                "target_file": filepath,
                "line_number": i,
                "code_snippet": stripped[:120],
                "proposed_fix": "Use PROJECT_ROOT / 'subpath' or os.environ.get() instead",
                "risk_if_ignored": "Script fails if run on a different machine or user account",
            })
    return findings


def check_resource_leaks(content: str, filepath: str) -> List[Dict]:
    """CQ-007: open() without context manager."""
    findings = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Find open() calls that are assigned (not in 'with' statement)
        if re.search(r'(?<!with\s)(\w+)\s*=\s*open\(', stripped):
            # Make sure it's not inside a 'with' line
            if not stripped.startswith("with "):
                findings.append({
                    "rule_id": "CQ-007",
                    "category": "code-quality",
                    "severity": "medium",
                    "title": "File opened without context manager",
                    "description": "File handle may not be properly closed on exceptions",
                    "target_file": filepath,
                    "line_number": i,
                    "code_snippet": stripped[:120],
                    "proposed_fix": "Use 'with open(...) as f:' to ensure proper cleanup",
                    "risk_if_ignored": "Resource leaks can cause file descriptor exhaustion",
                })
    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE CHECKS (INF-001 through INF-008)
# ═══════════════════════════════════════════════════════════════════════════════

def check_script_importability() -> List[Dict]:
    """INF-001: Verify all execution/*.py compile without syntax errors."""
    findings = []
    exec_dir = PROJECT_ROOT / "execution"
    if not exec_dir.exists():
        return findings

    for py_file in sorted(exec_dir.glob("*.py")):
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as e:
            findings.append({
                "rule_id": "INF-001",
                "category": "infrastructure",
                "severity": "high",
                "title": f"Syntax error in {py_file.name}",
                "description": str(e).split("\n")[0][:200],
                "target_file": str(py_file),
                "line_number": 0,
                "code_snippet": "",
                "proposed_fix": "Fix the syntax error indicated above",
                "risk_if_ignored": "Script cannot be imported or executed",
            })
    return findings


def check_directive_script_refs() -> List[Dict]:
    """INF-002: Scripts referenced in directives actually exist."""
    findings = []
    directives_dir = PROJECT_ROOT / "directives"
    if not directives_dir.exists():
        return findings

    for md_file in sorted(directives_dir.glob("*.md")):
        try:
            content = md_file.read_text(errors="ignore")
        except Exception:
            continue
        refs = re.findall(r'execution/(\w+\.py)', content)
        for ref in set(refs):
            if not (PROJECT_ROOT / "execution" / ref).exists():
                findings.append({
                    "rule_id": "INF-002",
                    "category": "infrastructure",
                    "severity": "medium",
                    "title": f"Broken script reference: execution/{ref}",
                    "description": f"{md_file.name} references execution/{ref} but file does not exist",
                    "target_file": str(md_file),
                    "line_number": 0,
                    "code_snippet": f"execution/{ref}",
                    "proposed_fix": f"Create execution/{ref} or update the directive reference",
                    "risk_if_ignored": "Directive refers to a nonexistent tool, breaking the execution layer",
                })
    return findings


def check_agent_path_refs() -> List[Dict]:
    """INF-003: Paths referenced in agent files exist on disk."""
    findings = []
    agents_dir = PROJECT_ROOT / "SabboOS" / "Agents"
    if not agents_dir.exists():
        return findings

    for md_file in sorted(agents_dir.glob("*.md")):
        try:
            content = md_file.read_text(errors="ignore")
        except Exception:
            continue
        # Find execution/ script references
        refs = re.findall(r'execution/(\w+\.(?:py|sh))', content)
        for ref in set(refs):
            if not (PROJECT_ROOT / "execution" / ref).exists():
                findings.append({
                    "rule_id": "INF-003",
                    "category": "infrastructure",
                    "severity": "medium",
                    "title": f"Agent refs missing script: execution/{ref}",
                    "description": f"{md_file.name} references execution/{ref} but file does not exist",
                    "target_file": str(md_file),
                    "line_number": 0,
                    "code_snippet": f"execution/{ref}",
                    "proposed_fix": f"Create execution/{ref} or update the agent directive",
                    "risk_if_ignored": "Agent directive references a nonexistent tool",
                })
    return findings


def check_env_keys() -> List[Dict]:
    """INF-004: Required keys present in .env (never log values)."""
    findings = []
    env_file = PROJECT_ROOT / ".env"

    if not env_file.exists():
        findings.append({
            "rule_id": "INF-004",
            "category": "infrastructure",
            "severity": "critical",
            "title": ".env file missing",
            "description": "No .env file found at project root",
            "target_file": str(env_file),
            "line_number": 0,
            "code_snippet": "",
            "proposed_fix": "Create .env with required API keys",
            "risk_if_ignored": "No API keys available — all API-dependent scripts will fail",
        })
        return findings

    try:
        content = env_file.read_text()
    except Exception:
        return findings

    required_keys = ["ANTHROPIC_API_KEY"]
    recommended_keys = ["GITHUB_TOKEN", "KEEPA_API_KEY"]

    for key in required_keys:
        if not re.search(rf'^{key}\s*=\s*.+', content, re.MULTILINE):
            findings.append({
                "rule_id": "INF-004",
                "category": "infrastructure",
                "severity": "critical",
                "title": f"Required key missing: {key}",
                "description": f"{key} not found in .env (value not logged for security)",
                "target_file": str(env_file),
                "line_number": 0,
                "code_snippet": f"{key}=<MISSING>",
                "proposed_fix": f"Add {key}=<your-key> to .env",
                "risk_if_ignored": "API-dependent scripts will fail without this key",
            })

    for key in recommended_keys:
        if not re.search(rf'^{key}\s*=\s*.+', content, re.MULTILINE):
            findings.append({
                "rule_id": "INF-004",
                "category": "infrastructure",
                "severity": "low",
                "title": f"Recommended key missing: {key}",
                "description": f"{key} not found in .env (some features may be unavailable)",
                "target_file": str(env_file),
                "line_number": 0,
                "code_snippet": f"{key}=<MISSING>",
                "proposed_fix": f"Add {key}=<your-key> to .env if needed",
                "risk_if_ignored": "Some optional features will not work",
            })
    return findings


def check_launchd_daemons() -> List[Dict]:
    """INF-005: All com.sabbo.* plists are loaded and running."""
    findings = []
    expected = [
        "com.sabbo.inbox-watcher",
        "com.sabbo.training-officer-scan",
        "com.sabbo.training-officer-watch",
    ]

    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=10
        )
        loaded = result.stdout
    except Exception as e:
        findings.append({
            "rule_id": "INF-005",
            "category": "infrastructure",
            "severity": "medium",
            "title": "Cannot check launchd daemons",
            "description": f"launchctl list failed: {e}",
            "target_file": "",
            "line_number": 0,
            "code_snippet": "",
            "proposed_fix": "Check if launchctl is accessible",
            "risk_if_ignored": "Cannot verify daemon health",
        })
        return findings

    for label in expected:
        if label not in loaded:
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
            findings.append({
                "rule_id": "INF-005",
                "category": "infrastructure",
                "severity": "medium",
                "title": f"Daemon not loaded: {label}",
                "description": f"{label} is not running. It may need to be loaded.",
                "target_file": str(plist_path),
                "line_number": 0,
                "code_snippet": "",
                "proposed_fix": f"launchctl load {plist_path}",
                "risk_if_ignored": "Automated monitoring/scanning for this daemon is offline",
            })
    return findings


def check_brain_writable() -> List[Dict]:
    """INF-006: brain.md exists and is writable."""
    findings = []
    if not BRAIN_FILE.exists():
        findings.append({
            "rule_id": "INF-006",
            "category": "infrastructure",
            "severity": "high",
            "title": "CEO brain.md missing",
            "description": f"{BRAIN_FILE} does not exist",
            "target_file": str(BRAIN_FILE),
            "line_number": 0,
            "code_snippet": "",
            "proposed_fix": "Create brain.md or check /Users/Shared/antigravity/memory/ceo/ permissions",
            "risk_if_ignored": "CEO persistent consciousness is offline — no cross-session learning",
        })
    elif not os.access(BRAIN_FILE, os.W_OK):
        findings.append({
            "rule_id": "INF-006",
            "category": "infrastructure",
            "severity": "high",
            "title": "CEO brain.md not writable",
            "description": f"{BRAIN_FILE} exists but is not writable",
            "target_file": str(BRAIN_FILE),
            "line_number": 0,
            "code_snippet": "",
            "proposed_fix": f"chmod 664 {BRAIN_FILE}",
            "risk_if_ignored": "CEO cannot update its persistent memory",
        })
    return findings


def check_bridge_directories() -> List[Dict]:
    """INF-007: Antigravity bridge directories exist with correct permissions."""
    findings = []
    required = ["inbox", "outbox", "memory", "proposals"]

    for subdir in required:
        path = SHARED_ROOT / subdir
        if not path.exists():
            findings.append({
                "rule_id": "INF-007",
                "category": "infrastructure",
                "severity": "high",
                "title": f"Bridge directory missing: {subdir}/",
                "description": f"{path} does not exist",
                "target_file": str(path),
                "line_number": 0,
                "code_snippet": "",
                "proposed_fix": f"mkdir -p {path} && chmod 777 {path}",
                "risk_if_ignored": "OpenClaw ↔ Claude Code handoff broken for this channel",
            })
        elif not os.access(path, os.W_OK):
            findings.append({
                "rule_id": "INF-007",
                "category": "infrastructure",
                "severity": "high",
                "title": f"Bridge directory not writable: {subdir}/",
                "description": f"{path} exists but is not writable",
                "target_file": str(path),
                "line_number": 0,
                "code_snippet": "",
                "proposed_fix": f"chmod 777 {path}",
                "risk_if_ignored": "Cannot write to this bridge channel",
            })
    return findings


def check_venv_health() -> List[Dict]:
    """INF-008: .venv exists and python3 is accessible."""
    findings = []
    venv_dir = PROJECT_ROOT / ".venv"

    if not venv_dir.exists():
        findings.append({
            "rule_id": "INF-008",
            "category": "infrastructure",
            "severity": "medium",
            "title": "Virtual environment missing",
            "description": f"{venv_dir} does not exist",
            "target_file": str(venv_dir),
            "line_number": 0,
            "code_snippet": "",
            "proposed_fix": "python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
            "risk_if_ignored": "Scripts may use system Python with missing dependencies",
        })
    elif not (venv_dir / "bin" / "python3").exists():
        findings.append({
            "rule_id": "INF-008",
            "category": "infrastructure",
            "severity": "medium",
            "title": "Virtual environment broken",
            "description": f"{venv_dir}/bin/python3 not found",
            "target_file": str(venv_dir),
            "line_number": 0,
            "code_snippet": "",
            "proposed_fix": "rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
            "risk_if_ignored": "Cannot activate virtual environment",
        })
    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# SCAN ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def ensure_dirs():
    """Create output directories if they don't exist."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SCANS_DIR.mkdir(parents=True, exist_ok=True)


def load_last_scan() -> Dict:
    """Load last scan state."""
    if LAST_SCAN_FILE.exists():
        try:
            return json.loads(LAST_SCAN_FILE.read_text())
        except Exception:
            return {}
    return {}


def load_findings_index() -> Dict:
    """Load findings deduplication index."""
    if FINDINGS_INDEX.exists():
        try:
            return json.loads(FINDINGS_INDEX.read_text())
        except Exception:
            return {}
    return {}


def save_findings_index(index: Dict):
    """Save findings deduplication index."""
    FINDINGS_INDEX.write_text(json.dumps(index, indent=2))


def save_last_scan(state: Dict):
    """Save last scan state."""
    LAST_SCAN_FILE.write_text(json.dumps(state, indent=2))


def finding_key(finding: Dict) -> str:
    """Generate deduplication key for a finding."""
    return f"{finding['rule_id']}:{finding.get('target_file', '')}:{finding.get('line_number', 0)}"


def is_duplicate(finding: Dict, index: Dict) -> bool:
    """Check if finding already exists in index."""
    key = finding_key(finding)
    if key in index:
        status = index[key].get("status", "")
        if status in ("pending", "acknowledged"):
            return True
    return False


def get_changed_files(last_scan: Dict, full_scan: bool = False) -> List[Path]:
    """Get files changed since last scan."""
    if full_scan:
        return get_all_monitored_files()

    last_ts = last_scan.get("timestamp", 0)
    file_mtimes = last_scan.get("file_mtimes", {})
    changed = []

    for filepath in get_all_monitored_files():
        try:
            mtime = filepath.stat().st_mtime
            prev_mtime = file_mtimes.get(str(filepath), 0)
            if mtime > prev_mtime:
                changed.append(filepath)
        except Exception:
            continue

    return changed


def get_all_monitored_files() -> List[Path]:
    """Get all files in monitored directories."""
    files = []
    for directory in MONITORED_DIRS:
        if not directory.exists():
            continue
        for filepath in directory.rglob("*"):
            if filepath.is_file() and filepath.suffix in MONITORED_EXTS:
                # Skip .tmp directories
                if ".tmp" in filepath.parts:
                    continue
                if "__pycache__" in filepath.parts:
                    continue
                files.append(filepath)

    # Add individually monitored files
    for filepath in MONITORED_FILES:
        if filepath.exists() and filepath not in files:
            files.append(filepath)

    return sorted(files)


def scan_security(filepath: Path, content: str) -> List[Dict]:
    """Run all security rules against a file."""
    findings = []
    filename = filepath.name

    for rule_id, rule in SECURITY_RULES.items():
        # Check file exclusions
        exclude_files = rule.get("exclude_files", [])
        if filename in exclude_files:
            continue

        for pattern in rule["patterns"]:
            for i, line in enumerate(content.splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    # For SEC-001, mask the actual value
                    snippet = line.strip()[:120]
                    if rule_id == "SEC-001":
                        snippet = re.sub(r'["\'][A-Za-z0-9+/=_-]{20,}["\']', '"<REDACTED>"', snippet)

                    findings.append({
                        "rule_id": rule_id,
                        "category": "security",
                        "severity": rule["severity"],
                        "title": f"{rule['name']} in {filename}",
                        "description": rule["description"],
                        "target_file": str(filepath),
                        "line_number": i,
                        "code_snippet": snippet,
                        "proposed_fix": f"Move sensitive value to .env and use os.environ.get()" if rule_id == "SEC-001" else f"Review and fix: {rule['description']}",
                        "risk_if_ignored": rule.get("risk", "Security vulnerability"),
                    })
                    break  # One finding per rule per file is enough

    return findings


def scan_code_quality(filepath: Path, content: str) -> List[Dict]:
    """Run all code quality checks against a Python file."""
    if filepath.suffix != ".py":
        return []

    findings = []
    findings.extend(check_bare_excepts(content, str(filepath)))
    findings.extend(check_mutable_defaults(content, str(filepath)))
    findings.extend(check_missing_error_handling(content, str(filepath)))
    findings.extend(check_hardcoded_paths(content, str(filepath)))
    findings.extend(check_resource_leaks(content, str(filepath)))
    return findings


def scan_infrastructure() -> List[Dict]:
    """Run all infrastructure integrity checks."""
    findings = []
    findings.extend(check_script_importability())
    findings.extend(check_directive_script_refs())
    findings.extend(check_agent_path_refs())
    findings.extend(check_env_keys())
    findings.extend(check_launchd_daemons())
    findings.extend(check_brain_writable())
    findings.extend(check_bridge_directories())
    findings.extend(check_venv_health())
    return findings


def generate_csr_id() -> str:
    """Generate a unique CSR ID."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Count existing CSRs for today
    existing = list(REPORTS_DIR.glob(f"CSR-{today}-*.yaml"))
    seq = len(existing) + 1
    return f"CSR-{today}-{seq:03d}"


def write_csr(finding: Dict, csr_id: str):
    """Write a CSR YAML file."""
    csr = {
        "report_id": csr_id,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "pending",
        "target_file": finding.get("target_file", ""),
        "target_agent": SCRIPT_AGENT_MAP.get(
            Path(finding.get("target_file", "")).name, "infrastructure"
        ),
        "category": finding.get("category", ""),
        "severity": finding.get("severity", ""),
        "title": finding.get("title", ""),
        "description": finding.get("description", ""),
        "line_number": finding.get("line_number", 0),
        "code_snippet": finding.get("code_snippet", ""),
        "rule_id": finding.get("rule_id", ""),
        "proposed_fix": finding.get("proposed_fix", ""),
        "auto_fixable": False,
        "risk_if_ignored": finding.get("risk_if_ignored", ""),
    }

    # Write as YAML-like format (avoid pyyaml dependency)
    lines = []
    for key, value in csr.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        elif "\n" in str(value):
            lines.append(f"{key}: |")
            for vline in str(value).splitlines():
                lines.append(f"  {vline}")
        else:
            lines.append(f'{key}: "{value}"')

    csr_file = REPORTS_DIR / f"{csr_id}.yaml"
    csr_file.write_text("\n".join(lines) + "\n")
    return csr_file


def load_csr(csr_id: str) -> Optional[Dict]:
    """Load a CSR file and parse it."""
    csr_file = REPORTS_DIR / f"{csr_id}.yaml"
    if not csr_file.exists():
        return None

    content = csr_file.read_text()
    csr = {}
    current_key = None
    multiline_value = []

    for line in content.splitlines():
        if line.startswith("  ") and current_key:
            multiline_value.append(line[2:])
        else:
            if current_key and multiline_value:
                csr[current_key] = "\n".join(multiline_value)
                multiline_value = []

            match = re.match(r'^(\w+):\s*(.*)$', line)
            if match:
                key, value = match.groups()
                if value == "|":
                    current_key = key
                    multiline_value = []
                else:
                    current_key = None
                    # Strip quotes
                    value = value.strip('"')
                    if value == "true":
                        value = True
                    elif value == "false":
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    csr[key] = value

    if current_key and multiline_value:
        csr[current_key] = "\n".join(multiline_value)

    return csr


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_report(new_findings: List[Dict], files_scanned: int,
                    files_changed: int, infra_results: List[Dict]) -> str:
    """Generate the formatted CodeSec Report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Count by severity
    severity_counts = defaultdict(int)
    category_counts = defaultdict(int)
    for f in new_findings:
        severity_counts[f.get("severity", "low")] += 1
        category_counts[f.get("category", "unknown")] += 1

    # Count pending CSRs
    pending_csrs = []
    for csr_file in sorted(REPORTS_DIR.glob("CSR-*.yaml")):
        csr = load_csr(csr_file.stem)
        if csr and csr.get("status") == "pending":
            pending_csrs.append(csr)

    pending_severity = defaultdict(int)
    pending_category = defaultdict(int)
    for csr in pending_csrs:
        pending_severity[csr.get("severity", "low")] += 1
        pending_category[csr.get("category", "unknown")] += 1

    # Build report
    lines = [
        "",
        "+" + "=" * 58 + "+",
        "|  CODESEC REPORT — " + now + " " * (39 - len(now)) + "|",
        "+" + "=" * 58 + "+",
        "",
        "-" * 60,
        " SCAN SUMMARY",
        "-" * 60,
        "",
        f"  Files scanned:            {files_scanned}",
        f"  Files changed since last: {files_changed}",
        f"  New findings:             {len(new_findings)}",
        f"    Critical:               {severity_counts.get('critical', 0)}",
        f"    High:                   {severity_counts.get('high', 0)}",
        f"    Medium:                 {severity_counts.get('medium', 0)}",
        f"    Low:                    {severity_counts.get('low', 0)}",
        "",
    ]

    # Critical/High findings
    crit_high = [f for f in new_findings if f.get("severity") in ("critical", "high")]
    if crit_high:
        lines.extend([
            "-" * 60,
            " CRITICAL / HIGH FINDINGS",
            "-" * 60,
            "",
        ])
        for f in crit_high:
            fname = Path(f.get("target_file", "")).name
            lines.append(f"  [{f['severity'].upper():8s}] {f['rule_id']} | {fname} | {f['title']}")
        lines.append("")

    # Code quality findings
    cq_findings = [f for f in new_findings if f.get("category") == "code-quality"]
    if cq_findings:
        lines.extend([
            "-" * 60,
            " CODE QUALITY",
            "-" * 60,
            "",
        ])
        for f in cq_findings:
            fname = Path(f.get("target_file", "")).name
            lines.append(f"  [{f['severity'].upper():8s}] {f['rule_id']} | {fname} | {f['title']}")
        lines.append("")

    # Infrastructure status
    infra_pass = len([f for f in get_all_monitored_files() if f.suffix == ".py" and "execution" in str(f)])
    infra_fail = len([f for f in infra_results if f["rule_id"] == "INF-001"])
    lines.extend([
        "-" * 60,
        " INFRASTRUCTURE STATUS",
        "-" * 60,
        "",
        f"  Script compilation:       {infra_pass - infra_fail}/{infra_pass} pass",
        f"  Launchd daemons:          {3 - len([f for f in infra_results if f['rule_id'] == 'INF-005'])}/3 running",
        f"  Bridge dirs:              {'PASS' if not any(f['rule_id'] == 'INF-007' for f in infra_results) else 'FAIL'}",
        f"  Brain.md:                 {'writable' if not any(f['rule_id'] == 'INF-006' for f in infra_results) else 'FAIL'}",
        f"  .env keys:                {'PASS' if not any(f['rule_id'] == 'INF-004' and f['severity'] == 'critical' for f in infra_results) else 'FAIL'}",
        f"  Venv health:              {'PASS' if not any(f['rule_id'] == 'INF-008' for f in infra_results) else 'FAIL'}",
        "",
    ])

    # Pending CSRs
    lines.extend([
        "-" * 60,
        " PENDING CSRs (AWAITING REVIEW)",
        "-" * 60,
        "",
        f"  Total pending:  {len(pending_csrs)}",
        f"  By severity:    CRITICAL ({pending_severity.get('critical', 0)}), "
        f"HIGH ({pending_severity.get('high', 0)}), "
        f"MEDIUM ({pending_severity.get('medium', 0)}), "
        f"LOW ({pending_severity.get('low', 0)})",
        f"  By category:    Security ({pending_category.get('security', 0)}), "
        f"Code Quality ({pending_category.get('code-quality', 0)}), "
        f"Infrastructure ({pending_category.get('infrastructure', 0)})",
        "",
    ])

    # Recommendation
    if crit_high:
        top = crit_high[0]
        lines.extend([
            "-" * 60,
            " RECOMMENDED PRIORITY",
            "-" * 60,
            "",
            f"  Review {top.get('rule_id', '')} first: {top.get('title', '')}",
            f"  Severity: {top.get('severity', '').upper()} — {top.get('risk_if_ignored', '')}",
            "",
        ])
    elif new_findings:
        top = new_findings[0]
        lines.extend([
            "-" * 60,
            " RECOMMENDED PRIORITY",
            "-" * 60,
            "",
            f"  Review {top.get('rule_id', '')}: {top.get('title', '')}",
            "",
        ])
    else:
        lines.extend([
            "-" * 60,
            " STATUS",
            "-" * 60,
            "",
            "  All clear. No new findings this scan.",
            "",
        ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_list_pending():
    """List all pending CSRs."""
    pending = []
    for csr_file in sorted(REPORTS_DIR.glob("CSR-*.yaml")):
        csr = load_csr(csr_file.stem)
        if csr and csr.get("status") == "pending":
            pending.append(csr)

    if not pending:
        print("\n  No pending CodeSec findings.\n")
        return

    print(f"\n  PENDING CODESEC FINDINGS ({len(pending)})\n")
    print(f"  {'ID':<22s} {'Severity':<10s} {'Rule':<10s} {'File':<25s} {'Title'}")
    print("  " + "-" * 90)
    for csr in pending:
        fname = Path(csr.get("target_file", "")).name[:24]
        print(f"  {csr.get('report_id', ''):<22s} "
              f"{csr.get('severity', '').upper():<10s} "
              f"{csr.get('rule_id', ''):<10s} "
              f"{fname:<25s} "
              f"{csr.get('title', '')[:40]}")
    print()


def cmd_show(csr_id: str):
    """Show a specific CSR."""
    csr = load_csr(csr_id)
    if not csr:
        print(f"\n  CSR not found: {csr_id}\n")
        return

    print(f"\n  CODESEC REPORT: {csr.get('report_id', '')}")
    print("  " + "=" * 50)
    print(f"  Status:       {csr.get('status', '')}")
    print(f"  Created:      {csr.get('created', '')}")
    print(f"  Category:     {csr.get('category', '')}")
    print(f"  Severity:     {csr.get('severity', '').upper()}")
    print(f"  Rule:         {csr.get('rule_id', '')}")
    print(f"  File:         {csr.get('target_file', '')}")
    print(f"  Line:         {csr.get('line_number', 0)}")
    print(f"  Agent:        {csr.get('target_agent', '')}")
    print()
    print(f"  Title:        {csr.get('title', '')}")
    print(f"  Description:  {csr.get('description', '')}")
    print()
    print(f"  Code:         {csr.get('code_snippet', '')}")
    print()
    print(f"  Proposed Fix: {csr.get('proposed_fix', '')}")
    print()
    print(f"  Risk:         {csr.get('risk_if_ignored', '')}")
    print()


def cmd_stats():
    """Show findings summary statistics."""
    all_csrs = []
    for csr_file in sorted(REPORTS_DIR.glob("CSR-*.yaml")):
        csr = load_csr(csr_file.stem)
        if csr:
            all_csrs.append(csr)

    if not all_csrs:
        print("\n  No CodeSec findings recorded yet.\n")
        return

    status_counts = defaultdict(int)
    severity_counts = defaultdict(int)
    category_counts = defaultdict(int)
    rule_counts = defaultdict(int)

    for csr in all_csrs:
        status_counts[csr.get("status", "unknown")] += 1
        severity_counts[csr.get("severity", "unknown")] += 1
        category_counts[csr.get("category", "unknown")] += 1
        rule_counts[csr.get("rule_id", "unknown")] += 1

    print(f"\n  CODESEC STATISTICS — {len(all_csrs)} total findings\n")

    print("  By Status:")
    for status, count in sorted(status_counts.items()):
        print(f"    {status:<15s} {count}")

    print("\n  By Severity:")
    for sev in ["critical", "high", "medium", "low"]:
        if sev in severity_counts:
            print(f"    {sev.upper():<15s} {severity_counts[sev]}")

    print("\n  By Category:")
    for cat, count in sorted(category_counts.items()):
        print(f"    {cat:<20s} {count}")

    print("\n  Top Rules:")
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"    {rule:<10s} {count}")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CodeSec Agent — Security, code quality, and infrastructure scanner"
    )
    parser.add_argument("--security", action="store_true", help="Security scan only")
    parser.add_argument("--quality", action="store_true", help="Code quality scan only")
    parser.add_argument("--infra", action="store_true", help="Infrastructure integrity only")
    parser.add_argument("--file", type=str, help="Scan a specific file")
    parser.add_argument("--list-pending", action="store_true", help="List pending CSRs")
    parser.add_argument("--show", type=str, help="Show specific CSR by ID")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no CSRs written")
    parser.add_argument("--full", action="store_true", help="Full scan ignoring change detection")
    parser.add_argument("--stats", action="store_true", help="Findings summary statistics")

    args = parser.parse_args()

    ensure_dirs()

    # ── Management commands ──
    if args.list_pending:
        cmd_list_pending()
        return

    if args.show:
        cmd_show(args.show)
        return

    if args.stats:
        cmd_stats()
        return

    # ── Determine scan scope ──
    scan_all = not (args.security or args.quality or args.infra)
    do_security = args.security or scan_all
    do_quality = args.quality or scan_all
    do_infra = args.infra or scan_all

    # ── Load state ──
    last_scan = load_last_scan()
    findings_index = load_findings_index()

    # ── Get files to scan ──
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        if not target.exists():
            print(f"[codesec] ERROR: File not found: {target}")
            sys.exit(1)
        files_to_scan = [target]
        files_changed = 1
    else:
        files_to_scan = get_changed_files(last_scan, full_scan=args.full)
        files_changed = len(files_to_scan)

    all_monitored = get_all_monitored_files()
    files_scanned = len(all_monitored) if args.full else files_changed

    print(f"[codesec] Scanning {files_scanned} files ({files_changed} changed)...")

    # ── Run scans ──
    all_findings: List[Dict] = []
    infra_results: List[Dict] = []

    # Security + Code Quality (per-file)
    for filepath in files_to_scan:
        try:
            content = filepath.read_text(errors="ignore")
        except Exception:
            continue

        if do_security:
            all_findings.extend(scan_security(filepath, content))

        if do_quality:
            all_findings.extend(scan_code_quality(filepath, content))

    # Infrastructure (system-wide)
    if do_infra:
        infra_results = scan_infrastructure()
        all_findings.extend(infra_results)

    # ── Deduplicate ──
    new_findings = []
    for finding in all_findings:
        if not is_duplicate(finding, findings_index):
            new_findings.append(finding)

    # ── Write CSRs ──
    if not args.dry_run:
        for finding in new_findings:
            csr_id = generate_csr_id()
            write_csr(finding, csr_id)
            key = finding_key(finding)
            findings_index[key] = {
                "csr_id": csr_id,
                "status": "pending",
                "created": datetime.now().isoformat(),
            }

        # Save state
        file_mtimes = {}
        for filepath in all_monitored:
            try:
                file_mtimes[str(filepath)] = filepath.stat().st_mtime
            except Exception:
                continue

        save_last_scan({
            "timestamp": datetime.now().timestamp(),
            "file_mtimes": file_mtimes,
            "scan_date": datetime.now().isoformat(),
        })
        save_findings_index(findings_index)

    # ── Generate and output report ──
    report = generate_report(new_findings, files_scanned, files_changed, infra_results)
    print(report)

    # ── Save scan report ──
    if not args.dry_run:
        scan_file = SCANS_DIR / f"scan-{datetime.now().strftime('%Y-%m-%d-%H%M')}.md"
        scan_file.write_text(report)

    # ── Summary line ──
    crit = len([f for f in new_findings if f.get("severity") == "critical"])
    high = len([f for f in new_findings if f.get("severity") == "high"])
    if crit > 0:
        print(f"[codesec] !! {crit} CRITICAL finding(s) — review immediately")
    elif high > 0:
        print(f"[codesec] ! {high} HIGH finding(s) — review recommended")
    elif new_findings:
        print(f"[codesec] {len(new_findings)} finding(s) logged")
    else:
        print("[codesec] All clear — no new findings")

    if args.dry_run:
        print("[codesec] (dry-run mode — no CSRs written)")


if __name__ == "__main__":
    main()
