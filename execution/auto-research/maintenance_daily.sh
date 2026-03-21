#!/bin/bash
# Daily memory maintenance + brain.md export
# Triggered by launchd: com.sabbo.memory-maintenance
cd /Users/Shared/antigravity/projects/nomad-nebula
export PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula
python3 execution/memory_maintenance.py >> /tmp/memory-maintenance.log 2>&1
python3 execution/memory_export.py --output /Users/Shared/antigravity/memory/ceo/brain.md >> /tmp/memory-maintenance.log 2>&1
echo "$(date): maintenance complete" >> /tmp/memory-maintenance.log
