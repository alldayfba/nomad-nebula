# VideoEditor Bot — Skills
> bots/video-editor/skills.md | Version 1.0

---

## Full Render
**Trigger:** "edit video", "render this"
**Script:** `python execution/video_editor.py render --manifest <path>`
**Output:** Rendered MP4 in .tmp/video-edits/<project>/

---

## Auto Captions
**Trigger:** "add captions", "caption this"
**Script:** `python execution/video_editor.py captions --input <path> --style <style>`
**Output:** Captioned video + captions.json

---

## Auto-Edit
**Trigger:** "auto-edit", "make this look good"
**Script:** `python execution/video_editor.py auto-edit --input <path> --style youtube_engaging`
**Output:** Fully edited video with captions, zooms, color grade

---

## Color Grade
**Trigger:** "color grade", "make it cinematic"
**Script:** `python execution/video_editor.py color-grade --input <path> --preset <preset>`
**Presets:** warm_cinematic, cool_moody, vibrant, desaturated, orange_teal

---

## Smart Reframe
**Trigger:** "make a short", "reframe to vertical", "9:16"
**Script:** `python execution/video_editor.py reframe --input <path> --ratio 9:16`
**Output:** Vertical video with face-tracked cropping

---

## YouTube Optimize
**Trigger:** "optimize for youtube", "generate chapters", "extract thumbnail"
**Script:** `python execution/video_editor.py youtube-optimize --input <path>`
**Output:** chapters.txt, thumbnails, hook analysis, pattern interrupts

---

## Preview
**Trigger:** "preview this edit"
**Script:** `python execution/video_editor.py preview --manifest <path> --duration 10`
**Output:** Quick 10s preview

---

## Manifest Build
**Trigger:** "build edit manifest"
**Script:** `python execution/video_manifest_builder.py --input <path> --cuts "<timestamps>"`
**Output:** manifest.json

---

### 9. YouTube Video Assembly
- **Trigger:** "assemble video", "put this video together", "edit my YouTube video"
- **Script:** `execution/video_assembler.py`
- **Input:** Project config JSON with source clips, section layouts, motion graphics
- **Output:** Fully assembled YouTube video with PiP, captions, color grade, SFX
- **Layouts:** fullscreen_facecam, pip_screenshare (face cam bottom-left at 28%)
