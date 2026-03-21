# Video Editor — SOP

**Layer:** Directive
**Script:** `execution/video_editor.py`
**Helpers:** `execution/video_caption_renderer.py`, `execution/video_overlay_templates.py`, `execution/video_manifest_builder.py`
**Last Updated:** 2026-03-17

---

## Purpose

Programmatic video editing engine for producing high-converting YouTube content,
short-form reels, and polished video deliverables. No paid software — FFmpeg +
PyAV + Pillow + OpenCV + faster-whisper.

---

## When To Use

| User Says | Action |
|---|---|
| "edit this video" | Build manifest from instructions, render |
| "add captions" | Run captions subcommand → auto-generate word-level captions |
| "auto-edit this video" | Run auto-edit (AI detects boring parts, adds zooms/captions) |
| "make a YouTube short from this" | Smart reframe 16:9 → 9:16 + captions |
| "color grade this" | Apply color preset or LUT |
| "add b-roll here" | Insert B-roll clip at timestamp with transition |
| "generate chapters" | Transcribe → chapter markers |
| "extract thumbnail" | Pull best thumbnail candidates |

---

## How It Works

### Architecture: Manifest-Driven Rendering

1. User describes edits in natural language
2. Agent translates to a JSON edit manifest
3. `video_editor.py render --manifest <path>` executes deterministically
4. Output goes to `.tmp/video-edits/<project>/`

### Rendering Pipeline

1. Validate manifest + probe all source files (ffprobe)
2. Generate text overlay frames (Pillow → PNG sequences)
3. Cut/speed-adjust timeline segments
4. Apply per-segment effects (zoom, ken burns, fade)
5. Join segments with xfade transitions
6. Composite overlay tracks (captions, lower thirds, subscribe btn)
7. Apply global color grade (eq + colorbalance or LUT)
8. Mix audio (speech + music ducking + SFX + normalize)
9. Final encode (H.264 VideoToolbox HW accel, -14 LUFS)
10. Cleanup intermediates

### CRITICAL: No drawtext in FFmpeg

This FFmpeg build lacks libfreetype/libass. All text is rendered via Pillow
as RGBA PNG frames, then overlaid. This gives us:
- Any TrueType/OpenType font
- Anti-aliased text with outlines, shadows, gradients
- Word-by-word highlighting (CapCut style)
- Animated text (scale, fade, slide)

---

## Execution Commands

### Full render from manifest
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/video_editor.py render --manifest .tmp/video-edits/project.json
```

### Auto-generate captions
```bash
python execution/video_editor.py captions --input video.mp4 --style capcut_pop
```

### AI auto-edit
```bash
python execution/video_editor.py auto-edit --input video.mp4 --style youtube_engaging
```

### YouTube optimization
```bash
python execution/video_editor.py youtube-optimize --input video.mp4
```

### Color grade only
```bash
python execution/video_editor.py color-grade --input video.mp4 --preset warm_cinematic
```

### Smart reframe
```bash
python execution/video_editor.py reframe --input video.mp4 --ratio 9:16
```

### Quick preview
```bash
python execution/video_editor.py preview --manifest project.json --duration 10
```

### Build manifest from simple instructions
```bash
python execution/video_manifest_builder.py --input video.mp4 \
  --cuts "0:00-1:30, 3:00-5:15" --captions auto --color-grade warm_cinematic
```

---

## Output Format

- Rendered video: `.tmp/video-edits/<project>/output.mp4`
- Captions JSON: `.tmp/video-edits/<project>/captions.json`
- Thumbnails: `.tmp/video-edits/<project>/thumbnails/`
- Chapters: `.tmp/video-edits/<project>/chapters.txt`
- Manifest: `.tmp/video-edits/<project>/manifest.json`

---

## Color Grade Presets

| Preset | Look | Best For |
|---|---|---|
| warm_cinematic | Orange highlights, lifted blacks | Talking head, coaching |
| cool_moody | Blue shadows, desaturated | Tech, dramatic |
| vibrant | High saturation, punchy | Product demos |
| desaturated | Low sat, high contrast | Premium editorial |
| orange_teal | Orange skin, teal shadows | YouTube standard |

---

## Caption Styles

| Style | Description |
|---|---|
| capcut_pop | Active word scales 120%, gold highlight, white + black stroke |
| subtitle_bar | Dark semi-transparent bar at bottom |
| karaoke | Color fill sweeps per word |
| minimal | White text, subtle shadow |
| bold_outline | Large text, thick stroke |

---

## Integration

| System | Connection |
|---|---|
| faster-whisper | Speech → word-level timestamps |
| yt-dlp | Download source videos |
| Content Engine | Content briefs |
| MediaBuyer | Ad creative output |

---

## Self-Annealing

If execution fails:
1. Check FFmpeg is in PATH: `which ffmpeg`
2. Check deps: `python -c "from PIL import Image; import cv2"`
3. If codec error → fall back to libx264 from videotoolbox
4. If memory error → segment-based rendering
5. If font not found → fall back to Helvetica
6. Update Known Issues section
7. Log fix in SabboOS/CHANGELOG.md

---

## Edge Cases

- **Very long videos (>1hr):** Segment in 10-min chunks
- **No audio track:** Skip audio mixing
- **Variable framerate:** Force CFR with fps filter
- **Portrait source for landscape:** Blur-padded background

---

## Known Issues

*(none yet — will self-anneal)*

---

## YouTube Video Assembly

### The `assemble` Command

Full multi-source YouTube video assembly from a project config JSON.

```bash
# Full assembly
python execution/video_assembler.py --config project-config.json

# Preview single section
python execution/video_assembler.py --config project-config.json --preview-section hook

# Skip slow steps
python execution/video_assembler.py --config project-config.json --skip-captions --skip-motion-graphics
```

Also available via: `python execution/video_editor.py assemble --config project-config.json`

### Project Config Schema

JSON file mapping source clips → sections with layout instructions:

- **`sources`**: Named video/audio files
- **`sections`**: Array of section configs, each with:
  - `layout`: `fullscreen_facecam` or `pip_screenshare`
  - `source` / `facecam_source` + `screen_source`: Source references
  - `trim` / `facecam_trim` + `screen_trim`: In/out timestamps
  - `pip`: Position, scale (0.28 = 28%), margin, border width
  - `motion_graphics`: Remotion compositions with props + timing
  - `lower_third`: Name/title overlay
  - `transition_out`: Fade or chapter transition
- **`captions`**: Style (capcut_pop default), Whisper model
- **`color_grade`**: Preset name
- **`audio_mix`**: Normalize, LUFS target, music path/volume
- **`sfx`**: Auto-sync from overlay/transition events

### PiP Layout

Screen share fills the frame. Face cam is composited at:
- Scale: 28% of frame (538x302 at 1080p)
- Position: bottom_left (30px margin)
- Border: 3px black
- Audio: Always from face cam (the speaker)

### Assembly Pipeline

1. Parse config + validate sources
2. Render each section (fullscreen or PiP)
3. Concat all sections
4. Render + overlay Remotion motion graphics
5. Apply color grade
6. Transcribe + overlay captions
7. Mix audio (normalize + SFX + optional music)
8. Final output

### Workflow

1. Film clips (face cam + screen recording)
2. Write project-config.json mapping clips to script sections
3. Preview individual sections with `--preview-section`
4. Run full assembly
5. Review and adjust trim points as needed
