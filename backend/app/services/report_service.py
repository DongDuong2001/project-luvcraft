"""Deterministic PDF reports rendered exclusively from persisted synthesis data."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import settings
from app.models.evaluation import GeneratedReport

REPORT_TYPES = {"executive", "case_study"}

def _text(value: object, fallback: str = "Unavailable") -> str:
    if value is None or value == "":
        return fallback
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

class ReportGeneratorService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = Path(storage_path or settings.REPORT_STORAGE_PATH).resolve()

    def generate(self, *, run_id: UUID, keyword: str, report_type: str, content: dict) -> GeneratedReport:
        if report_type not in REPORT_TYPES:
            raise ValueError("unsupported report type")
        report_id = uuid4()
        directory = self.storage_path / str(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{report_type}-{report_id}.pdf"
        fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
        self._render(path, keyword, report_type, content)
        return GeneratedReport(report_id=report_id, run_id=run_id, report_type=report_type,
            file_path=str(path), file_size_bytes=path.stat().st_size, status="completed",
            methodology_version=str(content.get("structured_result", {}).get("methodology_version", "luvcraft-analytics-v1")),
            input_fingerprint=fingerprint, generated_at=datetime.now(timezone.utc))

    def safe_path(self, report: GeneratedReport) -> Path:
        path = Path(report.file_path).resolve()
        if self.storage_path not in path.parents or not path.is_file():
            raise FileNotFoundError("report file is unavailable")
        return path

    def _render(self, path: Path, keyword: str, report_type: str, content: dict) -> None:
        if report_type == "executive":
            self._render_executive_slide_deck(path, keyword, content)
        else:
            self._render_case_study_report(path, keyword, content)

    def _render_executive_slide_deck(self, path: Path, keyword: str, content: dict) -> None:
        """Render a landscape slide-based presentation deck (1 insight theme per slide)."""
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            str(path),
            pagesize=landscape(A4),
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            pageCompression=0,
            title=f"Executive Statistical Brief: {keyword}",
        )
        methodology = content.get("methodology_details", {})
        confidence = content.get("cross_source_confidence", {})
        community = content.get("community_analysis", {})
        motivations = content.get("motivation_analysis", {})
        demand = content.get("demand_analysis", {})
        themes = content.get("narrative_theme_analysis", {})
        warnings = content.get("structured_result", {}).get("warnings", [])
        version = content.get("structured_result", {}).get("methodology_version", "luvcraft-analytics-v1")

        story = []

        # SLIDE 1: Title & Executive KPI Overview
        story.append(Paragraph("Executive Statistical Brief", styles["Title"]))
        story.append(Paragraph(f"Subject: {_text(keyword)}", styles["Heading1"]))
        story.append(
            Paragraph(
                f"Analysis timeframe: {_text(methodology.get('timeframe_start'))} to {_text(methodology.get('timeframe_end'))} &nbsp;|&nbsp; "
                f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} &nbsp;|&nbsp; "
                f"Contributing sources: {_text(content.get('source_count'), '0')} independent platforms",
                styles["BodyText"],
            )
        )
        story.append(Spacer(1, 10))

        metrics = [
            ["Overall Sentiment", "Sentiment Score", "Cross-Source Agreement", "Signals Analyzed", "Community Toxicity", "Trend Momentum"],
            [
                _text(content.get("overall_sentiment")),
                f"{_text(content.get('sentiment_score'))} / 100",
                _text(confidence.get("score"), "Insufficient sources"),
                f"{_text(content.get('signal_count'), '0')} signals",
                _text(community.get("toxicity_level"), "Low"),
                _text(content.get("trend_momentum")),
            ],
        ]
        table = Table(metrics, colWidths=[43 * mm, 43 * mm, 45 * mm, 43 * mm, 43 * mm, 43 * mm])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0F172A")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 11),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(table)
        story.append(Spacer(1, 12))
        story.append(Paragraph("Presentation Outline:", styles["Heading3"]))
        story.append(Paragraph("1. Sentiment & Source Distribution &nbsp;&bull;&nbsp; 2. Discussion Momentum & Regional Breakdown &nbsp;&bull;&nbsp; 3. Themes & Demand Signals &nbsp;&bull;&nbsp; 4. Strategic Actions", styles["BodyText"]))
        story.append(PageBreak())

        # SLIDE 2: Sentiment Distribution & Source Contributions
        story.append(Paragraph("Sentiment distribution &amp; source contribution", styles["Heading1"]))
        story.append(Paragraph("Balanced cross-platform sentiment breakdown and verified independent signal counts.", styles["Normal"]))
        story.append(Spacer(1, 8))
        chart_table = Table([[self._sentiment_chart(content, width=340), self._source_chart(content, width=340)]], colWidths=[130 * mm, 130 * mm])
        chart_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(chart_table)
        story.append(PageBreak())

        # SLIDE 3: Trend Momentum & Regional Intelligence
        story.append(Paragraph("Discussion Momentum &amp; Regional Intelligence", styles["Heading1"]))
        story.append(Paragraph(f"Overall momentum: {_text(content.get('trend_momentum'))} &nbsp;|&nbsp; Trend score: {_text(content.get('trend_score'))} &nbsp;|&nbsp; Statistical anomalies detected: {_text(len(content.get('anomaly_alerts', [])), '0')}", styles["Normal"]))
        story.append(Spacer(1, 8))
        trend_geo_table = Table([[self._trend_chart(content, width=340), self._geo_chart(content, width=340)]], colWidths=[130 * mm, 130 * mm])
        trend_geo_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(trend_geo_table)
        story.append(PageBreak())

        # SLIDE 4: Community Drivers, Narrative Themes & Demand Signals
        story.append(Paragraph("Narrative Themes, Praise Drivers &amp; Demand Signals", styles["Heading1"]))
        story.append(Spacer(1, 6))
        theme_items = themes.get("themes", [])[:4]
        demand_items = demand.get("demands", [])[:4]
        praise_items = (motivations.get("praise", []) + motivations.get("likes", []))[:4]
        complaint_items = (motivations.get("complaints", []) + motivations.get("unmet_expectations", []))[:4]

        theme_text = "<br/>".join([f"• <b>{_text(t.get('label'))}</b> ({_text(t.get('prevalence_percentage', 0))}% prevalence)" for t in theme_items] or ["• Insufficient stored evidence."])
        demand_text = "<br/>".join([f"• <b>{_text(d.get('request'))}</b> ({_text(d.get('mention_count', 0))} mentions)" for d in demand_items] or ["• Insufficient stored evidence."])
        praise_text = "<br/>".join([f"• {_text(p.get('topic'))}" for p in praise_items] or ["• Insufficient stored evidence."])
        complaint_text = "<br/>".join([f"• {_text(c.get('topic'))}" for c in complaint_items] or ["• Insufficient stored evidence."])

        insights_grid = [
            [Paragraph("<b>Top Narrative Themes</b>", styles["Heading3"]), Paragraph("<b>Explicit Demand Signals</b>", styles["Heading3"])],
            [Paragraph(theme_text, styles["BodyText"]), Paragraph(demand_text, styles["BodyText"])],
            [Paragraph("<b>Key Praise Drivers</b>", styles["Heading3"]), Paragraph("<b>Common Complaints &amp; Risks</b>", styles["Heading3"])],
            [Paragraph(praise_text, styles["BodyText"]), Paragraph(complaint_text, styles["BodyText"])],
        ]
        grid_table = Table(insights_grid, colWidths=[130 * mm, 130 * mm])
        grid_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EFF6FF")),
            ("BACKGROUND", (0, 2), (0, 2), colors.HexColor("#F0FDF4")),
            ("BACKGROUND", (1, 2), (1, 2), colors.HexColor("#FEF2F2")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(grid_table)
        story.append(PageBreak())

        # SLIDE 5: Strategic Decisions & Action Plan
        story.append(Paragraph("Strategic Opportunities &amp; Action Items", styles["Heading1"]))
        story.append(Spacer(1, 8))
        story.append(Paragraph("<b>Recommended Actions:</b>", styles["Heading3"]))
        story.append(Paragraph(self._recommendations(content), styles["BodyText"]))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Limitations &amp; Data Provenance:</b>", styles["Heading3"]))
        story.append(
            Paragraph(
                f"Methodology version: {_text(version)} &nbsp;|&nbsp; "
                f"Warnings: {_text('; '.join(warnings) if warnings else 'None')} &nbsp;|&nbsp; "
                "Data is grounded entirely in stored signals without synthetic extrapolation.",
                styles["BodyText"],
            )
        )
        doc.build(story, onFirstPage=self._page_number, onLaterPages=self._page_number)

    def _render_case_study_report(self, path: Path, keyword: str, content: dict) -> None:
        """Render a portrait narrative-style case study document for in-depth analysis."""
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            pageCompression=0,
            title=f"Structured Fandom Case Study: {keyword}",
        )
        methodology = content.get("methodology_details", {})
        confidence = content.get("cross_source_confidence", {})
        community = content.get("community_analysis", {})
        motivations = content.get("motivation_analysis", {})
        demand = content.get("demand_analysis", {})
        themes = content.get("narrative_theme_analysis", {})
        warnings = content.get("structured_result", {}).get("warnings", [])
        version = content.get("structured_result", {}).get("methodology_version", "luvcraft-analytics-v1")

        story = [
            Paragraph("Structured Fandom Case Study", styles["Title"]),
            Paragraph(f"Subject: {_text(keyword)}", styles["Heading2"]),
            Paragraph(
                f"Analysis timeframe: {_text(methodology.get('timeframe_start'))} to {_text(methodology.get('timeframe_end'))}<br/>"
                f"Generated: {datetime.now(timezone.utc).isoformat()}<br/>"
                f"Source scope: {_text(content.get('source_count'), '0')} independent sources",
                styles["BodyText"],
            ),
            Spacer(1, 8),
        ]

        metrics = [
            ["Sentiment", _text(content.get("overall_sentiment"))],
            ["Sentiment score", _text(content.get("sentiment_score"))],
            ["Cross-source confidence", _text(confidence.get("score"), "Insufficient sources")],
            ["Signals / Sources", f"{_text(content.get('signal_count'), '0')} / {_text(content.get('source_count'), '0')}"],
            ["Community toxicity", _text(community.get("toxicity_level"))],
            ["Trend momentum", _text(content.get("trend_momentum"))],
        ]
        table = Table(metrics, colWidths=[60 * mm, 100 * mm])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8E5FF")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.extend([table, Spacer(1, 10)])

        contents = [
            "Background and research objectives",
            "Sentiment distribution and source metrics",
            "Discussion momentum and regional breakdown",
            "Community posture and motivations",
            "Explicit demand and narrative themes",
            "Representative evidence excerpts",
            "Strategic opportunities and recommendations",
            "Methodology and reproducibility appendix",
        ]
        story.extend([
            Paragraph("Table of contents", styles["Heading2"]),
            Paragraph("<br/>".join(f"{index}. {_text(item)}" for index, item in enumerate(contents, 1)), styles["BodyText"]),
            Spacer(1, 10),
            Paragraph("Background and research objectives", styles["Heading2"]),
            Paragraph(
                "This report delivers structured market intelligence and fandom insight for the requested subject, "
                "combining multi-platform data collection with qualitative synthesis. It reflects observable audience discussions "
                "without synthetic demographic extrapolation.",
                styles["BodyText"],
            ),
            Spacer(1, 8),
            Paragraph("Sentiment distribution", styles["Heading2"]),
            self._sentiment_chart(content, width=420),
            Spacer(1, 8),
            Paragraph("Engagement and volume", styles["Heading2"]),
            Paragraph(
                f"The persisted run contains {_text(content.get('signal_count'), '0')} usable signals across "
                f"{_text(content.get('source_count'), '0')} contributing sources.",
                styles["BodyText"],
            ),
            self._source_chart(content, width=420),
            Paragraph("Trend and momentum", styles["Heading2"]),
            Paragraph(
                f"Overall momentum: {_text(content.get('trend_momentum'))}. Trend score: {_text(content.get('trend_score'))}. "
                f"Statistical anomaly count: {_text(len(content.get('anomaly_alerts', [])), '0')}.",
                styles["BodyText"],
            ),
            self._trend_chart(content, width=420),
            Paragraph("Regional comparison", styles["Heading2"]),
            Paragraph(
                "Regional findings are included only when stored collector location data is sufficient.",
                styles["BodyText"],
            ),
            self._geo_chart(content, width=420),
            Spacer(1, 8),
        ])

        sections = [
            ("Evidence-derived narrative themes", themes.get("themes", []), "label"),
            ("Explicit demand signals", demand.get("demands", []), "request"),
            ("Frequently asked questions", demand.get("frequently_asked_questions", []), "question"),
            ("Praise and likes", motivations.get("praise", []) + motivations.get("likes", []), "topic"),
            ("Complaints and unmet expectations", motivations.get("complaints", []) + motivations.get("unmet_expectations", []), "topic"),
        ]
        for heading, rows, key in sections:
            story.append(Paragraph(heading, styles["Heading2"]))
            if rows:
                for row in rows[:10]:
                    count = row.get("mention_count", "?")
                    story.append(Paragraph(f"• {_text(row.get(key))} (evidence mentions: {_text(count)})", styles["BodyText"]))
            else:
                story.append(Paragraph("Insufficient stored evidence.", styles["BodyText"]))
            story.append(Spacer(1, 6))

        story.extend([
            Paragraph("Representative evidence excerpts", styles["Heading2"]),
            *(
                [Paragraph(f"[{_text(item.get('signal_id'))}] {_text(item.get('excerpt'))}", styles["BodyText"]) for item in content.get("report_evidence", [])[:10]]
                or [Paragraph("No stored excerpts were available.", styles["BodyText"])]
            ),
            Spacer(1, 8),
            Paragraph("Strategic opportunities and recommended actions", styles["Heading2"]),
            Paragraph(self._recommendations(content), styles["BodyText"]),
            Spacer(1, 8),
            Paragraph("Methodology appendix", styles["Heading2"]),
            Paragraph(_text(json.dumps(methodology, sort_keys=True)), styles["Code"]),
            Paragraph("Risks, limitations, and methodology", styles["Heading2"]),
            Paragraph(
                f"Version: {_text(version)}. Results use stored signals only. Warnings: {_text('; '.join(warnings) if warnings else 'None')}",
                styles["BodyText"],
            ),
        ])
        doc.build(story, onFirstPage=self._page_number, onLaterPages=self._page_number)

    @staticmethod
    def _bar_chart(values: list[float], labels: list[str], title: str, width: int = 420) -> Drawing:
        drawing = Drawing(width, 180)
        drawing.add(String(10, 162, title, fontName="Helvetica-Bold", fontSize=10))
        chart = VerticalBarChart()
        chart.x = 35
        chart.y = 30
        chart.height = 120
        chart.width = width - 60
        chart.data = [values or [0]]
        chart.categoryAxis.categoryNames = labels or ["Unavailable"]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(100, max(values or [0]))
        chart.bars[0].fillColor = colors.HexColor("#536DFE")
        drawing.add(chart)
        return drawing

    def _sentiment_chart(self, content: dict, width: int = 420) -> Drawing:
        sources = content.get("cross_source_confidence", {}).get("sources", [])
        if not sources:
            return self._bar_chart([], [], "Sentiment distribution unavailable", width=width)
        values = [
            sum(float(row.get(key, 0)) for row in sources) / len(sources)
            for key in ("positive_percentage", "neutral_percentage", "negative_percentage")
        ]
        return self._bar_chart(values, ["Positive", "Neutral", "Negative"], "Source-balanced sentiment (%)", width=width)

    def _source_chart(self, content: dict, width: int = 420) -> Drawing:
        rows = content.get("cross_source_confidence", {}).get("sources", [])[:8]
        return self._bar_chart(
            [float(row.get("usable_signal_count", 0)) for row in rows],
            [str(row.get("source", "?"))[:12] for row in rows],
            "Usable signals by independent source",
            width=width,
        )

    def _geo_chart(self, content: dict, width: int = 420) -> Drawing:
        rows = content.get("geo_comparison", [])[:8]
        return self._bar_chart(
            [float(row.get("signal_count", 0)) for row in rows],
            [str(row.get("country_code", "?")) for row in rows],
            "Signals by collector region",
            width=width,
        )

    def _trend_chart(self, content: dict, width: int = 420) -> Drawing:
        points = content.get("trend_data", [])
        values = [float(point.get("volume", point.get("value", 0))) for point in points if isinstance(point, dict)][:20]
        if len(values) < 2:
            return self._bar_chart([], [], "Insufficient history for time-series movement", width=width)
        drawing = Drawing(width, 180)
        drawing.add(String(10, 162, "Discussion volume over time", fontName="Helvetica-Bold", fontSize=10))
        chart = HorizontalLineChart()
        chart.x = 35
        chart.y = 30
        chart.height = 120
        chart.width = width - 60
        chart.data = [values]
        chart.categoryAxis.categoryNames = [str(index + 1) for index in range(len(values))]
        chart.lines[0].strokeColor = colors.HexColor("#536DFE")
        drawing.add(chart)
        return drawing

    @staticmethod
    def _recommendations(content: dict) -> str:
        demands = content.get("demand_analysis", {}).get("demands", [])
        themes = content.get("narrative_theme_analysis", {}).get("themes", [])
        actions = [f"Validate and prioritize demand '{item.get('request')}' ({item.get('mention_count', 0)} mentions)." for item in demands[:2]]
        actions += [f"Monitor the {item.get('momentum')} theme '{item.get('label')}' ({item.get('prevalence_percentage', 0)}% prevalence)." for item in themes[:2]]
        return " ".join(actions) or "No evidence-backed strategic action is available; collect additional independent signals before deciding."

    @staticmethod
    def _page_number(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(doc.pagesize[0] - 16 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()
