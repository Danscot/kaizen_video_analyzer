"""
pdf_exporter.py
Generates a detailed, well-formatted PDF creative brief from Kaizen analysis data.
Uses reportlab Platypus for layout — no emojis, all SVG-safe characters.
"""

import io
import time
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak,
)
from reportlab.platypus import Flowable

# ── Brand colours ──────────────────────────────────────────────────────────────
C_BG       = HexColor("#0d0d0f")
C_SURFACE  = HexColor("#1c1c23")
C_BORDER   = HexColor("#2a2a35")
C_VIOLET   = HexColor("#7c3aed")
C_AMBER    = HexColor("#e8920a")
C_GREEN    = HexColor("#0ea371")
C_TXT      = HexColor("#dddde8")
C_TXT2     = HexColor("#8888a0")
C_TXT3     = HexColor("#52526a")
C_WHITE    = white

W, H = A4
MARGIN_X = 18 * mm
MARGIN_Y = 16 * mm
CONTENT_W = W - 2 * MARGIN_X


# ── Styles ─────────────────────────────────────────────────────────────────────

def _styles():
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            textColor=C_WHITE,
            spaceAfter=6,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=C_TXT2,
            spaceAfter=4,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            fontName="Helvetica",
            fontSize=9,
            leading=14,
            textColor=C_TXT3,
        ),
        "section_head": ParagraphStyle(
            "section_head",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=C_TXT3,
            spaceBefore=18,
            spaceAfter=8,
            letterSpacing=1.2,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            leading=16,
            textColor=C_TXT,
            spaceAfter=6,
        ),
        "body_dim": ParagraphStyle(
            "body_dim",
            fontName="Helvetica",
            fontSize=10,
            leading=16,
            textColor=C_TXT2,
            spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=C_TXT3,
            spaceAfter=2,
            letterSpacing=0.8,
        ),
        "value": ParagraphStyle(
            "value",
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=C_TXT,
            spaceAfter=8,
        ),
        "mono": ParagraphStyle(
            "mono",
            fontName="Courier",
            fontSize=9,
            leading=14,
            textColor=C_TXT2,
            spaceAfter=4,
        ),
        "hook_type": ParagraphStyle(
            "hook_type",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=C_VIOLET,
            letterSpacing=0.8,
        ),
        "hook_body": ParagraphStyle(
            "hook_body",
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=C_TXT,
            spaceAfter=2,
        ),
        "hook_tech": ParagraphStyle(
            "hook_tech",
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=13,
            textColor=C_TXT3,
        ),
        "tag": ParagraphStyle(
            "tag",
            fontName="Courier",
            fontSize=8,
            leading=11,
            textColor=C_TXT2,
        ),
        "stat_val": ParagraphStyle(
            "stat_val",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=C_VIOLET,
        ),
        "stat_label": ParagraphStyle(
            "stat_label",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=C_TXT3,
            letterSpacing=0.6,
        ),
        "table_head": ParagraphStyle(
            "table_head",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=C_TXT3,
            letterSpacing=0.6,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=C_TXT2,
        ),
        "table_cell_hi": ParagraphStyle(
            "table_cell_hi",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=C_TXT,
        ),
    }


# ── Custom flowables ───────────────────────────────────────────────────────────

class DarkRect(Flowable):
    """Full-width dark background rectangle."""
    def __init__(self, height, color=None, radius=4):
        super().__init__()
        self.height = height
        self.color = color or C_SURFACE
        self.radius = radius

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.height

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.roundRect(0, 0, self.width, self.height, self.radius, fill=1, stroke=0)


class AccentLine(Flowable):
    """Left-border accent line (for hooks, messages)."""
    def __init__(self, color, height):
        super().__init__()
        self.color = color
        self.bh = height

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.bh

    def draw(self):
        self.canv.setFillColor(C_SURFACE)
        self.canv.rect(0, 0, self.width, self.bh, fill=1, stroke=0)
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, 3, self.bh, fill=1, stroke=0)


