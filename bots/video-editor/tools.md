# VideoEditor Bot — Tools
> bots/video-editor/tools.md | Version 1.0

---

## Access Policy

Least privilege. All access scoped to video editing operations.

---

## Scripts

| Script | Purpose | Access |
|---|---|---|
| `execution/video_editor.py` | Core rendering engine | Read/Write |
| `execution/video_caption_renderer.py` | Text frame generation | Read/Write |
| `execution/video_overlay_templates.py` | Motion graphic templates | Read |
| `execution/video_manifest_builder.py` | Manifest conversion | Read/Write |

---

## External Tools

| Tool | Purpose |
|---|---|
| `ffmpeg` / `ffprobe` | Video processing + probing |
| `yt-dlp` | YouTube download |
| `faster-whisper` | Speech-to-text |

---

## File System Access

| Path | Access |
|---|---|
| `bots/video-editor/` | Read/Write |
| `.tmp/video-edits/` | Read/Write |
| `directives/` | Read |
| `SabboOS/` | Read + CHANGELOG append |

---

## Cannot Access

- Cloud uploads (Google Drive, YouTube)
- Other bots' config files
- Credentials or API keys
- Payment processors
- Student data

---

## Resource Limits

- Max .tmp/video-edits/ disk: 50GB
- Max single render source: 2hr video
- HW encoding preferred, software fallback automatic

---

### video_assembler.py
- **Purpose:** YouTube video assembly orchestrator
- **Access:** Full (core tool)
- **CLI:** `python execution/video_assembler.py --config <json> [--preview-section <id>] [--skip-captions] [--skip-motion-graphics]`
- **Dependencies:** video_editor.py, video_caption_renderer.py, remotion_renderer.py, sfx_library.py

---

*VideoEditor Bot Tools v1.0 — 2026-03-17*
