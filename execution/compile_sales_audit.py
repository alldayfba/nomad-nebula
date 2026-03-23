#!/usr/bin/env python3
"""
Compile all individual call analysis JSONs into the final SALES_CALL_AUDIT.md.
Phase 3 of the sales call audit pipeline.

Step 1: Python-based statistical aggregation (no API)
Step 2: Write the full audit document with all sections

Usage:
    python execution/compile_sales_audit.py
    python execution/compile_sales_audit.py --stats-only   # Just print stats
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

ANALYSIS_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "analysis")
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "manifest.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "SALES_CALL_AUDIT.md")
STATS_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "aggregated_stats.json")


def load_all_analyses():
    """Load all call analysis JSON files."""
    analyses = []
    errors = []
    for f in sorted(os.listdir(ANALYSIS_DIR)):
        if not f.endswith(".json"):
            continue
        filepath = os.path.join(ANALYSIS_DIR, f)
        try:
            with open(filepath, "r") as fh:
                data = json.load(fh)
                if "error" in data and "outcome" not in data:
                    errors.append((f, data.get("error", "unknown")))
                    continue
                analyses.append(data)
        except Exception as e:
            errors.append((f, str(e)))
    return analyses, errors


def compute_stats(analyses):
    """Compute aggregate statistics from all analyses."""
    stats = {}

    # Filter to sales calls only (exclude coaching, no_show with 0 duration)
    sales_calls = [a for a in analyses if a.get("outcome") not in ("coaching_call",)]
    all_calls = analyses

    stats["total_calls"] = len(all_calls)
    stats["sales_calls"] = len(sales_calls)
    stats["coaching_calls"] = len([a for a in all_calls if a.get("outcome") == "coaching_call"])

    # Outcomes
    outcome_counts = Counter(a.get("outcome", "unknown") for a in all_calls)
    stats["outcomes"] = dict(outcome_counts.most_common())

    # Close rate
    closed = [a for a in sales_calls if a.get("outcome") in ("closed", "verbal_yes_pending")]
    stats["closed_count"] = len(closed)
    stats["close_rate"] = len(closed) / len(sales_calls) * 100 if sales_calls else 0

    # Revenue
    stats["total_revenue"] = sum(a.get("revenue", 0) for a in all_calls)
    stats["avg_deal_size"] = stats["total_revenue"] / len(closed) if closed else 0
    stats["pif_count"] = len([a for a in closed if a.get("payment_type") == "pif"])
    stats["payment_plan_count"] = len([a for a in closed if a.get("payment_type") == "payment_plan"])
    stats["deposit_count"] = len([a for a in closed if a.get("payment_type") == "deposit"])

    # By closer
    for closer_name in ("Sabbo", "Rocky"):
        closer_calls = [a for a in sales_calls if a.get("closer") == closer_name]
        closer_closed = [a for a in closer_calls if a.get("outcome") in ("closed", "verbal_yes_pending")]
        stats[f"{closer_name.lower()}_calls"] = len(closer_calls)
        stats[f"{closer_name.lower()}_closed"] = len(closer_closed)
        stats[f"{closer_name.lower()}_close_rate"] = len(closer_closed) / len(closer_calls) * 100 if closer_calls else 0
        stats[f"{closer_name.lower()}_revenue"] = sum(a.get("revenue", 0) for a in closer_closed)

    # Duration
    durations = [a.get("duration_min", 0) for a in sales_calls if a.get("duration_min", 0) > 0]
    stats["avg_duration"] = sum(durations) / len(durations) if durations else 0
    closed_durations = [a.get("duration_min", 0) for a in closed if a.get("duration_min", 0) > 0]
    lost_durations = [a.get("duration_min", 0) for a in sales_calls if a.get("outcome") not in ("closed", "verbal_yes_pending", "coaching_call", "no_show") and a.get("duration_min", 0) > 0]
    stats["avg_duration_closed"] = sum(closed_durations) / len(closed_durations) if closed_durations else 0
    stats["avg_duration_lost"] = sum(lost_durations) / len(lost_durations) if lost_durations else 0

    # Objections
    all_objections = []
    for a in sales_calls:
        for obj in a.get("objections", []):
            all_objections.append(obj)
    objection_type_counts = Counter(obj.get("type", "other") for obj in all_objections)
    stats["objection_counts"] = dict(objection_type_counts.most_common())
    stats["total_objections"] = len(all_objections)

    # Objection resolution rates
    objection_resolution = {}
    for obj_type in objection_type_counts:
        type_objs = [o for o in all_objections if o.get("type") == obj_type]
        resolved = [o for o in type_objs if o.get("resolved")]
        objection_resolution[obj_type] = {
            "count": len(type_objs),
            "resolved": len(resolved),
            "resolution_rate": len(resolved) / len(type_objs) * 100 if type_objs else 0
        }
    stats["objection_resolution"] = objection_resolution

    # NEPQ stages
    nepq_stats = {}
    stage_names = ["1_connecting", "2_situation", "3_problem_awareness", "4_preframe",
                   "5_solution_awareness", "6_consequence", "7_commitment", "8_transition", "9_close"]
    for stage in stage_names:
        stage_data = [a.get("nepq_stages", {}).get(stage, {}) for a in sales_calls]
        executed = [s for s in stage_data if s.get("executed")]
        grades = [s.get("quality", "F") for s in executed if s.get("quality")]
        grade_map = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        avg_grade = sum(grade_map.get(g, 0) for g in grades) / len(grades) if grades else 0
        reverse_map = {4: "A", 3: "B", 2: "C", 1: "D", 0: "F"}
        avg_letter = reverse_map.get(round(avg_grade), "F")

        nepq_stats[stage] = {
            "execution_rate": len(executed) / len(stage_data) * 100 if stage_data else 0,
            "avg_grade": avg_letter,
            "avg_grade_numeric": round(avg_grade, 2),
            "grade_distribution": dict(Counter(grades).most_common()),
        }
    stats["nepq_stages"] = nepq_stats

    # Overall grades
    grades = [a.get("overall_grade", "F") for a in sales_calls]
    stats["grade_distribution"] = dict(Counter(grades).most_common())

    # ICP tiers
    tier_counts = Counter(a.get("icp", {}).get("tier", "unknown") for a in sales_calls)
    stats["tier_distribution"] = dict(tier_counts.most_common())

    # ICP tier close rates
    tier_close_rates = {}
    for tier in tier_counts:
        tier_calls = [a for a in sales_calls if a.get("icp", {}).get("tier") == tier]
        tier_closed = [a for a in tier_calls if a.get("outcome") in ("closed", "verbal_yes_pending")]
        tier_close_rates[tier] = {
            "calls": len(tier_calls),
            "closed": len(tier_closed),
            "close_rate": len(tier_closed) / len(tier_calls) * 100 if tier_calls else 0
        }
    stats["tier_close_rates"] = tier_close_rates

    # Content sources
    content_sources = Counter()
    for a in sales_calls:
        src = a.get("icp", {}).get("content_that_brought_them", "unknown")
        if src:
            content_sources[src.lower().strip()] += 1
    stats["content_sources"] = dict(content_sources.most_common())

    # Specific content named
    named_content = Counter()
    for a in sales_calls:
        for item in a.get("icp", {}).get("specific_content_named", []):
            if item and item.lower() not in ("none", "n/a", "unknown", ""):
                named_content[item] += 1
    stats["named_content"] = dict(named_content.most_common(20))

    # Problems stated
    all_problems = Counter()
    for a in sales_calls:
        for prob in a.get("icp", {}).get("stated_problems", []):
            if prob:
                all_problems[prob.lower().strip()] += 1
    stats["stated_problems"] = dict(all_problems.most_common(20))

    # Amazon experience distribution
    exp_counts = Counter(a.get("icp", {}).get("amazon_experience", "unknown") for a in sales_calls)
    stats["experience_distribution"] = dict(exp_counts.most_common())

    # Age distribution
    age_counts = Counter(a.get("icp", {}).get("age_bracket", "unknown") for a in sales_calls)
    stats["age_distribution"] = dict(age_counts.most_common())

    # Tonality
    tone_counts = Counter(a.get("tonality", {}).get("dominant_tone", "unknown") for a in sales_calls)
    stats["tone_distribution"] = dict(tone_counts.most_common())

    energy_counts = Counter(a.get("tonality", {}).get("energy_level", "unknown") for a in sales_calls)
    stats["energy_distribution"] = dict(energy_counts.most_common())

    # Technique usage rates
    technique_usage = {
        "pre_frame_used": sum(1 for a in sales_calls if a.get("tonality", {}).get("pre_frame_used")),
        "revealing_question_used": sum(1 for a in sales_calls if a.get("tonality", {}).get("revealing_question_used")),
        "future_pacing_used": sum(1 for a in sales_calls if a.get("tonality", {}).get("future_pacing_used")),
        "consequence_framing_used": sum(1 for a in sales_calls if a.get("tonality", {}).get("consequence_framing_used")),
    }
    stats["technique_usage"] = {k: {"count": v, "rate": v / len(sales_calls) * 100 if sales_calls else 0} for k, v in technique_usage.items()}

    # Top improvements (most common)
    improvements = Counter()
    for a in sales_calls:
        imp = a.get("biggest_improvement", "")
        if imp:
            improvements[imp] += 1
    stats["top_improvements"] = dict(improvements.most_common(15))

    return stats


def format_pct(value):
    return f"{value:.1f}%"


def write_audit_document(analyses, stats, errors):
    """Write the full SALES_CALL_AUDIT.md document."""
    sales_calls = [a for a in analyses if a.get("outcome") not in ("coaching_call",)]
    closed = [a for a in sales_calls if a.get("outcome") in ("closed", "verbal_yes_pending")]

    lines = []
    def w(s=""):
        lines.append(s)

    w("# SALES CALL AUDIT — AllDay FBA (Amazon OS)")
    w(f"**{stats['total_calls']} Calls Analyzed | Closers: Sabbo + Rocky | Generated: {datetime.now().strftime('%Y-%m-%d')}**")
    w()
    w("---")
    w()

    # ─── SECTION 1: EXECUTIVE SUMMARY ───
    w("## 1. EXECUTIVE SUMMARY")
    w()
    w(f"| Metric | Value |")
    w(f"|---|---|")
    w(f"| Total Calls Analyzed | {stats['total_calls']} |")
    w(f"| Sales Calls | {stats['sales_calls']} |")
    w(f"| Coaching/Support Calls | {stats['coaching_calls']} |")
    w(f"| **Closed Deals** | **{stats['closed_count']}** |")
    w(f"| **Close Rate** | **{format_pct(stats['close_rate'])}** |")
    w(f"| **Total Revenue** | **${stats['total_revenue']:,.0f}** |")
    w(f"| Avg Deal Size | ${stats['avg_deal_size']:,.0f} |")
    w(f"| Avg Call Duration | {stats['avg_duration']:.0f} min |")
    w(f"| Avg Duration (Closed) | {stats['avg_duration_closed']:.0f} min |")
    w(f"| Avg Duration (Lost) | {stats['avg_duration_lost']:.0f} min |")
    w()

    # Top 3 strengths/weaknesses from NEPQ
    sorted_stages = sorted(stats["nepq_stages"].items(), key=lambda x: x[1]["avg_grade_numeric"], reverse=True)
    w("### Top Strengths")
    for stage, data in sorted_stages[:3]:
        w(f"- **{stage}**: {format_pct(data['execution_rate'])} execution, avg grade {data['avg_grade']}")
    w()
    w("### Top Weaknesses")
    for stage, data in sorted_stages[-3:]:
        w(f"- **{stage}**: {format_pct(data['execution_rate'])} execution, avg grade {data['avg_grade']}")
    w()

    # ─── SECTION 2: PIPELINE DIAGNOSTICS ───
    w("---")
    w()
    w("## 2. PIPELINE DIAGNOSTICS")
    w()
    w("### 2.1 Outcome Distribution")
    w()
    w("| Outcome | Count | % |")
    w("|---|---|---|")
    for outcome, count in sorted(stats["outcomes"].items(), key=lambda x: -x[1]):
        pct = count / stats["total_calls"] * 100
        w(f"| {outcome} | {count} | {format_pct(pct)} |")
    w()

    w("### 2.2 Closer Comparison")
    w()
    w("| Metric | Sabbo | Rocky |")
    w("|---|---|---|")
    w(f"| Calls | {stats.get('sabbo_calls', 0)} | {stats.get('rocky_calls', 0)} |")
    w(f"| Closed | {stats.get('sabbo_closed', 0)} | {stats.get('rocky_closed', 0)} |")
    w(f"| Close Rate | {format_pct(stats.get('sabbo_close_rate', 0))} | {format_pct(stats.get('rocky_close_rate', 0))} |")
    w(f"| Revenue | ${stats.get('sabbo_revenue', 0):,.0f} | ${stats.get('rocky_revenue', 0):,.0f} |")
    w()

    w("### 2.3 Payment Type Distribution")
    w()
    w(f"- Pay-in-Full: {stats['pif_count']}")
    w(f"- Payment Plan: {stats['payment_plan_count']}")
    w(f"- Deposit: {stats['deposit_count']}")
    w()

    w("### 2.4 Overall Call Grade Distribution")
    w()
    w("| Grade | Count | % |")
    w("|---|---|---|")
    for grade in ["A", "B", "C", "D", "F"]:
        count = stats["grade_distribution"].get(grade, 0)
        pct = count / stats["sales_calls"] * 100 if stats["sales_calls"] else 0
        w(f"| {grade} | {count} | {format_pct(pct)} |")
    w()

    # ─── SECTION 3: ICP INTELLIGENCE ───
    w("---")
    w()
    w("## 3. ICP INTELLIGENCE")
    w()
    w("### 3.1 Who IS Buying (Closed Deal Profiles)")
    w()
    if closed:
        w("| # | Prospect | Closer | Revenue | Tier | Experience | Capital | Motivation |")
        w("|---|---|---|---|---|---|---|---|")
        for a in closed:
            icp = a.get("icp", {})
            w(f"| {a.get('call_id', '?')} | {a.get('prospect_name', '?')} | {a.get('closer', '?')} | ${a.get('revenue', 0):,.0f} | {icp.get('tier', '?')} | {icp.get('amazon_experience', '?')} | {icp.get('capital_available', '?')} | {icp.get('motivation', '?')[:50]} |")
    w()

    w("### 3.2 ICP Tier Close Rates")
    w()
    w("| Tier | Calls | Closed | Close Rate |")
    w("|---|---|---|---|")
    for tier, data in sorted(stats["tier_close_rates"].items(), key=lambda x: -x[1]["close_rate"]):
        w(f"| {tier} | {data['calls']} | {data['closed']} | {format_pct(data['close_rate'])} |")
    w()

    w("### 3.3 Experience Distribution")
    w()
    w("| Experience | Count | % |")
    w("|---|---|---|")
    for exp, count in stats["experience_distribution"].items():
        pct = count / stats["sales_calls"] * 100 if stats["sales_calls"] else 0
        w(f"| {exp} | {count} | {format_pct(pct)} |")
    w()

    w("### 3.4 Age Distribution")
    w()
    w("| Age Bracket | Count | % |")
    w("|---|---|---|")
    for age, count in stats["age_distribution"].items():
        pct = count / stats["sales_calls"] * 100 if stats["sales_calls"] else 0
        w(f"| {age} | {count} | {format_pct(pct)} |")
    w()

    w("### 3.5 Content That Brought Them")
    w()
    w("| Source | Count | % |")
    w("|---|---|---|")
    for src, count in stats["content_sources"].items():
        pct = count / stats["sales_calls"] * 100 if stats["sales_calls"] else 0
        w(f"| {src} | {count} | {format_pct(pct)} |")
    w()

    if stats["named_content"]:
        w("### 3.6 Specific Content Named on Calls")
        w()
        w("| Content | Times Named |")
        w("|---|---|")
        for content, count in stats["named_content"].items():
            w(f"| {content} | {count} |")
        w()

    w("### 3.7 Top Stated Problems")
    w()
    w("| Problem | Count |")
    w("|---|---|")
    for prob, count in list(stats["stated_problems"].items())[:15]:
        w(f"| {prob} | {count} |")
    w()

    # ─── SECTION 4: OBJECTION CATALOG ───
    w("---")
    w()
    w("## 4. OBJECTION CATALOG")
    w()
    w(f"**Total objections across all calls: {stats['total_objections']}**")
    w()
    w("### 4.1 Frequency Table")
    w()
    w("| Objection Type | Count | % of All | Resolution Rate |")
    w("|---|---|---|---|")
    for obj_type, data in sorted(stats["objection_resolution"].items(), key=lambda x: -x[1]["count"]):
        pct = data["count"] / stats["total_objections"] * 100 if stats["total_objections"] else 0
        w(f"| {obj_type} | {data['count']} | {format_pct(pct)} | {format_pct(data['resolution_rate'])} |")
    w()

    # Deep dive on top 5 objections with verbatim examples
    w("### 4.2 Top Objections — Deep Dive")
    w()
    top_obj_types = [t for t, _ in Counter(obj.get("type") for a in sales_calls for obj in a.get("objections", [])).most_common(5)]
    for obj_type in top_obj_types:
        w(f"#### {obj_type.upper().replace('_', ' ')}")
        w()
        examples = []
        for a in sales_calls:
            for obj in a.get("objections", []):
                if obj.get("type") == obj_type:
                    examples.append({
                        "call_id": a.get("call_id"),
                        "prospect": a.get("prospect_name"),
                        "quote": obj.get("verbatim_quote", ""),
                        "rebuttal": obj.get("rebuttal_used", ""),
                        "quality": obj.get("rebuttal_quality", "?"),
                        "resolved": obj.get("resolved", False),
                    })
        # Show best and worst examples
        resolved_ex = [e for e in examples if e["resolved"]]
        unresolved_ex = [e for e in examples if not e["resolved"]]
        if resolved_ex:
            best = resolved_ex[0]
            w(f"**Best handled (resolved):** Call #{best['call_id']} ({best['prospect']})")
            w(f"- Prospect: \"{best['quote']}\"")
            w(f"- Rebuttal: \"{best['rebuttal']}\" (Grade: {best['quality']})")
            w()
        if unresolved_ex:
            worst = unresolved_ex[0]
            w(f"**Worst handled (unresolved):** Call #{worst['call_id']} ({worst['prospect']})")
            w(f"- Prospect: \"{worst['quote']}\"")
            w(f"- Rebuttal: \"{worst['rebuttal']}\" (Grade: {worst['quality']})")
            w()

    # ─── SECTION 5: CALL FLOW ANALYSIS ───
    w("---")
    w()
    w("## 5. CALL FLOW ANALYSIS (NEPQ + TONALITY)")
    w()
    w("### 5.1 NEPQ Stage Execution")
    w()
    w("| Stage | Execution Rate | Avg Grade | A | B | C | D | F |")
    w("|---|---|---|---|---|---|---|---|")
    for stage in ["1_connecting", "2_situation", "3_problem_awareness", "4_preframe",
                   "5_solution_awareness", "6_consequence", "7_commitment", "8_transition", "9_close"]:
        data = stats["nepq_stages"][stage]
        dist = data["grade_distribution"]
        w(f"| {stage} | {format_pct(data['execution_rate'])} | {data['avg_grade']} | {dist.get('A', 0)} | {dist.get('B', 0)} | {dist.get('C', 0)} | {dist.get('D', 0)} | {dist.get('F', 0)} |")
    w()

    w("### 5.2 Technique Usage")
    w()
    w("| Technique | Used | Rate |")
    w("|---|---|---|")
    for technique, data in stats["technique_usage"].items():
        w(f"| {technique} | {data['count']} | {format_pct(data['rate'])} |")
    w()

    w("### 5.3 Tonality Distribution")
    w()
    w("| Dominant Tone | Count | % |")
    w("|---|---|---|")
    for tone, count in stats["tone_distribution"].items():
        pct = count / stats["sales_calls"] * 100 if stats["sales_calls"] else 0
        w(f"| {tone} | {count} | {format_pct(pct)} |")
    w()

    w("### 5.4 Energy Level Distribution")
    w()
    w("| Energy | Count | % |")
    w("|---|---|---|")
    for energy, count in stats["energy_distribution"].items():
        pct = count / stats["sales_calls"] * 100 if stats["sales_calls"] else 0
        w(f"| {energy} | {count} | {format_pct(pct)} |")
    w()

    # ─── SECTION 6: NOTABLE QUOTES BANK ───
    w("---")
    w()
    w("## 6. VERBATIM QUOTE BANK")
    w()
    w("### Best Closer Moments")
    w()
    for a in sales_calls:
        quote = a.get("notable_quotes", {}).get("best_closer_moment", "")
        if quote and len(quote) > 20:
            w(f"- **Call #{a['call_id']}** ({a.get('closer', '?')}, {a.get('prospect_name', '?')}): \"{quote}\"")
    w()

    w("### Strongest Buying Signals")
    w()
    for a in sales_calls:
        quote = a.get("notable_quotes", {}).get("prospect_buying_signal", "")
        if quote and len(quote) > 20:
            w(f"- **Call #{a['call_id']}** ({a.get('prospect_name', '?')}): \"{quote}\"")
    w()

    w("### Strongest Resistance Signals")
    w()
    for a in sales_calls:
        quote = a.get("notable_quotes", {}).get("prospect_resistance_signal", "")
        if quote and len(quote) > 20:
            w(f"- **Call #{a['call_id']}** ({a.get('prospect_name', '?')}): \"{quote}\"")
    w()

    # ─── SECTION 7: TOP IMPROVEMENTS ───
    w("---")
    w()
    w("## 7. TOP IMPROVEMENTS (Most Frequently Identified)")
    w()
    for i, (improvement, count) in enumerate(stats["top_improvements"].items(), 1):
        w(f"{i}. **({count}x)** {improvement}")
    w()

    # ─── SECTION 8: CALL-BY-CALL SCORECARDS ───
    w("---")
    w()
    w("## 8. CALL-BY-CALL SCORECARDS")
    w()
    w("| # | Prospect | Closer | Min | Outcome | Grade | Revenue | Biggest Improvement |")
    w("|---|---|---|---|---|---|---|---|")
    for a in sorted(analyses, key=lambda x: x.get("call_id", 0)):
        w(f"| {a.get('call_id', '?')} | {a.get('prospect_name', '?')[:20]} | {a.get('closer', '?')} | {a.get('duration_min', 0)} | {a.get('outcome', '?')} | {a.get('overall_grade', '?')} | ${a.get('revenue', 0):,.0f} | {a.get('biggest_improvement', '')[:60]} |")
    w()

    # ─── ERRORS ───
    if errors:
        w("---")
        w()
        w("## ERRORS (Calls that could not be analyzed)")
        w()
        for filename, error in errors:
            w(f"- {filename}: {error}")
        w()

    w("---")
    w()
    w(f"*Generated by compile_sales_audit.py on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats-only", action="store_true")
    args = parser.parse_args()

    print("Loading analyses...")
    analyses, errors = load_all_analyses()
    print(f"  Loaded {len(analyses)} analyses, {len(errors)} errors")

    if not analyses:
        print("ERROR: No analysis files found. Run analyze_sales_call.py first.")
        sys.exit(1)

    print("Computing statistics...")
    stats = compute_stats(analyses)

    # Save stats
    with open(STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"  Stats saved to {STATS_PATH}")

    if args.stats_only:
        print(f"\nClose rate: {format_pct(stats['close_rate'])}")
        print(f"Revenue: ${stats['total_revenue']:,.0f}")
        print(f"Sabbo: {stats['sabbo_closed']}/{stats['sabbo_calls']} ({format_pct(stats['sabbo_close_rate'])})")
        print(f"Rocky: {stats['rocky_closed']}/{stats['rocky_calls']} ({format_pct(stats['rocky_close_rate'])})")
        print(f"Top objection: {list(stats['objection_counts'].keys())[0] if stats['objection_counts'] else 'none'}")
        return

    print("Writing audit document...")
    doc = write_audit_document(analyses, stats, errors)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  Audit written to {OUTPUT_PATH}")
    print(f"  Document size: {len(doc):,} chars")

    # Quick summary
    print(f"\n{'='*60}")
    print(f"AUDIT COMPLETE")
    print(f"  Calls: {stats['total_calls']} ({stats['sales_calls']} sales, {stats['coaching_calls']} coaching)")
    print(f"  Close Rate: {format_pct(stats['close_rate'])}")
    print(f"  Revenue: ${stats['total_revenue']:,.0f}")
    print(f"  Avg Grade: {list(stats['grade_distribution'].keys())[0] if stats['grade_distribution'] else '?'}")
    print(f"  Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
