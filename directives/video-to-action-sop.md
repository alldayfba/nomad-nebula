# Video-to-Action Pipeline SOP
> directives/video-to-action-sop.md | Version 1.0

---

## Purpose

Extract structured, actionable implementation tasks from YouTube videos. Goes beyond summaries — produces specific steps, file paths, priorities, and dependencies that can feed directly into a task queue.

---

## When to Use

- Sabbo shares a YouTube link and says "implement this"
- Creator research: extracting frameworks from creator videos
- Course content: breaking training videos into actionable steps
- Competitor analysis: understanding competitor strategies from their content

---

## How It Works

1. **Input:** YouTube URL or transcript file
2. **Extract:** Pull transcript via yt-dlp (auto-subtitles)
3. **Chunk:** Split long transcripts into processable chunks (~30K chars)
4. **Analyze:** Claude extracts techniques with timestamps, steps, files, priority
5. **Synthesize:** Merge chunks into unified action list
6. **Output:** JSON + Markdown files in `.tmp/video-actions/`

---

## Execution

```bash
# From YouTube URL
python execution/video_to_action.py \
    --url "https://www.youtube.com/watch?v=VIDEO_ID" \
    --context "Agency OS (growth agency), Amazon OS (FBA coaching)"

# From existing transcript
python execution/video_to_action.py \
    --transcript .tmp/creators/nick-saraev/videos/video_transcript.txt \
    --context "AI agent orchestration patterns"

# With multimodal frame extraction (requires Gemini API key)
python execution/video_to_action.py \
    --url "https://www.youtube.com/watch?v=VIDEO_ID" \
    --multimodal \
    --context "AI agents"
```

---

## Output Format

### JSON (`.tmp/video-actions/actions_YYYYMMDD_HHMMSS.json`)
```json
{
  "techniques": [
    {
      "name": "Self-Modifying Instructions",
      "timestamp": "00:25:00",
      "summary": "Auto-append rules to CLAUDE.md when errors occur",
      "implementation_steps": ["Step 1: Add ## Learned Rules section", "..."],
      "files_to_create": ["execution/append_learned_rule.py"],
      "files_to_modify": [".claude/CLAUDE.md"],
      "priority": "high",
      "dependencies": []
    }
  ]
}
```

### Markdown (`.tmp/video-actions/actions_YYYYMMDD_HHMMSS.md`)
Human-readable version with headers per technique.

---

## Integration

- **Training Officer:** High-priority techniques can be converted to Training Proposals
- **CEO Brain:** New techniques logged to brain.md → Asset Registry
- **Creator Brains:** If video is from a tracked creator, update their brain file
- **Task Queue:** Action items can feed directly into session tasks

---

## Relationship to build_implementation_notes.py

`build_implementation_notes.py` (existing) synthesizes themes across multiple creator videos.
`video_to_action.py` (this) extracts granular action items from a single video.

Use `video_to_action.py` when you need specific implementation steps.
Use `build_implementation_notes.py` when you need a thematic overview across many videos.
