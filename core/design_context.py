"""
design_context.py
Distils raw Gemma frame-analysis JSON into a structured Design Context Block:
  - Color system (primary bg, text, accent, full palette)
  - Typography DNA
  - Animation pacing
  - Layout patterns
  - Mood arc
  - Scene templates per mood phase
  - Key design insights

The output can be:
  1. Saved as design_context.json
  2. Formatted as a Markdown block for injection into a planner prompt
  3. Both — and merged into the master kaizen output JSON
"""

import re
import json
from collections import Counter, defaultdict


# ── Normalisation helpers ─────────────────────────────────────────────────────

COLOR_ALIASES = {
    "white": "#ffffff", "black": "#000000", "yellow": "#ffff00",
    "red": "#ff0000", "gold": "#d4af37", "gray": "#808080",
    "grey": "#808080", "pink": "#ffb6c1", "blue": "#0000ff",
    "green": "#008000", "orange": "#ffa500", "purple": "#800080",
    "dark": "#1a1a1a", "light": "#f0f0f0", "transparent": "#00000000",
}

def _norm_color(c: str) -> str:
    c = c.strip().lower()
    if c in COLOR_ALIASES:
        return COLOR_ALIASES[c]
    if re.match(r'^#?[0-9a-f]{3,6}$', c):
        return ("#" + c.lstrip("#")).upper()
    return c


MOOD_GROUPS = {
    "neutral":    ["neutral", "neutral/void", "blank", "empty"],
    "analytical": ["analytical", "calm and analytical", "analytical and structured",
                   "modern and analytical", "educational", "informative", "instructive",
                   "clear and explanatory", "educational and structured"],
    "tension":    ["disorienting", "isolated", "monotonous", "expectant", "anticipatory",
                   "suspenseful", "urgent"],
    "revealing":  ["revealing", "awakening", "conceptual discovery", "enlightening",
                   "progressive", "evolving", "expanding", "discovery"],
    "epic":       ["epic", "philosophical and focused", "zen and evocative",
                   "serene and traditional", "energetic", "dynamic and explanatory",
                   "powerful", "bold"],
    "resolution": ["inspiring", "balanced", "balanced and complete", "introspective",
                   "minimalist and focused", "detailed and focusing", "transitional",
                   "geometric and abstract", "satisfying"],
    "direct":     ["direct", "punchy", "assertive"],
}

def _norm_mood(mood: str) -> str:
    m = mood.strip().lower()
    for group, members in MOOD_GROUPS.items():
        if m in members:
            return group
    return m


COMP_TO_LAYOUT = {
    "blank": "full-bleed", "centered": "centered", "center-aligned": "centered",
    "minimalist": "centered", "centrally": "centered", "typographic": "centered",
    "radially": "centered", "landscape": "grid", "layered depth": "overlay",
    "split": "split", "symmetrical": "split", "integrated": "overlay",
    "asymmetric": "overlay", "cropped": "overlay", "right-to-left": "split",
    "horizontal narrative": "split",
}

def _comp_to_layout(composition: str) -> str:
    c = composition.lower()
    for key, layout in COMP_TO_LAYOUT.items():
        if key in c:
            return layout
    return "centered"


ANIM_TO_ENTER = {
    "enter": "scale-in", "transition": "slide-up",
    "steady": "fade-in", "exit": "fade-out",
}

def _anim_to_enter(state: str) -> str:
    return ANIM_TO_ENTER.get(state, "fade-in")


def _focal_to_position(focal_point: str) -> dict:
    fp = focal_point.lower()
    h = "left" if "left" in fp else "right" if "right" in fp else "center"
    v = "top"  if any(w in fp for w in ["top","upper"]) else \
        "bottom" if any(w in fp for w in ["bottom","lower"]) else "middle"
    return {"horizontal": h, "vertical": v}


def _hex_brightness(h: str) -> float:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return 0.299 * r + 0.587 * g + 0.114 * b
    except Exception:
        return 128.0


# ── Core extraction ───────────────────────────────────────────────────────────

