#!/usr/bin/env python3
"""
openai_mcp_server.py — MCP server wrapping the OpenAI API.

Exposes tools:
  - openai_generate: Send a prompt to GPT, get a response
  - openai_code_review: Code review via GPT

Requires: OPENAI_API_KEY in .env
Install: pip install mcp openai

Run: python execution/mcp_servers/openai_mcp_server.py
"""
from __future__ import annotations

import json
import sys

try:
    from mcp.server import Server
    from mcp.server.stdio import run_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: pip install mcp", file=sys.stderr)
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: pip install openai", file=sys.stderr)
    sys.exit(1)

from mcp_server_utils import get_api_key, format_response, truncate_text

# ── Setup ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = get_api_key("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

DEFAULT_MODEL = "gpt-4.1"
FAST_MODEL = "gpt-4.1-mini"

server = Server("openai-mcp-server")


# ── Tools ─────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="openai_generate",
            description=(
                "Send a prompt to OpenAI GPT and get a response. "
                "Best for: backend code, math, test-driven development. "
                "Models: gpt-4.1 (default), gpt-4.1-mini (fast/cheap)."
            ),
            inputSchema={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to send to GPT",
                    },
                    "model": {
                        "type": "string",
                        "description": f"Model to use (default: {DEFAULT_MODEL})",
                        "default": DEFAULT_MODEL,
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "Optional system message",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Temperature 0.0-2.0 (default: 1.0)",
                        "default": 1.0,
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Max output tokens (default: 4096)",
                        "default": 4096,
                    },
                },
            },
        ),
        Tool(
            name="openai_code_review",
            description=(
                "Submit code for review by GPT. Returns issues, suggestions, "
                "and an overall quality score. Best for backend, algorithms, "
                "and test coverage analysis."
            ),
            inputSchema={
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code to review",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (default: python)",
                        "default": "python",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Review focus: 'bugs', 'performance', 'security', 'all' (default: all)",
                        "default": "all",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "openai_generate":
        return await handle_generate(arguments)
    elif name == "openai_code_review":
        return await handle_code_review(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_generate(args: dict):
    """Handle openai_generate tool call."""
    prompt = args["prompt"]
    model = args.get("model", DEFAULT_MODEL)
    system_prompt = args.get("system_prompt")
    temperature = args.get("temperature", 1.0)
    max_tokens = args.get("max_tokens", 4096)

    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        text = response.choices[0].message.content or "(empty response)"
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
            "completion_tokens": response.usage.completion_tokens if response.usage else None,
            "total_tokens": response.usage.total_tokens if response.usage else None,
        }

        result = format_response(text=truncate_text(text), model=model, usage=usage)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"OpenAI API error: {str(e)}")]


async def handle_code_review(args: dict):
    """Handle openai_code_review tool call."""
    code = args["code"]
    language = args.get("language", "python")
    focus = args.get("focus", "all")

    review_prompt = f"""Review this {language} code. Focus: {focus}.

Return a structured review with:
1. **Issues** — bugs, logic errors, edge cases (severity: critical/warning/info)
2. **Suggestions** — improvements, better patterns, performance wins
3. **Quality Score** — 1-10 with brief justification
4. **Security** — any vulnerabilities found

Code:
```{language}
{code}
```"""

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are a senior code reviewer. Be specific and actionable."},
                {"role": "user", "content": review_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        text = response.choices[0].message.content or "(empty review)"
        result = format_response(text=truncate_text(text), model=DEFAULT_MODEL)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"OpenAI code review error: {str(e)}")]


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_server(server))
