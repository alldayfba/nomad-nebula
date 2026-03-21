# CodeSec Agent SOP
> directives/codesec-sop.md | Version 1.0

---

## Purpose

This SOP documents how the CodeSec agent operates: how it scans files, classifies findings, generates CodeSec Reports (CSRs), manages the approval workflow, and integrates with the CEO + Training Officer.

The CodeSec agent's full directive (identity, check categories, report format, severity levels, guardrails) lives in `SabboOS/Agents/CodeSec.md`. This SOP covers the execution layer.

---

## Trigger Phrases

| User Says | Action |
|---|---|
| "Run codesec" / "Security scan" | Full scan + report |
| "codesec report" | Output latest scan report |
| "Check security" | Full scan |
| "Infrastructure check" | Infrastructure integrity only |
| "Show codesec findings" | List pending CSRs |
| "Show CSR-{id}" | Display full finding details |
| "Approve CSR-{id}" | Apply the proposed fix |
| "Reject CSR-{id}" | Mark rejected, log reason |
| "Acknowledge CSR-{id}" | Mark as accepted risk |
| "What's exposed?" | Quick secrets/credentials scan only |

---

## Execution Flow

### Full Scan

**Step 1 — Load State**
```
Read: .tmp/codesec/last-scan.json
  → Contains: last_scan_timestamp, file_hashes, findings_index
  → If file doesn't exist: first run, scan everything
```

**Step 2 — Detect Changed Files**
```
Scan monitored directories:
  directives/*.md
  execution/*.py
  SabboOS/Agents/*.md
  SabboOS/*.md
  bots/**/*
  clients/**/*
  .env
Compare mtime to last-scan.json. Queue changed/new files.
For --full flag: scan ALL files regardless of change detection.
```

**Step 3 — Security Scan**
```
For each queued file:
  Run all SEC-* rules (regex pattern matching):
  - SEC-001: Secret detection (API key patterns, token patterns)
  - SEC-002: SQL injection (f-string/format in SQL)
  - SEC-003: Command injection (subprocess shell=True with vars)
  - SEC-004: Insecure deserialization (pickle.load, unsafe yaml.load)
  - SEC-005: Path traversal
  - SEC-006: SSRF patterns
  - SEC-007: Debug leftovers
  - SEC-008: Insecure permissions
  - SEC-009: Credential logging
  - SEC-010: Weak crypto
  For each finding: generate CSR YAML
```

**Step 4 — Code Quality Scan**
```
For each queued .py file:
  - py_compile syntax check
  - AST analysis for bare excepts, unused imports, mutable defaults
  - Regex for missing error handling patterns
  - Hardcoded path detection
  For each finding: generate CSR YAML
```

**Step 5 — Infrastructure Integrity**
```
Run full infrastructure checks:
  - INF-001: py_compile every .py in execution/
  - INF-002: Parse directives/*.md for script refs, verify they exist
  - INF-003: Parse SabboOS/Agents/*.md for path refs, verify they exist
  - INF-004: Check .env for required keys (existence only, NEVER log values)
  - INF-005: launchctl list | grep com.sabbo to verify daemons
  - INF-006: Check brain.md exists and is writable
  - INF-007: Check bridge directory existence and permissions
  - INF-008: Check .venv health
  For each failure: generate CSR YAML
```

**Step 6 — Deduplicate**
```
Load findings-index.json
For each new CSR: check if (rule_id, target_file, line_number) already has a pending/acknowledged CSR
If duplicate: skip
If not: write CSR and update index
```

**Step 7 — Cross-Reference**
```
For CRITICAL/HIGH findings:
  → If finding is in execution/ script, check SCRIPT_AGENT_MAP
  → If agent training needed, flag Training Officer queue in brain.md
```

**Step 8 — Update Scan State**
```
Write last-scan.json with current timestamps and file hashes
Write findings-index.json with all finding keys
```

**Step 9 — Output Report**
```
Generate formatted CodeSec Report to stdout
Save to .tmp/codesec/scans/scan-{date}-{time}.md
```

---

## CLI Usage

```bash
# Full scan
python execution/codesec_scan.py

# Category-specific
python execution/codesec_scan.py --security
python execution/codesec_scan.py --quality
python execution/codesec_scan.py --infra

# File-specific
python execution/codesec_scan.py --file execution/run_scraper.py

# Management
python execution/codesec_scan.py --list-pending
python execution/codesec_scan.py --show CSR-2026-02-22-001
python execution/codesec_scan.py --dry-run
python execution/codesec_scan.py --full
python execution/codesec_scan.py --stats
```

---

## CSR Lifecycle

```
1. DETECTED      → Finding found during scan
2. GENERATED     → CSR YAML written to .tmp/codesec/reports/
3. PRESENTED     → Shown to Sabbo in CodeSec Report or on request
4. REVIEWED      → Sabbo reads full CSR details
5a. APPROVED     → Fix applied to target file, status → "applied", logged to CHANGELOG
5b. REJECTED     → Status → "rejected", reason stored
5c. ACKNOWLEDGED → Sabbo marks as accepted risk (won't re-flag)
```

---

## Security Check Rules

### SEC-001: Hardcoded API Keys/Tokens
- **Pattern:** Regex matching `sk-`, `ghp_`, `xox[bsp]-`, `AIza`, `AKIA`, base64 tokens, password assignments
- **Excludes:** .env files (those are expected to contain keys)
- **Severity:** CRITICAL

