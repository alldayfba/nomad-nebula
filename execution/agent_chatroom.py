#!/usr/bin/env python3
"""
agent_chatroom.py — Multi-Agent Debate Rooms (v2).

Spawns N agents into a shared conversation where they debate, disagree, and
converge on a solution via round-robin turns with parallel execution.

Based on Nick Saraev's model-chat architecture: async parallel API calls,
streaming synthesis, structured debate format, convergence detection,
color-coded output, and interactive mode.

Usage:
    # 3-agent debate
    python execution/agent_chatroom.py \
        --topic "Best hook angle for a $10K Amazon FBA coaching offer?" \
        --personas devils_advocate,business_strategist,creative_director \
        --rounds 3

    # 5-agent debate with all default framings
    python execution/agent_chatroom.py \
        --topic "Should we use React or Next.js for the SaaS dashboard?" \
        --rounds 3

    # Interactive mode (inject messages between rounds)
    python execution/agent_chatroom.py \
        --topic "Pricing strategy for Agency OS" \
        --interactive

    # Programmatic:
    from execution.agent_chatroom import run_chatroom
    import asyncio
    result = asyncio.run(run_chatroom(topic="...", persona_names=["optimizer", "pragmatist"]))
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    anthropic = None

# Fallback to sync callers if anthropic async not available
from consensus_engine import call_claude

# ── Config ──────────────────────────────────────────────────────────────────

MODEL = os.getenv("CHATROOM_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 2048

# ── Persona Framings ────────────────────────────────────────────────────────
# Nick Saraev's 8 agent framings (used when --personas not specified)

DEFAULT_FRAMINGS = [
    {
        "id": "systems-thinker",
        "name": "Systems Thinker",
        "framing": (
            "You tend to think in systems and architecture. You reason about "
            "structure, dependencies, second-order effects, and how pieces fit "
            "together. You look for leverage points and compounding mechanisms."
        ),
    },
    {
        "id": "pragmatist",
        "name": "Pragmatist",
        "framing": (
            "You tend to think practically and focus on what ships fast. You're "
            "skeptical of overengineering and prefer simple, proven approaches. "
            "You ask 'does this actually work in practice?' before anything else."
        ),
    },
    {
        "id": "edge-case-finder",
        "name": "Edge-Case Finder",
        "framing": (
            "You tend to find edge cases, failure modes, and hidden assumptions. "
            "You stress-test ideas by asking 'what happens when X goes wrong?' "
            "You're the one who prevents catastrophic oversights."
        ),
    },
    {
        "id": "user-advocate",
        "name": "User Advocate",
        "framing": (
            "You tend to think about user experience and how things feel in "
            "practice. You optimize for clarity, simplicity, and delight. You "
            "ask 'would a real person actually use this?' and 'is this intuitive?'"
        ),
    },
    {
        "id": "contrarian",
        "name": "Contrarian",
        "framing": (
            "You tend to challenge assumptions and propose unconventional "
            "alternatives. You play devil's advocate not to be difficult, but "
            "because the best ideas survive strong opposition. You ask 'what if "
            "the opposite were true?'"
        ),
    },
    {
        "id": "first-principles",
        "name": "First Principles Thinker",
        "framing": (
            "You reason from first principles. You strip away conventions and "
            "ask 'why does it have to be this way?' You're willing to propose "
            "radical simplifications that others overlook."
        ),
    },
    {
        "id": "risk-analyst",
        "name": "Risk Analyst",
        "framing": (
            "You think in terms of risk, probability, and downside protection. "
            "You weigh the cost of being wrong against the cost of being slow. "
            "You look for irreversible decisions and flag them."
        ),
    },
    {
        "id": "integrator",
        "name": "Integrator",
        "framing": (
            "You look for synthesis and common ground. You find the 80% that "
            "everyone agrees on and surface the 20% that actually matters. You "
            "bridge different perspectives into coherent plans."
        ),
    },
]

# ── Color Output ────────────────────────────────────────────────────────────

AGENT_COLORS = ["36", "33", "35", "32", "31", "34", "96", "93"]


def color(text, code):
    """ANSI color wrapper."""
    if not sys.stdout.isatty():
        return text
    return "\033[{}m{}\033[0m".format(code, text)


def agent_color(idx, text):
    return color(text, AGENT_COLORS[idx % len(AGENT_COLORS)])


def print_header(text):
    w = min(os.get_terminal_size().columns if sys.stdout.isatty() else 80, 80)
    print(color("\n" + "=" * w, "1;37"))
    print(color("  " + text, "1;37"))
    print(color("=" * w + "\n", "1;37"))


def print_round_header(round_num, total):
    w = min(os.get_terminal_size().columns if sys.stdout.isatty() else 80, 80)
    print(color("\n" + "-" * w, "90"))
    print(color("  ROUND {}/{}".format(round_num, total), "1;97"))
    print(color("-" * w, "90"))


# ── Persona Loading ─────────────────────────────────────────────────────────

PERSONAS_FILE = Path(__file__).parent / "chatroom_personas.json"


def load_personas():
    """Load custom personas from JSON file."""
    if PERSONAS_FILE.exists():
        with open(PERSONAS_FILE, "r") as f:
            return json.load(f)
    return {}


def build_agents(persona_names, agent_count):
    """Build agent list from persona names or default framings."""
    custom_personas = load_personas()

    if persona_names:
        # Use specified personas
        agents = []
        for i, name in enumerate(persona_names):
            if name in custom_personas:
                p = custom_personas[name]
                agents.append({
                    "idx": i,
                    "id": name,
                    "name": p["name"],
                    "system_prompt": p["system_prompt"],
                })
            else:
                # Check default framings
                match = next((f for f in DEFAULT_FRAMINGS if f["id"] == name), None)
                if match:
                    agents.append({
                        "idx": i,
                        "id": match["id"],
                        "name": match["name"],
                        "system_prompt": _build_system_prompt(match, len(persona_names)),
                    })
                else:
                    agents.append({
                        "idx": i,
                        "id": name,
                        "name": name.replace("_", " ").replace("-", " ").title(),
                        "system_prompt": "You are {} in a multi-agent debate.".format(
                            name.replace("_", " ").replace("-", " ")
                        ),
                    })
        return agents
    else:
        # Use default framings (cycle if more than 8)
        agents = []
        for i in range(agent_count):
            framing = DEFAULT_FRAMINGS[i % len(DEFAULT_FRAMINGS)]
            agents.append({
                "idx": i,
                "id": framing["id"],
                "name": framing["name"],
                "system_prompt": _build_system_prompt(framing, agent_count),
            })
        return agents


def _build_system_prompt(framing, agent_count):
    """Build system prompt from a framing definition."""
    return (
        "You are one of {} AI participants in a collaborative debate room. "
        "Your role is to help solve a problem through genuine intellectual discourse.\n\n"
        "{}\n\n"
        "## Rules of engagement\n"
        "- Read all previous messages carefully before responding.\n"
        "- Build on, challenge, or refine what others have said — don't just repeat your own position.\n"
        "- If you agree with someone, say so briefly and add something new.\n"
        "- If you disagree, explain WHY with concrete reasoning.\n"
        "- Be concise. 150-300 words max per response. No filler.\n"
        "- Use your unique perspective — that's why you're here.\n"
        "- Address other participants directly when responding to their points.\n"
        "- It's fine to change your mind if someone makes a compelling argument.\n\n"
        "## Format\n"
        "Start your response with **[{}]:** then your contribution. No preamble."
    ).format(agent_count, framing["framing"], framing["id"])


# ── Prompt Templates ────────────────────────────────────────────────────────

ROUND_1_FORMAT = """This is Round 1 of a multi-agent debate. State your initial position on this problem. Be specific and concrete — propose actual solutions, not vague principles. Take a clear stance.