class ColorSwatch(Flowable):
    """Inline color swatch chip."""
    def __init__(self, hex_color, label, size=10):
        super().__init__()
        self.hex = hex_color
        self.label = label
        self.size = size
        self.row_h = size + 4

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.row_h

    def draw(self):
        try:
            c = HexColor(self.hex)
        except Exception:
            c = C_SURFACE
        self.canv.setFillColor(c)
        self.canv.roundRect(0, 2, self.size, self.size, 2, fill=1, stroke=0)
        self.canv.setFillColor(C_TXT2)
        self.canv.setFont("Courier", 8)
        self.canv.drawString(self.size + 6, 4, f"{self.hex}  {self.label}")


class BarChart(Flowable):
    """Horizontal bar chart for animation DNA."""
    def __init__(self, rows, total_h=None):
        super().__init__()
        self.rows = rows   # [(label, pct, color_hex)]
        self.row_h = 18
        self.total_h = total_h or len(rows) * self.row_h

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.total_h

    def draw(self):
        label_w = 70
        bar_w   = self.width - label_w - 40
        y       = self.total_h - self.row_h
        for label, pct, color in self.rows:
            self.canv.setFont("Helvetica", 8)
            self.canv.setFillColor(C_TXT2)
            self.canv.drawString(0, y + 4, label)
            # bg
            self.canv.setFillColor(C_SURFACE)
            self.canv.roundRect(label_w, y + 3, bar_w, 8, 2, fill=1, stroke=0)
            # fill
            fill = max(2, int(bar_w * pct / 100))
            try:
                fc = HexColor(color)
            except Exception:
                fc = C_VIOLET
            self.canv.setFillColor(fc)
            self.canv.roundRect(label_w, y + 3, fill, 8, 2, fill=1, stroke=0)
            # pct label
            self.canv.setFillColor(C_TXT3)
            self.canv.setFont("Courier", 8)
            self.canv.drawString(label_w + bar_w + 5, y + 4, f"{pct}%")
            y -= self.row_h


# ── Section divider ────────────────────────────────────────────────────────────

def _section(title, st):
    return [
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6),
        Paragraph(title.upper(), st["section_head"]),
    ]


def _kv(label, value, st):
    if not value:
        return []
    return [
        Paragraph(label.upper(), st["label"]),
        Paragraph(str(value), st["value"]),
    ]


def _stat_row(items, st):
    """Render a horizontal stat row as a table."""
    cells = []
    for label, val, color in items:
        try:
            col = HexColor(color) if color else C_VIOLET
        except Exception:
            col = C_VIOLET
        cells.append([
            Paragraph(str(val or "—"), ParagraphStyle(
                "sv", fontName="Helvetica-Bold", fontSize=15,
                leading=18, textColor=col,
            )),
            Paragraph(label.upper(), ParagraphStyle(
                "sl", fontName="Helvetica", fontSize=7,
                leading=10, textColor=C_TXT3, letterSpacing=0.6,
            )),
        ])
    col_w = CONTENT_W / len(items)
    tbl = Table(
        [cells],
        colWidths=[col_w] * len(items),
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_SURFACE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_SURFACE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [6]),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, C_BORDER),
    ]))
    return [tbl, Spacer(1, 3 * mm)]


# ── Cover page ─────────────────────────────────────────────────────────────────

def _cover(story, data, st):
    meta     = data.get("meta", {})
    analysis = data.get("analysis") or data.get("content_analysis") or {}
    title    = analysis.get("title") or meta.get("source", "Untitled")
    niche    = analysis.get("niche", "")
    platform = analysis.get("platform_style", "")
    ts       = meta.get("analysed_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    # Dark cover block
    cover_tbl = Table(
        [[
            Paragraph("KAIZEN", ParagraphStyle(
                "brand", fontName="Helvetica-Bold", fontSize=9,
                leading=12, textColor=C_VIOLET, letterSpacing=2,
            )),
            Paragraph("VIDEO ANALYST", ParagraphStyle(
                "brand2", fontName="Helvetica", fontSize=9,
                leading=12, textColor=C_TXT3, letterSpacing=1.5,
            )),
        ]],
        colWidths=[60, CONTENT_W - 60],
    )
    cover_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    story += [
        cover_tbl,
        Spacer(1, 12 * mm),
        HRFlowable(width="100%", thickness=0.5, color=C_VIOLET, spaceAfter=10),
        Paragraph(title, st["cover_title"]),
        Spacer(1, 2 * mm),
    ]

    if niche or platform:
        badges = "  /  ".join(filter(None, [niche, platform]))
        story.append(Paragraph(badges, st["cover_sub"]))

    story += [
        Spacer(1, 6 * mm),
        Paragraph(f"Analysis generated: {ts}", st["cover_meta"]),
        Paragraph(f"Source: {meta.get('source', '—')}", st["cover_meta"]),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=0),
    ]


