"""Claude CLI Proxy — routes Anthropic API requests through claude CLI (uses Max plan).

Mimics the Anthropic Messages API at localhost:5055/v1/messages.
Translates requests into claude --print calls, returns Anthropic-format responses.
Supports vision/images by saving base64 images to temp files and using --tools "Read".

Usage:
    python execution/claude_cli_proxy.py          # Start proxy on port 5055
    python execution/claude_cli_proxy.py --port 5060  # Custom port
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import subprocess
import time
import uuid

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# Clean directory with no CLAUDE.md files
CLEAN_CWD = "/tmp/claude-proxy-workspace"
IMAGE_DIR = os.path.join(CLEAN_CWD, "images")
os.makedirs(CLEAN_CWD, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)


def _format_prompt(messages: list[dict]) -> tuple[str, list[str]]:
    """Convert Anthropic messages into a single prompt + list of saved image paths."""
    parts = []
    image_paths = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block["text"])
                elif isinstance(block, dict) and block.get("type") == "image":
                    # Save base64 image to temp file for claude Read tool
                    source = block.get("source", {})
                    if source.get("type") == "base64":
                        media = source.get("media_type", "image/png")
                        ext = media.split("/")[-1].replace("jpeg", "jpg")
                        img_id = uuid.uuid4().hex[:8]
                        path = os.path.join(IMAGE_DIR, f"img_{img_id}.{ext}")
                        try:
                            with open(path, "wb") as f:
                                f.write(base64.b64decode(source["data"]))
                            image_paths.append(path)
                        except Exception as e:
                            print(f"[proxy] Failed to save image: {e}")
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    # Pass through tool use blocks as text context
                    text_parts.append(f"[Tool call: {block.get('name', 'unknown')}]")
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    text_parts.append(f"[Tool result: {block.get('content', '')}]")
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)

        if role == "assistant":
            parts.append(f"[Assistant previously said]: {content}")
        else:
            parts.append(content)

    return "\n\n".join(parts), image_paths


def _cleanup_images(image_paths: list[str]):
    """Delete temp image files after processing."""
    for p in image_paths:
        try:
            os.remove(p)
        except Exception:
            pass


def _call_claude_cli(system: str, prompt: str, max_tokens: int = 2048,
                     image_paths: list[str] | None = None) -> str:
    """Call claude CLI with --print flag. Uses Read tool for images."""
    has_images = bool(image_paths)

    # Enable Read tool when images are present so Claude can see them
    tools = "Read" if has_images else ""

    # Prepend image read instructions to the prompt
    if has_images:
        img_lines = "\n".join(f"- {p}" for p in image_paths)
        prompt = (
            f"I've attached {len(image_paths)} image(s) for you to analyze. "
            f"Read each image file below:\n{img_lines}\n\n"
            f"Now respond to this:\n{prompt}"
        )

    cmd = [
        "claude",
        "--print",
        "--tools", tools,
        "--disable-slash-commands",
        "-p", prompt,
    ]

    if system:
        cmd.extend(["--system-prompt", system])

    # Strip CLAUDECODE env var to allow nested CLI calls
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=CLEAN_CWD,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:500]}")

    output = result.stdout.strip()

    # Strip any Claude Code status line leaked from CLAUDE.md instructions
    lines = output.split("\n")
    cleaned = []
    for line in lines:
        if line.strip().startswith("~$") and "active" in line and "queued" in line:
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


@app.route("/v1/messages", methods=["POST"])
def messages():
    """Handle Anthropic Messages API requests (text + vision)."""
    data = request.get_json()

    system = data.get("system", "")
    messages_list = data.get("messages", [])
    max_tokens = data.get("max_tokens", 2048)
    model = data.get("model", "claude-haiku-4-5-20251001")

    prompt, image_paths = _format_prompt(messages_list)

    if image_paths:
        print(f"[proxy] Vision request: {len(image_paths)} image(s)")

    try:
        response_text = _call_claude_cli(system, prompt, max_tokens, image_paths)
    except subprocess.TimeoutExpired:
        _cleanup_images(image_paths)
        return jsonify({"error": {"type": "timeout", "message": "CLI timed out"}}), 504
    except RuntimeError as e:
        _cleanup_images(image_paths)
        return jsonify({"error": {"type": "cli_error", "message": str(e)}}), 502
    finally:
        _cleanup_images(image_paths)

    # Build Anthropic-compatible response
    input_tokens = _estimate_tokens(prompt)
    output_tokens = _estimate_tokens(response_text)

    response = {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": response_text}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }

    return jsonify(response)


@app.route("/v1/messages", methods=["OPTIONS"])
def messages_options():
    """CORS preflight."""
    return Response(status=200, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, x-api-key, anthropic-version",
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        cli_ok = result.returncode == 0
        cli_version = result.stdout.strip() if cli_ok else result.stderr.strip()
    except Exception as e:
        cli_ok = False
        cli_version = str(e)

    return jsonify({
        "status": "ok" if cli_ok else "degraded",
        "cli_available": cli_ok,
        "cli_version": cli_version,
        "proxy": "claude-cli-proxy",
        "vision": True,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude CLI Proxy")
    parser.add_argument("--port", type=int, default=5055)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    print(f"Claude CLI Proxy starting on {args.host}:{args.port}")
    print(f"Endpoint: http://{args.host}:{args.port}/v1/messages")
    print("Routes Anthropic API calls through claude CLI (uses your Max plan)")
    print("Vision support: enabled (images saved to temp files, Read tool)")
    app.run(host=args.host, port=args.port, debug=False)
