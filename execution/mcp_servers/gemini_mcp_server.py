#!/usr/bin/env python3
"""
gemini_mcp_server.py — MCP server wrapping the Google Gemini API.

Exposes tools:
  - gemini_generate: Send a prompt to Gemini, get a response
  - gemini_analyze_image: Multimodal image analysis

Requires: GOOGLE_API_KEY in .env
Install: pip install mcp google-generativeai

Run: python execution/mcp_servers/gemini_mcp_server.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

try:
    from mcp.server import Server
    from mcp.server.stdio import run_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: pip install mcp", file=sys.stderr)
    sys.exit(1)

try:
    import google.generativeai as genai
except ImportError:
    print("ERROR: pip install google-generativeai", file=sys.stderr)
    sys.exit(1)

from mcp_server_utils import get_api_key, format_response, truncate_text

# ── Setup ─────────────────────────────────────────────────────────────────────
GOOGLE_API_KEY = get_api_key("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

DEFAULT_MODEL = "gemini-2.0-flash"
CREATIVE_MODEL = "gemini-2.0-pro"

server = Server("gemini-mcp-server")


# ── Tools ─────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="gemini_generate",
            description=(
                "Send a prompt to Google Gemini and get a response. "
                "Best for: frontend design, multimodal tasks, fast output. "
                "Models: gemini-2.0-flash (fast, default), gemini-2.0-pro (creative)."
            ),
            inputSchema={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to send to Gemini",
                    },
                    "model": {
                        "type": "string",
                        "description": f"Model to use (default: {DEFAULT_MODEL})",
                        "default": DEFAULT_MODEL,
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "Optional system instruction",
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
            name="gemini_analyze_image",
            description=(
                "Analyze an image using Gemini's multimodal capabilities. "
                "Supports: screenshots, diagrams, photos, charts. "
                "Provide either a file path or base64-encoded image data."
            ),
            inputSchema={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "What to analyze about the image",
                    },
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file",
                    },
                    "image_base64": {
                        "type": "string",
                        "description": "Base64-encoded image data",
                    },
                    "mime_type": {
                        "type": "string",
                        "description": "Image MIME type (default: image/png)",
                        "default": "image/png",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "gemini_generate":
        return await handle_generate(arguments)
    elif name == "gemini_analyze_image":
        return await handle_analyze_image(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_generate(args: dict):
    """Handle gemini_generate tool call."""
    prompt = args["prompt"]
    model_name = args.get("model", DEFAULT_MODEL)
    system_prompt = args.get("system_prompt")
    temperature = args.get("temperature", 1.0)
    max_tokens = args.get("max_tokens", 4096)

    try:
        config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
            generation_config=config,
        )

        response = model.generate_content(prompt)
        text = response.text if response.text else "(empty response)"

        result = format_response(
            text=truncate_text(text),
            model=model_name,
            usage={
                "prompt_tokens": response.usage_metadata.prompt_token_count if hasattr(response, "usage_metadata") else None,
                "completion_tokens": response.usage_metadata.candidates_token_count if hasattr(response, "usage_metadata") else None,
            },
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Gemini API error: {str(e)}")]


async def handle_analyze_image(args: dict):
    """Handle gemini_analyze_image tool call."""
    prompt = args["prompt"]
    image_path = args.get("image_path")
    image_base64 = args.get("image_base64")
    mime_type = args.get("mime_type", "image/png")

    if not image_path and not image_base64:
        return [TextContent(type="text", text="Error: provide either image_path or image_base64")]

    try:
        model = genai.GenerativeModel(DEFAULT_MODEL)

        if image_path:
            img_path = Path(image_path)
            if not img_path.exists():
                return [TextContent(type="text", text=f"Error: Image not found: {image_path}")]
            image_data = img_path.read_bytes()
        else:
            image_data = base64.b64decode(image_base64)

        image_part = {
            "mime_type": mime_type,
            "data": image_data,
        }

        response = model.generate_content([prompt, image_part])
        text = response.text if response.text else "(empty response)"

        result = format_response(text=truncate_text(text), model=DEFAULT_MODEL)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Gemini image analysis error: {str(e)}")]


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_server(server))