# ── Content analysis sections ──────────────────────────────────────────────────

def _content_sections(story, analysis, transcript, st):
    cs  = analysis.get("content_structure") or {}
    rn  = analysis.get("reproduction_notes") or {}
    cta = analysis.get("cta") or {}

    # Stats row
    story += _section("Overview", st)
    story += _stat_row([
        ("Duration", f"~{analysis.get('duration_estimate','?')}s", "#7c3aed"),
        ("Pacing",   cs.get("pacing", "—"),                        "#e8920a"),
        ("Language", analysis.get("language", "—"),                 "#0ea371"),
        ("Complexity", rn.get("estimated_complexity","—"),           "#7c3aed"),
    ], st)

    story += _kv("Summary", analysis.get("summary"), st)
    story += _kv("Core Message", analysis.get("core_message"), st)
    story += _kv("Target Audience", analysis.get("target_audience"), st)
    story += _kv("Format", cs.get("format"), st)

    # Narrative arc
    if cs.get("pattern"):
        story += _section("Narrative Arc", st)
        arc_parts = [p.strip() for p in cs["pattern"].replace("→", ">").split(">")]
        arc_str   = "  >  ".join(arc_parts)
        story.append(Paragraph(arc_str, st["body_dim"]))

    # Hooks
    hooks = analysis.get("hooks") or []
    if hooks:
        story += _section(f"Hooks  ({len(hooks)} detected)", st)
        for hk in hooks:
            block = [
                Paragraph((hk.get("type") or "hook").upper(), st["hook_type"]),
                Spacer(1, 1 * mm),
                Paragraph(hk.get("timestamp_estimate") or "", st["mono"]),
                Paragraph(hk.get("content") or "", st["hook_body"]),
                Paragraph(hk.get("technique") or "", st["hook_tech"]),
                Spacer(1, 2 * mm),
            ]
            story.append(KeepTogether(block))

    # Emotional journey
    ej = analysis.get("emotional_journey") or []
    if ej:
        story += _section("Emotional Journey", st)
        rows = [["Phase", "Timestamp", "Trigger"]]
        for e in ej:
            rows.append([
                Paragraph(e.get("phase","—"), st["table_cell_hi"]),
                Paragraph(e.get("timestamp_estimate","—"), st["mono"]),
                Paragraph(e.get("trigger","—"), st["table_cell"]),
            ])
        tbl = Table(rows, colWidths=[60, 55, CONTENT_W - 115])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_BORDER),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_TXT3),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("LETTERSPACEING", (0, 0), (-1, 0), 0.8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_SURFACE, C_BG]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("ROUNDEDCORNERS", [4]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 3 * mm))

    # Scenes
    scenes = analysis.get("scenes") or []
    if scenes:
        story += _section(f"Scene Breakdown  ({len(scenes)} scenes)", st)
        rows = [["#", "Timestamp", "Purpose", "Tone", "Description"]]
        for s in scenes:
            desc = (s.get("description") or "")[:80]
            if len(s.get("description") or "") > 80:
                desc += "..."
            rows.append([
                Paragraph(str(s.get("scene_number", "")), st["table_cell_hi"]),
                Paragraph(s.get("timestamp_estimate","—"), st["mono"]),
                Paragraph(s.get("purpose","—"), st["table_cell"]),
                Paragraph(s.get("tone","—"), ParagraphStyle(
                    "tone_s", fontName="Helvetica", fontSize=9,
                    leading=13, textColor=C_AMBER,
                )),
                Paragraph(desc, st["table_cell"]),
            ])
        tbl = Table(rows, colWidths=[18, 50, 55, 50, CONTENT_W - 173])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_BORDER),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_SURFACE, C_BG]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 3 * mm))

        # B-roll notes
        story += _section("B-Roll & Scene Notes", st)
        for s in scenes:
            if s.get("b_roll_suggestion"):
                story.append(Paragraph(
                    f"<b>Scene {s.get('scene_number','')}:</b>  {s['b_roll_suggestion']}",
                    st["body_dim"],
                ))

    # CTA
    if cta.get("type") or cta.get("exists"):
        story += _section("Call to Action", st)
        story += _kv("Type", cta.get("type"), st)
        story += _kv("Content", cta.get("content"), st)
        story += _kv("Placement", cta.get("placement"), st)

    # Reproduction notes
    if rn:
        story += _section("Reproduction Notes", st)
        story += _kv("Tone Guide", rn.get("tone_guide"), st)
        story += _kv("Visual Style", rn.get("visual_style"), st)
        story += _kv("Music Suggestion", rn.get("music_suggestion"), st)
        els = rn.get("essential_elements") or []
        if els:
            story.append(Paragraph("ESSENTIAL ELEMENTS", st["label"]))
            for el in els:
                story.append(Paragraph(f"  -  {el}", st["body_dim"]))
            story.append(Spacer(1, 3 * mm))

    # Keywords
    kws = analysis.get("keywords_and_topics") or []
    if kws:
        story += _section("Keywords & Topics", st)
        story.append(Paragraph("  |  ".join(kws), st["mono"]))
        story.append(Spacer(1, 2 * mm))

    # Transcript
    if transcript:
        story.append(PageBreak())
        story += _section("Full Transcript", st)
        lines = transcript.split("\n")
        for line in lines[:120]:   # cap at 120 lines to avoid enormous PDFs
            story.append(Paragraph(line, st["mono"]))
        if len(lines) > 120:
            story.append(Paragraph(f"... ({len(lines)-120} more lines truncated)", st["body_dim"]))


