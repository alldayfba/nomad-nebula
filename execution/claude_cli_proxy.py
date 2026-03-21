"""Claude CLI Proxy — routes Anthropic API requests through claude CLI (uses Max plan).

Mimics the Anthropic Messages API at localhost:5055/v1/messages.
Translates requests into claude --print calls, returns Anthropic-format responses.

Usage:
    python execution/claude_cli_proxy.py          # Start proxy on port 5055
    python execution/claude_cli_proxy.py --port 5060  # Custom port
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid

from flask import Flask, Response, jsonify, request

app = Flask(__name__)


def _format_prompt(messages: list[dict]) -> str:
    """Convert Anthropic messages into a single prompt for claude CLI."""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Handle content blocks (list of dicts with type/text)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        if role == "assistant":
            parts.append(f"[Assistant previously said]: {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


# Clean directory with no CLAUDE.md files
CLEAN_CWD = "/tmp/claude-proxy-workspace"
os.makedirs(CLEAN_CWD, exist_ok=True)


def _call_claude_cli(system: str, prompt: str, max_tokens: int = 2048) -> str:
    """Call claude CLI with --print flag, custom system prompt, no tools."""
    cmd = [
        "claude",
        "--print",
        "--tools", "",                     # Disable all tools — pure chat
        "--disable-slash-commands",        # No skills
        "-p", prompt,
    ]

    # Pass system prompt if provided (overrides Claude Code default)
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
        cwd=CLEAN_CWD,  # Clean dir — no CLAUDE.md loaded
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:500]}")

    output = result.stdout.strip()

    # Strip any Claude Code status line leaked from CLAUDE.md instructions
    # Pattern: ~$X.XX (X.X%) | Xh Xm | X active · X queued · X blocked
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
    """Handle Anthropic Messages API requests."""
    data = request.get_json()

    system = data.get("system", "")
    messages_list = data.get("messages", [])
    max_tokens = data.get("max_tokens", 2048)
    model = data.get("model", "claude-haiku-4-5-20251001")

    prompt = _format_prompt(messages_list)

    try:
        response_text = _call_claude_cli(system, prompt, max_tokens)
    except subprocess.TimeoutExpired:
        return jsonify({"error": {"type": "timeout", "message": "CLI timed out"}}), 504
    except RuntimeError as e:
        return jsonify({"error": {"type": "cli_error", "message": str(e)}}), 502

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
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude CLI Proxy")
    parser.add_argument("--port", type=int, default=5055)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    print(f"Claude CLI Proxy starting on {args.host}:{args.port}")
    print(f"Endpoint: http://{args.host}:{args.port}/v1/messages")
    print("Routes Anthropic API calls through claude CLI (uses your Max plan)")
    app.run(host=args.host, port=args.port, debug=False)