Other agents will challenge your position in subsequent rounds, so make your reasoning explicit.

Respond in this format:
POSITION: [Your one-sentence stance]
REASONING: [Your detailed argument — 3-5 key points]
PROPOSAL: [Your concrete recommendation]
CONCERNS: [What could go wrong with your approach]"""

ROUND_N_FORMAT = """This is Round {round_num} of a multi-agent debate. Read the previous discussion carefully.

Your job:
1. Respond to the strongest counterargument against your position
2. Identify where you AGREE with other agents (concede good points)
3. Identify where you still DISAGREE and why
4. Refine your proposal based on the discussion so far

Do NOT just repeat your previous position. Engage with what others said. Change your mind if they made a better argument.

Respond in this format:
AGREEMENTS: [What other agents got right]
DISAGREEMENTS: [Where you still differ and why]
REFINED PROPOSAL: [Your updated recommendation]
CONFIDENCE: [1-10 how confident you are in your refined position]"""

SYNTHESIS_PROMPT = """You are a senior synthesizer. You've just observed a {round_count}-round debate between {agent_count} AI participants on the following topic:

**{topic}**

Read the full debate transcript below, then produce a structured synthesis.

## Your output format

### Consensus
What did most or all participants agree on? List the 3-5 strongest points of agreement.

