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
        styles = getSampleStyleSheet()
        title = "Executive Statistical Brief" if report_type == "executive" else "Structured Fandom Case Study"
        page_size = landscape(A4) if report_type == "executive" else A4
        doc = SimpleDocTemplate(str(path), pagesize=page_size, rightMargin=16*mm, leftMargin=16*mm,
            topMargin=15*mm, bottomMargin=15*mm, pageCompression=0, title=f"{title}: {keyword}")
        story = [Paragraph(title, styles["Title"]), Paragraph(f"Subject: {_text(keyword)}", styles["Heading2"]), Spacer(1, 8)]
        confidence = content.get("cross_source_confidence", {})
        community = content.get("community_analysis", {})
        motivations = content.get("motivation_analysis", {})
        demand = content.get("demand_analysis", {})
        themes = content.get("narrative_theme_analysis", {})
        metrics = [["Sentiment", _text(content.get("overall_sentiment"))],
            ["Sentiment score", _text(content.get("sentiment_score"))],
            ["Cross-source confidence", _text(confidence.get("score"), "Insufficient sources")],
            ["Signals / Sources", f"{_text(content.get('signal_count'), '0')} / {_text(content.get('source_count'), '0')}"],
            ["Community toxicity", _text(community.get("toxicity_level"))],
            ["Trend momentum", _text(content.get("trend_momentum"))]]
        table = Table(metrics, colWidths=[60*mm, 100*mm])
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), colors.HexColor("#E8E5FF")),
            ("GRID", (0,0), (-1,-1), .5, colors.grey), ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("PADDING", (0,0), (-1,-1), 7)]))
        story.extend([table, Spacer(1, 12)])
        contents = ["Global summary", "Engagement and volume", "Trend and momentum", "Regional comparison", "Community and motivation", "Demand and intent", "Narrative themes", "Strategic opportunities", "Risks, limitations, and methodology"]
        story.extend([Paragraph("Table of contents", styles["Heading2"]), Paragraph("<br/>".join(f"{index}. {_text(item)}" for index, item in enumerate(contents, 1)), styles["BodyText"]), PageBreak()])
        if report_type == "case_study":
            story.extend([Paragraph("Background and research objectives", styles["Heading2"]), Paragraph("This report describes observable audience discussion, sentiment, momentum, motivations, and explicit demand for the selected research subject. It does not infer unavailable demographic attributes.", styles["BodyText"]), Spacer(1, 8)])
        engagement = content.get("analysis_pipeline", {})
        story.extend([Paragraph("Engagement and volume", styles["Heading2"]), Paragraph(f"The persisted run contains {_text(content.get('signal_count'), '0')} usable signals across {_text(content.get('source_count'), '0')} contributing sources. Detailed engagement aggregates remain available in the canonical pipeline payload: {_text(bool(engagement))}.", styles["BodyText"]), Paragraph("Trend and momentum", styles["Heading2"]), Paragraph(f"Overall momentum: {_text(content.get('trend_momentum'))}. Trend score: {_text(content.get('trend_score'))}. Statistical anomaly count: {_text(len(content.get('anomaly_alerts', [])), '0')}.", styles["BodyText"]), Paragraph("Regional comparison", styles["Heading2"]), Paragraph("Regional findings are included only when stored collector location data is sufficient. Collector region must not be interpreted as audience residence.", styles["BodyText"]), Spacer(1, 8)])
        sections = [("Evidence-derived narrative themes", themes.get("themes", []), "label"),
            ("Explicit demand signals", demand.get("demands", []), "request"),
            ("Frequently asked questions", demand.get("frequently_asked_questions", []), "question"),
            ("Praise and likes", motivations.get("praise", []) + motivations.get("likes", []), "topic"),
            ("Complaints and unmet expectations", motivations.get("complaints", []) + motivations.get("unmet_expectations", []), "topic")]
        for heading, rows, key in sections:
            story.append(Paragraph(heading, styles["Heading2"]))
            if rows:
                for row in rows[:10]:
                    count = row.get("mention_count", "?")
                    story.append(Paragraph(f"• {_text(row.get(key))} (evidence mentions: {_text(count)})", styles["BodyText"]))
            else:
                story.append(Paragraph("Insufficient stored evidence.", styles["BodyText"]))
            story.append(Spacer(1, 7))
            if report_type == "executive" and len(story) > 12:
                story.append(PageBreak())
        warnings = content.get("structured_result", {}).get("warnings", [])
        version = content.get("structured_result", {}).get("methodology_version", "luvcraft-analytics-v1")
        story.extend([Paragraph("Strategic opportunities and recommended actions", styles["Heading2"]), Paragraph("Prioritize the highest-prevalence evidence-backed demand and rising themes; validate decisions against the linked raw signals before execution.", styles["BodyText"]), Paragraph("Risks, limitations, and methodology", styles["Heading2"]),
            Paragraph(f"Version: {_text(version)}. Results use stored signals only; evidence gaps are not inferred. Warnings: {_text('; '.join(warnings) if warnings else 'None')}", styles["BodyText"])])
        doc.build(story, onFirstPage=self._page_number, onLaterPages=self._page_number)

    @staticmethod
    def _page_number(canvas, doc) -> None:
        canvas.saveState(); canvas.setFont("Helvetica", 8)
        canvas.drawRightString(doc.pagesize[0] - 16*mm, 8*mm, f"Page {doc.page}"); canvas.restoreState()
