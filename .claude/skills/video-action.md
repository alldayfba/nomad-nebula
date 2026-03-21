---
name: video-action
description: Extract structured implementation tasks from a YouTube video
trigger: when user says "implement this video", "action items from video", "extract from youtube", "what should we build from this"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Video-to-Action Pipeline

## Directive
Read `directives/video-to-action-sop.md` for the full SOP before proceeding.

## Goal
Take a YouTube video URL or transcript, extract every actionable technique with timestamps, implementation steps, file paths, and priorities.

## Inputs
| Input | Required | Default |
|---|---|---|
| url | Yes* | — (YouTube URL) |
| transcript | Yes* | — (path to transcript file, alternative to URL) |
| context | No | `"Agency OS (growth agency) + Amazon OS (FBA coaching)"` |

*One of url or transcript is required.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_to_action.py --url "{url}" --context "{context}"
```

From transcript:
```bash
python execution/video_to_action.py --transcript "{transcript_path}" --context "{context}"
```

## Output
- JSON: `.tmp/video-actions/actions_YYYYMMDD_HHMMSS.json` — structured techniques with steps
- Markdown: `.tmp/video-actions/actions_YYYYMMDD_HHMMSS.md` — human-readable version
- Console: technique list with priorities and step previews

## Next Steps
After extraction, offer to:
1. Create tasks from the high-priority techniques
2. Feed techniques into Training Officer as proposals
3. Update relevant creator brain file if video is from a tracked creator

## Self-Annealing
If execution fails:
1. If yt-dlp fails → check `yt-dlp` is installed, try `pip install yt-dlp`
2. If transcript is empty → video may not have captions, ask user for manual transcript
3. If JSON parse fails → raw text is still saved, extract manually
4. Fix the script, update `directives/video-to-action-sop.md`
5. Log fix in `SabboOS/CHANGELOG.md`