### Key Disagreements
Where did participants genuinely disagree? For each disagreement:
- State the tension clearly
- Summarize each side's strongest argument
- Give your assessment of which side is stronger and why

### Surprising Insights
Any unexpected ideas, edge cases, or reframings that emerged from the debate?

### Final Recommendation
Based on the full debate, what is the best path forward? Be specific and actionable.

## Debate Transcript
{transcript}"""


# ── Async Core ──────────────────────────────────────────────────────────────

async def get_agent_response_async(client, agent, conversation, topic, round_num, total_rounds):
    """Get a single agent's response via async API call."""
    messages = []
    messages.append({"role": "user", "content": "**Topic for debate:** {}".format(topic)})

    for entry in conversation:
        messages.append({"role": "assistant", "content": entry["content"]})
        messages.append({
            "role": "user",
            "content": "Continue the debate. Respond to the points made above.",
        })

    # Replace last generic prompt with structured format
    if conversation:
        messages.pop()
        if round_num > 1:
            messages.append({
                "role": "user",
                "content": ROUND_N_FORMAT.format(round_num=round_num),
            })
        else:
            messages.append({
                "role": "user",
                "content": "It's your turn. Respond to the discussion above.",
            })
    else:
        # First message — use Round 1 format
        messages.pop()
        messages.append({"role": "user", "content": "**Topic for debate:** {}\n\n{}".format(topic, ROUND_1_FORMAT)})

    try:
        async with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=agent["system_prompt"],
            messages=messages,
        ) as stream:
            response = await stream.get_final_message()
        return response.content[0].text
    except Exception as e:
        return "[Error: {}]".format(str(e))


def get_agent_response_sync(agent, conversation, topic, round_num):
    """Fallback sync response via consensus_engine callers."""
    parts = ["**Topic for debate:** {}\n".format(topic)]

    for entry in conversation:
        parts.append("**[{}]:** {}".format(entry.get("agent_id", "agent"), entry["content"]))

    if round_num == 1:
        parts.append(ROUND_1_FORMAT)
    else:
        parts.append(ROUND_N_FORMAT.format(round_num=round_num))

    prompt = "\n\n".join(parts)
    response = call_claude(prompt, temperature=0.8, system_prompt=agent["system_prompt"])
    if "error" in response:
        return "[Error: {}]".format(response["error"])
    return response["text"]


def check_convergence(conversation, agents, current_round):
    """Check if all agents have converged (confidence 8+ and aligned proposals)."""
    if current_round < 2:
        return False

    # Look for CONFIDENCE scores in the last round's entries
    last_round_entries = [e for e in conversation if e.get("round") == current_round]
    confidences = []
    for entry in last_round_entries:
        # Extract confidence score from text
        match = re.search(r"CONFIDENCE:\s*(\d+)", entry.get("content", ""))
        if match:
            confidences.append(int(match.group(1)))

    if len(confidences) >= len(agents) and all(c >= 8 for c in confidences):
        return True
    return False