def _extract_all(visual_data: dict):
    """Single-pass collector over all scenes in the raw visual analysis."""
    scenes_raw = []
    for batch in visual_data.get("batches", []):
        scenes_raw.extend(batch.get("scenes", []))

    stats = defaultdict(list)
    temporal = []

    for s in scenes_raw:
        frame       = s.get("frame_index", 0)
        anim_state  = s.get("animation_state", "steady")
        layout_obj  = s.get("layout", {})
        composition = layout_obj.get("composition", "")
        focal_point = layout_obj.get("focal_point", "none")
        zones       = layout_obj.get("zones", [])
        colors      = [_norm_color(c) for c in s.get("color_palette", [])]
        design_note = s.get("design_notes", "")
        elements    = s.get("visual_elements", [])
        text_blocks = s.get("typography", {}).get("text_blocks", [])
        raw_mood    = s.get("mood", "")

        mood        = _norm_mood(raw_mood)
        layout      = _comp_to_layout(composition)
        enter_type  = _anim_to_enter(anim_state)
        position    = _focal_to_position(focal_point)

        stats["colors"].extend(colors)
        stats["moods"].append(mood)
        stats["raw_moods"].append(raw_mood)
        stats["anim_states"].append(anim_state)
        stats["layouts"].append(layout)
        stats["enter_types"].append(enter_type)
        stats["elements"].extend(elements)
        stats["design_notes"].append(design_note)
        for tb in text_blocks:
            stats["text_sizes"].append(tb.get("size"))
            stats["text_weights"].append(tb.get("weight"))

        temporal.append({
            "frame": frame,
            "mood_group": mood,
            "raw_mood": raw_mood,
            "anim_state": anim_state,
            "layout": layout,
            "enter_type": enter_type,
            "position": position,
            "composition": composition,
            "focal_point": focal_point,
            "colors": colors,
            "elements": elements[:4],
            "text_count": len(text_blocks),
            "design_notes": design_note,
            "n_zones": len(zones),
        })

    return dict(stats), temporal


# ── Public API ────────────────────────────────────────────────────────────────

