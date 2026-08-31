from pathlib import Path
from uuid import uuid4

import pytest

from app.services.report_service import ReportGeneratorService
from app.main import app

@pytest.mark.parametrize("report_type,heading", [("executive", b"Executive Statistical Brief"), ("case_study", b"Structured Fandom Case Study")])
def test_report_service_writes_real_pdf_from_synthesis(tmp_path: Path, report_type: str, heading: bytes):
    content = {"overall_sentiment": "Positive", "sentiment_score": 73, "signal_count": 12, "source_count": 2, "cross_source_confidence": {"sources": [{"source": "youtube", "usable_signal_count": 8, "positive_percentage": 70, "neutral_percentage": 20, "negative_percentage": 10}, {"source": "news", "usable_signal_count": 4, "positive_percentage": 60, "neutral_percentage": 30, "negative_percentage": 10}]}, "trend_data": [{"volume": 5}, {"volume": 12}, {"volume": 9}], "geo_comparison": [{"country_code": "VN", "signal_count": 7}], "demand_analysis": {"demands": [{"request": "co-op", "mention_count": 3}]}, "report_evidence": [{"signal_id": "one", "excerpt": "Please add co-op because playing together is more fun."}], "methodology_details": {"timeframe_start": "2026-08-01", "timeframe_end": "2026-08-27"}, "structured_result": {"methodology_version": "luvcraft-analytics-v1", "warnings": []}}
    report = ReportGeneratorService(tmp_path).generate(run_id=uuid4(), keyword="Sample", report_type=report_type, content=content)
    payload = Path(report.file_path).read_bytes()
    assert payload.startswith(b"%PDF")
    assert heading in payload
    assert b"Sentiment distribution" in payload
    assert b"Analysis timeframe" in payload
    if report_type == "case_study":
        assert b"Representative evidence excerpts" in payload
        assert b"Methodology appendix" in payload
    assert report.file_size_bytes == len(payload)
    assert len(report.input_fingerprint) == 64

def test_safe_path_rejects_files_outside_storage(tmp_path: Path):
    service = ReportGeneratorService(tmp_path / "allowed")
    report = service.generate(run_id=uuid4(), keyword="Sample", report_type="executive", content={})
    report.file_path = str(tmp_path / "other.pdf")
    with pytest.raises(FileNotFoundError):
        service.safe_path(report)


def test_authenticated_report_api_contract_is_registered():
    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    assert ("/api/v1/runs/{run_id}/reports/executive", "POST") in routes
    assert ("/api/v1/runs/{run_id}/reports/case-study", "POST") in routes
    assert ("/api/v1/runs/{run_id}/reports", "GET") in routes
    assert ("/api/v1/reports/{report_id}/download", "GET") in routes


def test_report_embeds_unicode_font_for_vietnamese(tmp_path: Path):
    content = {
        "overall_sentiment": "Tích cực",
        "trend_momentum": "đang tăng",
        "narrative_theme_analysis": {
            "themes": [{"label": "kiểm soát nội dung âm nhạc", "mention_count": 2}]
        },
    }
    report = ReportGeneratorService(tmp_path).generate(
        run_id=uuid4(),
        keyword="Sơn Tùng và âm nhạc Việt",
        report_type="case_study",
        content=content,
    )
    payload = Path(report.file_path).read_bytes()
    assert b"/Subtype /TrueType" in payload
    assert b"/ToUnicode" in payload