# ── Main Runner ─────────────────────────────────────────────────────────────

async def run_chatroom_async(
    topic,
    persona_names=None,
    agent_count=5,
    rounds=3,
    interactive=False,
):
    """Run a multi-agent debate with async parallel API calls."""
    if anthropic is None:
        raise ImportError("anthropic package required for async mode. pip install anthropic")

    client = anthropic.AsyncAnthropic()
    agents = build_agents(persona_names, agent_count)
    conversation = []

    print_header("AGENT CHATROOM — {} agents, {} rounds".format(len(agents), rounds))
    print(color("  Topic: {}\n".format(topic), "97"))
    print(color("  Agents:", "90"))
    for a in agents:
        print(agent_color(a["idx"], "    - {}".format(a["name"])))
    print()

    converged = False

    for round_num in range(1, rounds + 1):
        print_round_header(round_num, rounds)

        # Fire all API calls in parallel
        tasks = [
            get_agent_response_async(client, agent, conversation.copy(), topic, round_num, rounds)
            for agent in agents
        ]

        print(color("  (all agents thinking...)", "90"))
        responses = await asyncio.gather(*tasks)

        # Print responses sequentially (no interleaving)
        for agent, response_text in zip(agents, responses):
            prefix = agent_color(agent["idx"], "\n[{}]".format(agent["name"]))
            sys.stdout.write(prefix + " ")
            sys.stdout.write(agent_color(agent["idx"], response_text))
            sys.stdout.write("\n")
            sys.stdout.flush()

            conversation.append({
                "round": round_num,
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "content": response_text,
                "timestamp": datetime.now().isoformat(),
            })

        # Convergence detection
        if check_convergence(conversation, agents, round_num):
            print(color("\n  [Converged] All agents at confidence 8+. Stopping early.", "1;32"))
            converged = True
            break

        # Interactive mode
        if interactive and round_num < rounds:
            print(color(
                "\n  [Interactive] Press Enter to continue, or type to inject a message:",
                "90",
            ))
            try:
                user_input = input(color("  > ", "97")).strip()
                if user_input:
                    print(color("\n  [User]: {}".format(user_input), "1;97"))
                    conversation.append({
                        "round": round_num,
                        "agent_id": "user",
                        "agent_name": "User (moderator)",
                        "content": user_input,
                        "timestamp": datetime.now().isoformat(),
                    })
            except EOFError:
                pass

    # ── Synthesis ────────────────────────────────────────────────────────
    print_header("SYNTHESIS")

    transcript = "\n\n".join(
        "**[{}]:** {}".format(e["agent_name"], e["content"])
        for e in conversation
    )

    synth_prompt = SYNTHESIS_PROMPT.format(
        round_count=round_num,
        agent_count=len(agents),
        topic=topic,
        transcript=transcript,
    )

    # Stream synthesis for real-time feel
    synthesis_parts = []
    try:
        async with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": synth_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                sys.stdout.write(color(text, "97"))
                sys.stdout.flush()
                synthesis_parts.append(text)
    except Exception as e:
        synthesis_parts.append("[Synthesis error: {}]".format(str(e)))

    synthesis = "".join(synthesis_parts)
    print("\n")

    # ── Save outputs ────────────────────────────────────────────────────
    base_dir = Path(__file__).parent.parent / ".tmp" / "chatrooms"
    run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = base_dir / run_ts
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "topic": topic,
        "agent_count": len(agents),
        "round_count": round_num,
        "model": MODEL,
        "converged": converged,
        "timestamp": datetime.now().isoformat(),
        "agents": [{"id": a["id"], "name": a["name"], "idx": a["idx"]} for a in agents],
        "conversation": conversation,
        "synthesis": synthesis,
    }

    conv_path = output_dir / "conversation.json"
    conv_path.write_text(json.dumps(result, indent=2))

    synth_path = output_dir / "synthesis.md"
    synth_path.write_text(
        "# Agent Chatroom Synthesis\n\n"
        "**Topic:** {}\n"
        "**Agents:** {} | **Rounds:** {} | **Model:** {}\n"
        "**Date:** {}\n**Converged:** {}\n\n"
        "---\n\n{}\n".format(
            topic, len(agents), round_num, MODEL,
            datetime.now().strftime("%Y-%m-%d %H:%M"), converged, synthesis,
        )
    )

    # Update 'latest' symlink
    latest_link = base_dir / "latest"
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(output_dir)

    print(color("  Saved: {}".format(conv_path), "90"))
    print(color("  Saved: {}".format(synth_path), "90"))

    return result