def build_design_context(visual_data: dict, source_name: str = "analyzed_video") -> dict:
    """
    Distil raw frame-analysis JSON into a Design Context Block.

    Args:
        visual_data:  Output dict from visual_analyser.analyse_frames_visually().
        source_name:  Label to embed in the context block.

    Returns:
        Design context dict.
    """
    stats, temporal = _extract_all(visual_data)

    if not temporal:
        return {"source": source_name, "total_scenes_analyzed": 0, "error": "no scenes found"}

    # ── Color system ─────────────────────────────────────────────────────────
    color_counts = Counter(c for c in stats["colors"] if c.startswith("#"))
    top_colors   = [c for c, _ in color_counts.most_common(8)]

    dark   = sorted([c for c in top_colors if _hex_brightness(c) < 100],  key=lambda c: -color_counts[c])
    light  = sorted([c for c in top_colors if _hex_brightness(c) > 200],  key=lambda c: -color_counts[c])
    accent = sorted([c for c in top_colors if 100 <= _hex_brightness(c) <= 200], key=lambda c: -color_counts[c])

    color_system = {
        "primary_background": dark[0]   if dark   else "#0a0a0a",
        "primary_text":       light[0]  if light  else "#ffffff",
        "accent":             accent[0] if accent else (light[1] if len(light) > 1 else "#ffff00"),
        "supporting_dark":    dark[1]   if len(dark)  > 1 else "#1a1a1a",
        "supporting_light":   light[1]  if len(light) > 1 else "#cccccc",
        "full_palette":       top_colors,
    }

    # ── Typography ────────────────────────────────────────────────────────────
    size_dist   = Counter(s for s in stats["text_sizes"]   if s)
    weight_dist = Counter(w for w in stats["text_weights"] if w)
    typography  = {
        "dominant_size":       size_dist.most_common(1)[0][0]   if size_dist   else "medium",
        "dominant_weight":     weight_dist.most_common(1)[0][0] if weight_dist else "bold",
        "size_distribution":   dict(size_dist.most_common()),
        "weight_distribution": dict(weight_dist.most_common()),
        "heading_hint":        "xl" if size_dist.get("hero", 0) > 5 else "lg",
        "body_hint":           "sm" if size_dist.get("small", 0) > size_dist.get("medium", 0) else "md",
    }

    # ── Animation DNA ─────────────────────────────────────────────────────────
    anim_dist = Counter(stats["anim_states"])
    total     = len(temporal)
    animation_dna = {
        "steady_pct":     round(anim_dist.get("steady",     0) / total * 100),
        "transition_pct": round(anim_dist.get("transition", 0) / total * 100),
        "enter_pct":      round(anim_dist.get("enter",      0) / total * 100),
        "dominant_enter": Counter(stats["enter_types"]).most_common(1)[0][0],
        "distribution":   dict(anim_dist),
    }

    # ── Layout patterns ───────────────────────────────────────────────────────
    layout_dist = Counter(stats["layouts"])
    pos_dist    = Counter(
        f"{s['position']['horizontal']}-{s['position']['vertical']}"
        for s in temporal
    )
    layout_patterns = {
        "dominant_layout":       layout_dist.most_common(1)[0][0],
        "layout_distribution":   dict(layout_dist.most_common()),
        "dominant_focal_position": pos_dist.most_common(1)[0][0].replace("-", " "),
        "common_positions":      [p.replace("-", " ") for p, _ in pos_dist.most_common(3)],
    }

    # ── Mood architecture ─────────────────────────────────────────────────────
    mood_seq = [s["mood_group"] for s in temporal]
    mood_arc = []
    prev = None
    for m in mood_seq:
        if m != prev:
            mood_arc.append(m)
            prev = m

    mood_transitions: dict[str, list] = defaultdict(list)
    for i in range(len(mood_seq) - 1):
        mood_transitions[mood_seq[i]].append(mood_seq[i + 1])

    mood_architecture = {
        "arc":            mood_arc,
        "arc_simplified": mood_arc[:7],
        "dominant_mood":  Counter(stats["moods"]).most_common(1)[0][0],
        "mood_distribution": dict(Counter(stats["moods"]).most_common()),
        "transitions":    {k: Counter(v).most_common(2) for k, v in mood_transitions.items()},
        "opens_with":     mood_arc[0]  if mood_arc else "neutral",
        "closes_with":    mood_arc[-1] if mood_arc else "resolution",
    }

    # ── Visual elements ───────────────────────────────────────────────────────
    el_counts = Counter(stats["elements"])
    top_el    = el_counts.most_common(10)
    visual_elements = {
        "signature_elements": [e for e, c in top_el if c >= 2],
        "all_elements":       dict(top_el),
        "element_count":      len(el_counts),
    }

    # ── Scene patterns per mood phase ─────────────────────────────────────────
    mood_buckets: dict[str, list] = defaultdict(list)
    for s in temporal:
        mood_buckets[s["mood_group"]].append(s)

    scene_patterns = {}
    for mood, items in mood_buckets.items():
        layouts   = Counter(s["layout"]     for s in items)
        enters    = Counter(s["enter_type"] for s in items)
        positions = Counter(f"{s['position']['horizontal']}-{s['position']['vertical']}" for s in items)
        scene_patterns[mood] = {
            "typical_layout": layouts.most_common(1)[0][0],
            "typical_enter":  enters.most_common(1)[0][0],
            "typical_focal":  positions.most_common(1)[0][0].replace("-", " "),
            "avg_zones":       round(sum(s["n_zones"]    for s in items) / len(items), 1),
            "avg_text_elements": round(sum(s["text_count"] for s in items) / len(items), 1),
            "scene_count":    len(items),
        }

    # ── Design insights ───────────────────────────────────────────────────────
    insights = [n for n in stats["design_notes"] if n and len(n) > 30][:12]

    return {
        "source":                source_name,
        "total_scenes_analyzed": total,
        "color_system":          color_system,
        "typography":            typography,
        "animation_dna":         animation_dna,
        "layout_patterns":       layout_patterns,
        "mood_architecture":     mood_architecture,
        "visual_elements":       visual_elements,
        "scene_patterns":        scene_patterns,
        "design_insights":       insights,
    }