# ── Visual / design context sections ──────────────────────────────────────────

def _visual_sections(story, dc, st):
    cs  = dc.get("color_system") or {}
    ty  = dc.get("typography") or {}
    ad  = dc.get("animation_dna") or {}
    lp  = dc.get("layout_patterns") or {}
    ma  = dc.get("mood_architecture") or {}
    ve  = dc.get("visual_elements") or {}
    sp  = dc.get("scene_patterns") or {}
    ins = dc.get("design_insights") or []

    story += _section("Visual Overview", st)
    story += _stat_row([
        ("Scenes Analysed", dc.get("total_scenes_analyzed","—"), "#7c3aed"),
        ("Dominant Mood",   ma.get("dominant_mood","—"),          "#0ea371"),
        ("Dominant Layout", lp.get("dominant_layout","—"),        "#e8920a"),
        ("Enter Anim",      ad.get("dominant_enter","—"),         "#7c3aed"),
    ], st)

    # Color system
    story += _section("Color System", st)
    color_rows = [
        (cs.get("primary_background",""), "Primary Background"),
        (cs.get("primary_text",""),       "Primary Text"),
        (cs.get("accent",""),             "Accent"),
        (cs.get("supporting_dark",""),    "Supporting Dark"),
    ]
    for hex_c, label in color_rows:
        if hex_c:
            story.append(ColorSwatch(hex_c, label))
    story.append(Spacer(1, 2 * mm))

    pal = cs.get("full_palette") or []
    if pal:
        story.append(Paragraph("FULL PALETTE", st["label"]))
        story.append(Paragraph("  ".join(pal), st["mono"]))
        story.append(Spacer(1, 3 * mm))

    # Typography
    story += _section("Typography", st)
    story += _kv("Dominant Size",   ty.get("dominant_size"), st)
    story += _kv("Dominant Weight", ty.get("dominant_weight"), st)
    story += _kv("Heading Hint",    ty.get("heading_hint"), st)
    story += _kv("Body Hint",       ty.get("body_hint"), st)

    # Animation DNA
    story += _section("Animation DNA", st)
    bars = [
        ("Steady",      ad.get("steady_pct", 0),     "#0ea371"),
        ("Transition",  ad.get("transition_pct", 0), "#7c3aed"),
        ("Enter",       ad.get("enter_pct", 0),      "#e8920a"),
    ]
    story.append(BarChart(bars, total_h=len(bars) * 18 + 4))
    story.append(Spacer(1, 2 * mm))

    # Mood arc
    arc = ma.get("arc_simplified") or []
    if arc:
        story += _section("Emotional Arc", st)
        story.append(Paragraph("  >  ".join(arc), st["body_dim"]))
        story += _kv("Opens With", ma.get("opens_with"), st)
        story += _kv("Closes With", ma.get("closes_with"), st)

    # Scene patterns
    if sp:
        story += _section("Scene Patterns by Mood Phase", st)
        rows = [["Phase", "Layout", "Enter", "Focal Point", "Avg Text", "Count"]]
        for mood, p in sp.items():
            rows.append([
                Paragraph(mood, st["table_cell_hi"]),
                Paragraph(p.get("typical_layout","—"), st["mono"]),
                Paragraph(p.get("typical_enter","—"),  st["mono"]),
                Paragraph(p.get("typical_focal","—"),  st["table_cell"]),
                Paragraph(str(p.get("avg_text_elements",0)), st["table_cell"]),
                Paragraph(str(p.get("scene_count",0)), st["table_cell"]),
            ])
        col_w = CONTENT_W / 6
        tbl = Table(rows, colWidths=[col_w] * 6)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), C_BORDER),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 7),
            ("ROWBACKGROUNDS",(0, 1), (-1,-1), [C_SURFACE, C_BG]),
            ("LEFTPADDING",   (0, 0), (-1,-1), 6),
            ("RIGHTPADDING",  (0, 0), (-1,-1), 6),
            ("TOPPADDING",    (0, 0), (-1,-1), 5),
            ("BOTTOMPADDING", (0, 0), (-1,-1), 5),
            ("LINEBELOW",     (0, 0), (-1,-1), 0.3, C_BORDER),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 3 * mm))

    # Signature elements
    sigs = ve.get("signature_elements") or []
    if sigs:
        story += _section("Signature Visual Elements", st)
        story.append(Paragraph("  |  ".join(sigs), st["mono"]))
        story.append(Spacer(1, 2 * mm))

    # Design insights
    if ins:
        story += _section("Design Insights", st)
        for n in ins:
            story.append(Paragraph(f"-  {n}", st["body_dim"]))
        story.append(Spacer(1, 2 * mm))

    # Planner markdown
    md = dc.get("planner_markdown") or ""
    if md:
        story.append(PageBreak())
        story += _section("Planner Context Block (Markdown)", st)
        for line in md.split("\n")[:150]:
            story.append(Paragraph(line or " ", st["mono"]))


