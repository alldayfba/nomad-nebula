---
name: memory
description: Search, browse, and manage the persistent memory system (SQLite + FTS5)
trigger: when user says "remember", "what do you know about", "forget", "recall", "memory", "search memory"
tools: [Bash, Read]
---

# Memory System

## Overview
SQLite-backed memory with FTS5 BM25 ranked search. DB at `/Users/Shared/antigravity/memory/ceo/memory.db`.

All commands require: `PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula`

## Commands

### Search
```bash
python3 execution/memory_recall.py --query "<query>" --limit 5 -v
python3 execution/memory_recall.py --query "<name>" --type person -v
python3 execution/memory_recall.py --query "<topic>" --type decision,learning -v
```

### Browse Recent
```bash
python3 execution/memory_recall.py --recent --days 7 -v
python3 execution/memory_recall.py --category sourcing --limit 10 -v
```

### Add Memory
```bash
python3 execution/memory_store.py add --type <type> --category <cat> --title "<title>" --content "<content>" --tags "<tags>"
```
Types: decision, learning, preference, event, asset, person, error, correction, idea
Categories: agency, amazon, sourcing, sales, content, technical, agent, client, student, general

### Update Existing
```bash
python3 execution/memory_store.py update --search "<what to find>" --content "<new info>" --reason "<why>"
```

### Forget / Delete
```bash
python3 execution/memory_store.py delete --id <id>
```

### Stats
```bash
python3 execution/memory_store.py stats
```

### Health Check
```bash
python3 execution/memory_maintenance.py --check
```

### Export brain.md
```bash
python3 execution/memory_export.py --output /Users/Shared/antigravity/memory/ceo/brain.md
```

### Boot Context (session start)
```bash
python3 execution/memory_boot.py
```

## Workflow
1. User asks "what do you know about X" → run `memory_recall.py --query "X" -v`
2. User asks "remember that X" → run `memory_store.py add ...`
3. User asks "forget X" → search first, then delete by ID
4. User asks "how's the memory system" → run `memory_store.py stats` + `memory_maintenance.py --check`