def format_as_markdown(context: dict) -> str:
    """
    Render the design context as a Markdown block ready for injection
    into a planner / reproduction LLM prompt.
    """
    c  = context
    cs = c.get("color_system", {})
    ty = c.get("typography", {})
    ad = c.get("animation_dna", {})
    lp = c.get("layout_patterns", {})
    ma = c.get("mood_architecture", {})
    ve = c.get("visual_elements", {})
    sp = c.get("scene_patterns", {})

    lines = [
        "## Reference Design System",
        f"*(Extracted from: {c['source']} — {c.get('total_scenes_analyzed', 0)} scenes analysed)*",
        "",
        "### Color System",
        f"- **Primary Background:** `{cs.get('primary_background','')}`",
        f"- **Primary Text:** `{cs.get('primary_text','')}`",
        f"- **Accent:** `{cs.get('accent','')}`",
        f"- **Supporting Dark:** `{cs.get('supporting_dark','')}`",
        f"- **Supporting Light:** `{cs.get('supporting_light','')}`",
        f"- **Full Palette:** {' · '.join(cs.get('full_palette', []))}",
        "",
        "### Typography",
        f"- **Dominant Size:** {ty.get('dominant_size','')} → heading `{ty.get('heading_hint','')}`, body `{ty.get('body_hint','')}`",
        f"- **Dominant Weight:** {ty.get('dominant_weight','')}",
        f"- **Size Distribution:** {' | '.join(f'{k}: {v}' for k,v in ty.get('size_distribution',{}).items())}",
        "",
        "### Animation DNA",
        f"- **Pacing:** {ad.get('steady_pct',0)}% steady · {ad.get('transition_pct',0)}% transition · {ad.get('enter_pct',0)}% enter",
        f"- **Dominant Enter Type:** `{ad.get('dominant_enter','')}`",
        f"- **Rule:** Use enter animations sparingly — most scenes prefer `fade-in` or `slide-up`",
        "",
        "### Layout Patterns",
        f"- **Dominant Layout:** `{lp.get('dominant_layout','')}`",
        f"- **Layout Mix:** {' · '.join(f'{k}: {v}' for k,v in lp.get('layout_distribution',{}).items())}",
        f"- **Primary Focal Position:** {lp.get('dominant_focal_position','')}",
        f"- **Common Focal Positions:** {' → '.join(lp.get('common_positions', []))}",
        "",
        "### Mood Architecture",
        f"- **Emotional Arc:** {' → '.join(ma.get('arc_simplified', []))}",
        f"- **Opens With:** `{ma.get('opens_with','')}` mood",
        f"- **Closes With:** `{ma.get('closes_with','')}` mood",
        "",
        "### Scene Patterns by Mood Phase",
        "Use these as templates when generating new scenes:",
        "",
    ]

    for mood, pattern in sp.items():
        lines += [
            f"**{mood.title()} phase** ({pattern['scene_count']} reference scenes)",
            f"  - Layout: `{pattern['typical_layout']}` | Enter: `{pattern['typical_enter']}`",
            f"  - Focal: `{pattern['typical_focal']}` | Avg text elements: {pattern['avg_text_elements']}",
            "",
        ]

    sigs = ve.get("signature_elements", [])
    if sigs:
        lines += [
            "### Signature Visual Elements",
            "*(Recurring elements — use as reusable components)*",
            *[f"  - {el}" for el in sigs],
            "",
        ]

    insights = c.get("design_insights", [])
    if insights:
        lines += [
            "### Key Design Insights",
            "*(Respect these patterns in new compositions)*",
            *[f"  - {note}" for note in insights[:8]],
            "",
        ]

    return "\n".join(lines)
