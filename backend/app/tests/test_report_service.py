from pathlib import Path
from uuid import uuid4

import pytest

from app.services.report_service import ReportGeneratorService

@pytest.mark.parametrize("report_type,heading", [("executive", b"Executive Statistical Brief"), ("case_study", b"Structured Fandom Case Study")])
def test_report_service_writes_real_pdf_from_synthesis(tmp_path: Path, report_type: str, heading: bytes):
    content = {"overall_sentiment": "Positive", "sentiment_score": 73, "signal_count": 12, "source_count": 2, "demand_analysis": {"demands": [{"request": "co-op", "mention_count": 3}]}, "structured_result": {"methodology_version": "luvcraft-analytics-v1", "warnings": []}}
    report = ReportGeneratorService(tmp_path).generate(run_id=uuid4(), keyword="Sample", report_type=report_type, content=content)
    payload = Path(report.file_path).read_bytes()
    assert payload.startswith(b"%PDF")
    assert heading in payload
    assert report.file_size_bytes == len(payload)
    assert len(report.input_fingerprint) == 64

def test_safe_path_rejects_files_outside_storage(tmp_path: Path):
    service = ReportGeneratorService(tmp_path / "allowed")
    report = service.generate(run_id=uuid4(), keyword="Sample", report_type="executive", content={})
    report.file_path = str(tmp_path / "other.pdf")
    with pytest.raises(FileNotFoundError):
        service.safe_path(report)