def run_chatroom(
    topic,
    persona_names=None,
    agent_count=5,
    rounds=3,
    model="claude",
    temperature=0.8,
    interactive=False,
):
    """Sync wrapper — tries async first, falls back to sync sequential."""
    # Try async path (requires anthropic package)
    if anthropic is not None:
        return asyncio.run(run_chatroom_async(
            topic=topic,
            persona_names=persona_names,
            agent_count=agent_count if not persona_names else len(persona_names),
            rounds=rounds,
            interactive=interactive,
        ))

    # Fallback: sync sequential (original behavior)
    agents = build_agents(persona_names, agent_count if not persona_names else len(persona_names))
    conversation = []

    for round_num in range(1, rounds + 1):
        for agent in agents:
            text = get_agent_response_sync(agent, conversation, topic, round_num)
            conversation.append({
                "round": round_num,
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "content": text,
                "timestamp": datetime.now().isoformat(),
            })

    # Sync synthesis
    transcript = "\n\n".join(
        "**[{}]:** {}".format(e["agent_name"], e["content"])
        for e in conversation
    )
    synth_prompt = SYNTHESIS_PROMPT.format(
        round_count=rounds,
        agent_count=len(agents),
        topic=topic,
        transcript=transcript,
    )
    synth_response = call_claude(synth_prompt, temperature=0.3)
    synthesis = synth_response.get("text", "[Synthesis failed]") if "error" not in synth_response else "[Error]"

    return {
        "topic": topic,
        "agent_count": len(agents),
        "round_count": rounds,
        "model": model,
        "converged": False,
        "timestamp": datetime.now().isoformat(),
        "agents": [{"id": a["id"], "name": a["name"], "idx": a["idx"]} for a in agents],
        "conversation": conversation,
        "synthesis": synthesis,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-agent debate chatroom (v2)")
    parser.add_argument("topic", nargs="?", help="The debate topic or question")
    parser.add_argument("--topic", dest="topic_flag", help="Topic (alt flag form)")
    parser.add_argument("--personas",
                        help="Comma-separated persona names (e.g., contrarian,pragmatist,edge-case-finder)")
    parser.add_argument("--agents", type=int, default=5, help="Number of agents if no --personas (default: 5)")
    parser.add_argument("--rounds", type=int, default=3, help="Number of debate rounds (default: 3)")
    parser.add_argument("--model", default="claude", choices=["claude", "gemini", "openai"])
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--interactive", action="store_true", help="Inject messages between rounds")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--list-personas", action="store_true", help="List available personas")
    args = parser.parse_args()

    if args.list_personas:
        print("\n  Custom personas (chatroom_personas.json):")
        for key, p in load_personas().items():
            print("    {:25s} — {}".format(key, p["name"]))
        print("\n  Default framings (Nick Saraev):")
        for f in DEFAULT_FRAMINGS:
            print("    {:25s} — {}".format(f["id"], f["name"]))
        return

    topic = args.topic or args.topic_flag
    if not topic:
        parser.error("topic is required (positional or --topic)")

    persona_names = [p.strip() for p in args.personas.split(",")] if args.personas else None
    agent_count = len(persona_names) if persona_names else args.agents

    print("Starting chatroom: {} agents x {} rounds".format(agent_count, args.rounds))

    result = run_chatroom(
        topic=topic,
        persona_names=persona_names,
        agent_count=agent_count,
        rounds=args.rounds,
        model=args.model,
        temperature=args.temperature,
        interactive=args.interactive,
    )

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