# ── Background canvas (dark pages) ────────────────────────────────────────────

def _dark_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # Footer
    canvas.setFillColor(C_TXT3)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN_X, 8 * mm, "Kaizen Video Analyst")
    canvas.drawRightString(W - MARGIN_X, 8 * mm, f"Page {doc.page}")
    # Footer line
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_X, 12 * mm, W - MARGIN_X, 12 * mm)
    canvas.restoreState()


# ── Public API ─────────────────────────────────────────────────────────────────

def export_pdf(data: dict, track: str = "content") -> bytes:
    """
    Generate a PDF brief from analysis data.

    Args:
        data:   The full result dict (as stored in the JSON output file).
        track:  'content' | 'visual' | 'full'

    Returns:
        Raw PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=MARGIN_Y,  bottomMargin=18 * mm,
        title="Kaizen Video Analysis Brief",
        author="Kaizen Video Analyst",
    )

    st    = _styles()
    story = []

    # Cover
    _cover(story, data, st)
    story.append(Spacer(1, 6 * mm))

    # Content track
    analysis   = data.get("analysis") or data.get("content_analysis") or {}
    transcript = data.get("transcript", "")
    if analysis and track in ("content", "full"):
        _content_sections(story, analysis, transcript, st)

    # Visual track
    dc = data.get("design_context") or {}
    if dc and track in ("visual", "full"):
        if analysis:   # separate from content with a page break
            story.append(PageBreak())
            story += [
                Paragraph("VISUAL / MOTION ANALYSIS", ParagraphStyle(
                    "vis_hd", fontName="Helvetica-Bold", fontSize=14,
                    leading=18, textColor=C_AMBER, spaceBefore=6, spaceAfter=4,
                )),
            ]
        _visual_sections(story, dc, st)

    doc.build(story, onFirstPage=_dark_page, onLaterPages=_dark_page)
    return buf.getvalue()
