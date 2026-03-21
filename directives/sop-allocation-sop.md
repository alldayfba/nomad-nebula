# SOP Allocation SOP
> directives/sop-allocation-sop.md | Version 1.0

---

## Purpose

This SOP documents how to ingest new training materials, SOPs, and business documents into the multi-agent system so they automatically improve every agent's output quality.

The key insight: **the more you feed the system, the better every agent performs.** Every SOP, info product, framework, or transcript you upload becomes training material that the relevant agent references on every task.

---

## When to Use This

- You've bought a new course or info product (Jeremy Haynes, Daniel Fazio, Ben Heath, etc.)
- You've written a new SOP and want agents to follow it
- You have transcripts, recordings, or notes you want agents to learn from
- You want to add client-specific training material

---

## Step-by-Step

### Step 1 — Prepare Your Files

Supported formats: `.md`, `.txt`, `.pdf`

For best results:
- Convert Word docs / Google Docs → `.txt` (copy/paste or download as plain text)
- For PDFs: make sure text is selectable (not a scanned image)
- For transcripts: save as `.txt` — no need to clean them up, Claude handles it

### Step 2 — Drop Into the Upload Folder

```bash
# The drop folder:
/Users/Shared/antigravity/memory/uploads/
```

You can drag-and-drop any number of files at once. There's no limit.

### Step 3 — Run the Allocator

```bash
cd /Users/sabbojb/.gemini/antigravity/playground/nomad-nebula
source .venv/bin/activate
python execution/allocate_sops.py
```

The script will:
1. Read each file
2. Ask Claude Haiku (fast + cheap) to classify the domain
3. Route each file to the correct agent's `skills.md`
4. Archive the original to `uploads/processed/`
5. Print a receipt showing exactly where each file went

### Step 4 — Review the Receipt

The script prints an allocation summary:
```
ALLOCATION RECEIPT — 2026-02-20 09:14
────────────────────────────────────────────────────────────
  Processed: 6 files
  Allocated: 6
  Skipped:   0

  Routing summary:
    ads-copy-agent (ads): 2 file(s)
    ads-copy-agent (copywriting): 1 file(s)
    outreach-agent (outreach): 2 file(s)
    content-agent (vsl): 1 file(s)
────────────────────────────────────────────────────────────
```

If anything looks wrong, you can manually move a reference in the target `skills.md`.

### Step 5 (Optional) — Update Agent Skills in Claude Code

After allocation, tell the CEO agent or doe-director:
> "Update agent skills with new SOPs"

This triggers `doe-director` to review what was allocated and ensure each agent's skills map references the new material correctly.

---

## Domain Classification Map

The allocator uses Claude to classify files into these domains:

| Domain Tag | Routes to | Examples |
|---|---|---|
| `ads` | ads-copy-agent | Meta ads SOPs, Facebook ad strategies, YouTube ads, creative testing |
| `copywriting` | ads-copy-agent | Direct response copy, persuasion frameworks, AIDA, storytelling |
| `vsl` | content-agent | VSL scripting, video sales letter structure |
| `funnel` | content-agent | Landing page copy, funnel optimization, conversion |
| `content` | content-agent | Organic content strategy, social media, YouTube, TikTok |
| `lead-gen` | lead-gen-agent | Lead scraping, prospecting, database building |
| `outreach` | outreach-agent | Cold email, DM scripts, Dream 100, personalized outreach |
| `sales` | outreach-agent | Sales calls, objection handling, discovery calls |
| `closing` | outreach-agent | Closing techniques, proposals, contracts |
| `amazon` | amazon-agent | Amazon FBA, product research, listing optimization |
| `fba` | amazon-agent | FBA logistics, suppliers, inventory |
| `fulfillment` | amazon-agent | Program delivery, student success, coaching |
| `coaching` | amazon-agent | Coaching methodology, curriculum design |
| `general` | CEO (global) | General business strategy, mindset, broad marketing |

---

## Dry Run (Preview Without Writing)

To see what would happen without making any changes:
```bash
python execution/allocate_sops.py --dry-run
```

To preview a single file:
```bash
python execution/allocate_sops.py --file /path/to/your-file.pdf --dry-run
```

---

## Processing a Specific File

```bash
python execution/allocate_sops.py --file /Users/sabbojb/Downloads/jeremy-haynes-ads.pdf
```

---

## Where Files Go After Allocation

Each agent's skills map gets a reference entry appended:
- `bots/ads-copy/skills.md` — ads + copywriting domain
- `bots/content/skills.md` — vsl + funnel + content domain
- `bots/outreach/skills.md` — outreach + sales + closing domain
- `/Users/Shared/antigravity/memory/amazon/references.md` — amazon + fba + coaching domain
- `/Users/Shared/antigravity/memory/global/references.md` — general domain

Original files are archived to: `uploads/processed/`

---

## Known Limitations

- PDFs with scanned images (not selectable text) will be skipped — convert to text first
- Very long documents (100k+ words) are classified on the first 4,000 chars — make sure the opening is representative
- If a file is genuinely ambiguous, it defaults to `general` (global memory). You can manually move it.

---

## Self-Annealing Note

If the classifier routes something incorrectly, manually edit the reference in the skills.md file to move it to the right section. Then update this SOP's domain classification table if it reveals a pattern — so future files of that type get routed correctly.

---

*SOP Allocation v1.0 — 2026-02-20*
