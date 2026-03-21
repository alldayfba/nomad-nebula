# Knowledge Ingestion SOP

## Purpose
Add any business document (SOP, brand guide, style doc, email template, swipe file) to the agent memory system so all Claude Code and OpenClaw agents can reference it when doing fulfillment work.

## Trigger
Run whenever you have a new document that agents should know about — a new SOP, a client framework, a copywriting swipe file, a competitor teardown, anything.

## Inputs
- The document in any of these formats: `.md`, `.txt`, `.pdf`

## Steps

### Option A: Quick Drop (Recommended)
1. Copy the file to `/Users/Shared/antigravity/memory/uploads/`
2. Run: `python execution/ingest_docs.py`
3. Done — the doc is automatically routed to the right memory bucket and appended to `references.md`

### Option B: Specific File
```bash
python execution/ingest_docs.py --file /path/to/your/doc.md
```

### Option C: Auto-Watch Mode (Continuous)
```bash
python execution/ingest_docs.py --watch
```
Runs in background — any file dropped in `uploads/` is processed immediately.

## How Routing Works
The script detects which memory bucket the doc belongs to based on keywords:
- **agency/** — docs mentioning agency, growth, retainer, ads, funnel, client, CAC, LTV
- **amazon/** — docs mentioning Amazon, FBA, PPC, ACOS, product research, supplier
- **global/** — everything else (applies across all projects)

If the auto-detection is wrong, move the resulting entry manually in the `references.md` file.

## Outputs
- Doc content appended to `/Users/Shared/antigravity/memory/<bucket>/references.md`
- Original file moved to `uploads/processed/` as archive

## What to Upload
| Document type | Example | Bucket |
|---------------|---------|--------|
| Brand voice guide | "How we write emails" | agency or amazon |
| Copywriting swipe file | Winning ad copy examples | agency or amazon |
| Client SOP | Onboarding checklist | agency |
| Email templates | VSL follow-up sequence | agency or amazon |
| Framework doc | The 5-Phase System explained | amazon |
| Competitor teardown | Analysis of competitor LP | agency or amazon |
| Prompt library | Proven Claude prompts | global |
| Style guide | Tone, voice, formatting rules | global |

## After Ingesting
No restart needed. Agents load memory files fresh on each task — they'll see the new content immediately.

To verify ingestion worked: open `/Users/Shared/antigravity/memory/<bucket>/references.md` and confirm the new section appears at the bottom.

## Known Issues & Warnings
- PDFs require `pypdf` installed: `pip install pypdf`
- Very large docs (>50K tokens) should be manually summarized before uploading — the script takes the first 3000 chars as a preview
- If a doc covers multiple topics, split it into separate files for cleaner routing

## Last Updated
2026-02-20