### SEC-002: SQL Injection
- **Pattern:** f-string or .format() inside SQL query strings, execute() with f-strings
- **Severity:** HIGH

### SEC-003: Command Injection
- **Pattern:** subprocess with shell=True using variables; os.system/os.popen with f-strings
- **Severity:** HIGH

### SEC-004: Insecure Deserialization
- **Pattern:** pickle.load, yaml.load without Loader=SafeLoader
- **Severity:** MEDIUM

### SEC-005: Path Traversal
- **Pattern:** User/external input concatenated into file paths without validation
- **Severity:** HIGH

### SEC-006: SSRF
- **Pattern:** requests.get/post with variable URLs without allowlist
- **Severity:** MEDIUM

### SEC-007: Debug Leftovers
- **Pattern:** debug=True in production, print(password), print(api_key)
- **Severity:** LOW

### SEC-008: Insecure File Permissions
- **Pattern:** os.chmod with 0o777, world-writable
- **Severity:** MEDIUM

### SEC-009: Credential Logging
- **Pattern:** logging calls with password/key/token/secret variables
- **Severity:** HIGH

### SEC-010: Weak Crypto
- **Pattern:** hashlib.md5, hashlib.sha1 used for security
- **Severity:** MEDIUM

---

## Code Quality Rules

### CQ-001: Bare Except Clauses
- **Pattern:** `except:` without specific exception type
- **Fix:** `except Exception as e:`

### CQ-002: Unused Imports
- **Pattern:** Imported names not referenced in file body
- **Fix:** Remove unused import

### CQ-003: Mutable Default Arguments
- **Pattern:** `def f(x=[])` or `def f(x={})`
- **Fix:** `def f(x=None): x = x or []`

### CQ-004: Missing Error Handling
- **Pattern:** requests.get/post, open(), subprocess.run without try/except
- **Fix:** Wrap in try/except with appropriate error handling

### CQ-005: Hardcoded Paths
- **Pattern:** Absolute `/Users/` paths not using PROJECT_ROOT or os.environ
- **Fix:** Use `PROJECT_ROOT / "subpath"` or `os.environ.get()`

### CQ-006: Missing Input Validation
- **Pattern:** Functions taking external input without type/bounds checks
- **Fix:** Add validation at function entry

### CQ-007: Resource Leaks
- **Pattern:** `open()` without context manager (`with` statement)
- **Fix:** Use `with open(...) as f:`

---

## Infrastructure Rules

### INF-001: Script Importability
- **Check:** py_compile.compile() every .py in execution/
- **On fail:** Report syntax error with line number

### INF-002: Directive-Script References
- **Check:** Regex `execution/\w+\.py` in directives/*.md, verify file exists
- **On fail:** Report broken reference

### INF-003: Agent Path References
- **Check:** File paths in SabboOS/Agents/*.md exist on disk
- **On fail:** Report missing path

### INF-004: .env Required Keys
- **Check:** ANTHROPIC_API_KEY exists in .env (NEVER log value)
- **On fail:** CRITICAL — key missing

### INF-005: Launchd Daemons
- **Check:** `launchctl list | grep com.sabbo`
- **Expected:** inbox-watcher, training-officer-scan, training-officer-watch, codesec-watch, codesec-scan
- **On fail:** Report daemon not loaded with restart command

### INF-006: Brain.md Writable
- **Check:** /Users/Shared/antigravity/memory/ceo/brain.md exists and os.access(W_OK)
- **On fail:** Report permission issue

### INF-007: Bridge Directories
- **Check:** /Users/Shared/antigravity/{inbox,outbox,memory,proposals} exist and writable
- **On fail:** Report missing/inaccessible directory

### INF-008: Venv Health
- **Check:** .venv/ exists, .venv/bin/python3 accessible
- **On fail:** Report broken venv

---

## Integration with Other Agents

### → Training Officer
When a CSR finding suggests an agent generated insecure code:
```
If CSR.target_file in SCRIPT_AGENT_MAP:
  agent = SCRIPT_AGENT_MAP[CSR.target_file]
  → Add to brain.md → Training Officer Queue:
     "CodeSec found {severity} issue in {script} (owned by {agent}): {title}"
```

### → CEO Brain
For CRITICAL/HIGH findings:
```
Append to brain.md → System State:
  "CodeSec [{severity}]: {title} in {target_file} — CSR-{id} pending review"
```

### → CHANGELOG
When a CSR is approved and applied:
```
Append to SabboOS/CHANGELOG.md:
  "{date} | {target_file} | CodeSec fix applied: {title} (CSR-{id})"
```

---

## Always-On Operation

### fswatch Daemon
- **Script:** `execution/codesec_watch.sh`
- **Launchd:** `~/Library/LaunchAgents/com.sabbo.codesec-watch.plist`
- **Behavior:** Watches monitored dirs, triggers scan on file changes, 120s cooldown
- **Log:** `.tmp/codesec/watch.log`

### Scheduled Daily Scan
- **Launchd:** `~/Library/LaunchAgents/com.sabbo.codesec-scan.plist`
- **Schedule:** Daily at 8:00 AM
- **Mode:** `--full` (scans everything, ignores change detection)

---

*CodeSec SOP v1.0 — 2026-02-22*
*Every change gets scanned. Every finding gets reported. The code stays clean.*
