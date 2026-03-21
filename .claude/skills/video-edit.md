---
name: video-edit
description: Edit videos programmatically — cuts, captions, transitions, color grading, motion graphics, audio mixing
trigger: when user says "edit video", "add captions", "auto-edit", "color grade", "make a short", "video editor", "reframe video", "youtube optimize", "make clips", "repurpose", "generate thumbnail", "create shorts", "motion graphics", "add title card", "make it premium", "add animations"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Video Editor

## Directive
Read `directives/video-editing-sop.md` for the editing SOP.
Read `directives/youtube-foundations-sop.md` for YouTube strategy (thumbnails, hooks, scripting).

## Goal
Edit videos programmatically using FFmpeg, PyAV, Pillow, and faster-whisper. Translate natural language editing instructions into a JSON manifest, then render deterministically.

## Inputs
| Input | Required | Default |
|---|---|---|
| input video path or URL | Yes | — |
| editing instructions | Yes | — (natural language) |
| output format | No | mp4 (H.264) |
| caption style | No | capcut_pop |
| color preset | No | none |

## Execution

### Auto-edit (most common)
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py auto-edit --input "{input}" --style youtube_engaging
```

### Full manifest render
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py render --manifest "{manifest_path}"
```

### Captions only
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py captions --input "{input}" --style {style}
```

### YouTube optimization
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py youtube-optimize --input "{input}"
```

### Extract clips for Shorts/Reels (long-form → short-form)
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py clips --input "{input}" --count 5 --reframe --captions
```

### Generate thumbnail
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py thumbnail --input "{input}" --text "{title}" --template bold_text --highlight "{key_words}"
```

### Render motion graphics (Remotion)
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py motion-graphics --template TitleSequence --props '{"title":"Your Title","subtitle":"Subtitle"}'
```

Available templates: TitleSequence, RevenueChart, BlueprintOverview, TestimonialCard, ChapterTransition, EndScreen

## Workflow

1. If user provides a YouTube URL → download with yt-dlp first
2. If instructions are vague → reverse-prompt for specifics
3. Build manifest JSON (or use auto-edit for AI-driven defaults)
4. Render via video_editor.py
5. Preview first 10s if user wants to iterate
6. Final render at full quality

## Output
- Rendered video at `.tmp/video-edits/<project>/output.mp4`
- Captions, thumbnails, chapters as side outputs

## Self-Annealing
If execution fails:
1. Check dependencies: `python -c "from PIL import Image; import cv2; import av"`
2. Fall back to libx264 if videotoolbox fails
3. Fix the script, update directive Known Issues
4. Log fix in `SabboOS/CHANGELOG.md`
