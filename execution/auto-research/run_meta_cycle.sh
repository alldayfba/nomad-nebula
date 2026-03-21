#!/bin/bash
# Run one meta-cycle of all auto-research optimizers
# Triggered by launchd: com.sabbo.auto-research
cd /Users/Shared/antigravity/projects/nomad-nebula
export PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula
LOG="/tmp/auto-research.log"
echo "$(date): Starting meta cycle" >> "$LOG"
python3 execution/auto-research/meta_orchestrator.py >> "$LOG" 2>&1
echo "$(date): Meta cycle complete" >> "$LOG"
echo "---" >> "$LOG"
