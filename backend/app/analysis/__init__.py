"""Canonical contracts and modules for the Project Luvcraft analysis layer."""

from app.analysis.contracts import (
    AnalysisCoverageStatus,
    AnalysisDataset,
    AnalysisError,
    AnalysisInputSummary,
    AnalysisMetric,
    AnalysisModule,
    AnalysisQuality,
    AnalysisResult,
    AnalysisSignal,
    AnalysisStage,
    AnalysisStatus,
    AnalysisTimeframe,
    AnalysisWarning,
    CollectorStatus,
    ExclusionCount,
    FilterStatistics,
    SignalModality,
    SourceCoverage,
)
from app.analysis.modules.sentiment import SentimentAnalysisModule
from app.analysis.pipeline import AnalysisPipeline
from app.analysis.registry import AnalysisModuleRegistry


def create_default_analysis_registry() -> AnalysisModuleRegistry:
    """Create the production registry without relying on import side effects."""
    return AnalysisModuleRegistry([SentimentAnalysisModule()])


__all__ = [
    "AnalysisCoverageStatus",
    "AnalysisDataset",
    "AnalysisError",
    "AnalysisInputSummary",
    "AnalysisMetric",
    "AnalysisModule",
    "AnalysisModuleRegistry",
    "AnalysisPipeline",
    "AnalysisQuality",
    "AnalysisResult",
    "AnalysisSignal",
    "AnalysisStage",
    "AnalysisStatus",
    "AnalysisTimeframe",
    "AnalysisWarning",
    "CollectorStatus",
    "ExclusionCount",
    "FilterStatistics",
    "SentimentAnalysisModule",
    "SignalModality",
    "SourceCoverage",
    "create_default_analysis_registry",
]
