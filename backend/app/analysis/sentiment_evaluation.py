"""Human-labelled sentiment evaluation and release-gate CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict, Field, field_validator

from app.analysis.contracts import (
    AnalysisDataset,
    AnalysisSignal,
    AnalysisStage,
    AnalysisTimeframe,
    FilterStatistics,
    FrozenModel,
    SignalModality,
)
from app.analysis.modules.hybrid_sentiment import SentimentInferenceRoute
from app.analysis.modules.sentiment import (
    SentimentAnalysisModule,
    SentimentLabel,
)
from app.analysis.sentiment_provider import SentimentTokenUsage


EVALUATION_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
SUPPORTED_LANGUAGES: tuple[Literal["en", "vi"], ...] = ("en", "vi")
CAPSTONE_AGREEMENT_THRESHOLD = 0.75
CAPSTONE_MINIMUM_SAMPLE_COUNT = 500


class LabelledSentimentExample(FrozenModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")

    example_id: str = Field(min_length=1, max_length=100)
    keyword: str = Field(min_length=1, max_length=255)
    language: Literal["en", "vi"]
    text: str = Field(min_length=1)
    human_label: SentimentLabel
    source_category: str | None = Field(default=None, max_length=100)
    phenomena: tuple[str, ...] = ()

    @field_validator("example_id", "keyword", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("phenomena")
    @classmethod
    def normalize_phenomena(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({item.strip() for item in value if item.strip()}))


class SentimentEvaluationPrediction(FrozenModel):
    example_id: str = Field(min_length=1)
    predicted_label: SentimentLabel | None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    route: str = Field(min_length=1)


class SentimentDatasetManifest(FrozenModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")

    dataset_version: str = Field(min_length=1, max_length=100)
    labelled_at: date
    reviewer_count: int = Field(ge=2)
    blind_review: bool
    adjudicated: bool
    pii_reviewed: bool
    rights_reviewed: bool
    annotator_agreement: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def verified(self) -> bool:
        return (
            self.blind_review
            and self.adjudicated
            and self.pii_reviewed
            and self.rights_reviewed
        )


class SentimentEvaluationPredictor(Protocol):
    classifier_name: str
    classifier_version: str
    provider: str | None
    model_identifier: str | None
    prompt_version: str | None
    prompt_hash: str | None

    def predict(
        self,
        examples: tuple[LabelledSentimentExample, ...],
    ) -> tuple[SentimentEvaluationPrediction, ...]: ...


class ConfusionRow(FrozenModel):
    actual_label: SentimentLabel
    positive: int = Field(ge=0)
    neutral: int = Field(ge=0)
    negative: int = Field(ge=0)
    missing: int = Field(ge=0)


class LabelMetric(FrozenModel):
    label: SentimentLabel
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    support: int = Field(ge=0)


class LanguageMetric(FrozenModel):
    language: Literal["en", "vi"]
    sample_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    agreement: float = Field(ge=0.0, le=1.0)


class RouteCount(FrozenModel):
    route: str = Field(min_length=1)
    count: int = Field(ge=0)


class SentimentEvaluationReport(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    classifier_name: str
    classifier_version: str
    provider: str | None
    model_identifier: str | None
    prompt_version: str | None
    prompt_hash: str | None
    actual_models: tuple[str, ...]
    provider_call_count: int = Field(ge=0)
    usage: SentimentTokenUsage
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    truncated_count: int = Field(ge=0)
    threshold: float = Field(ge=0.0, le=1.0)
    minimum_sample_count: int = Field(ge=1)
    require_full_llm_coverage: bool
    capstone_threshold: float = Field(
        default=CAPSTONE_AGREEMENT_THRESHOLD,
        ge=0.75,
        le=0.75,
    )
    capstone_minimum_sample_count: int = Field(
        default=CAPSTONE_MINIMUM_SAMPLE_COUNT,
        ge=500,
        le=500,
    )
    sample_count: int = Field(ge=1)
    prediction_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    human_agreement: float = Field(ge=0.0, le=1.0)
    prediction_coverage: float = Field(ge=0.0, le=1.0)
    llm_coverage: float = Field(ge=0.0, le=1.0)
    macro_f1: float = Field(ge=0.0, le=1.0)
    meets_agreement_threshold: bool
    meets_minimum_sample_count: bool
    meets_capstone_agreement: bool
    meets_capstone_minimum_sample_count: bool
    meets_per_language_capstone_agreement: bool
    has_required_languages: bool
    has_required_labels: bool
    annotation_manifest_verified: bool
    release_ready: bool
    confusion_matrix: tuple[ConfusionRow, ...]
    per_label: tuple[LabelMetric, ...]
    per_language: tuple[LanguageMetric, ...]
    routes: tuple[RouteCount, ...]


class AnalysisModuleSentimentPredictor:
    """Evaluate the real module contract, grouping examples by target keyword."""

    def __init__(self, module) -> None:
        self._module = module
        self.classifier_name = module.name
        self.classifier_version = module.version
        descriptor = getattr(module, "provider_descriptor", None)
        self.provider = descriptor.provider if descriptor is not None else None
        self.model_identifier = descriptor.model if descriptor is not None else None
        self.prompt_version = (
            descriptor.prompt_version if descriptor is not None else None
        )
        self.prompt_hash = descriptor.prompt_hash if descriptor is not None else None
        self.actual_models: tuple[str, ...] = ()
        self.provider_call_count = 0
        self.usage = SentimentTokenUsage()
        self.estimated_cost_usd: Decimal | None = None
        self.truncated_count = 0

    def predict(
        self,
        examples: tuple[LabelledSentimentExample, ...],
    ) -> tuple[SentimentEvaluationPrediction, ...]:
        grouped: dict[str, list[LabelledSentimentExample]] = defaultdict(list)
        actual_models: set[str] = set()
        usage_totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }
        total_cost = Decimal(0)
        cost_is_configured = True
        saw_inference = False
        self.provider_call_count = 0
        self.truncated_count = 0
        for example in examples:
            grouped[example.keyword].append(example)

        predictions: dict[str, SentimentEvaluationPrediction] = {}
        for keyword in sorted(grouped):
            group = tuple(sorted(grouped[keyword], key=lambda item: item.example_id))
            result = self._module.analyze(self._dataset(keyword, group))
            inference = getattr(result.data, "inference", None)
            if inference is not None:
                saw_inference = True
                actual_models.update(inference.actual_models)
                self.provider_call_count += inference.provider_call_count
                self.truncated_count += inference.truncated_count
                for field in usage_totals:
                    usage_totals[field] += getattr(inference.usage, field)
                if inference.estimated_cost_usd is None:
                    cost_is_configured = False
                else:
                    total_cost += inference.estimated_cost_usd
            item_by_id = (
                {item.signal_id: item for item in result.data.items}
                if result.data is not None
                else {}
            )
            for example in group:
                signal_id = self._signal_id(example.example_id)
                item = item_by_id.get(signal_id)
                if item is None:
                    predictions[example.example_id] = SentimentEvaluationPrediction(
                        example_id=example.example_id,
                        predicted_label=None,
                        confidence=None,
                        route="missing",
                    )
                    continue
                route = getattr(item, "route", "lexicon")
                predictions[example.example_id] = SentimentEvaluationPrediction(
                    example_id=example.example_id,
                    predicted_label=item.label,
                    confidence=item.confidence,
                    route=str(route),
                )

        self.actual_models = tuple(sorted(actual_models))
        self.usage = SentimentTokenUsage(**usage_totals)
        self.estimated_cost_usd = (
            total_cost if saw_inference and cost_is_configured else None
        )
        return tuple(predictions[example.example_id] for example in examples)

    @classmethod
    def _dataset(
        cls,
        keyword: str,
        examples: tuple[LabelledSentimentExample, ...],
    ) -> AnalysisDataset:
        canonical = json.dumps(
            [example.model_dump(mode="json") for example in examples],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
        signals = tuple(
            AnalysisSignal(
                signal_id=cls._signal_id(example.example_id),
                source="human_validation",
                signal_type="labelled_text",
                cleaned_text=example.text,
                language=example.language,
                modalities=(SignalModality.TEXT,),
                published_at=EVALUATION_TIME,
                collected_at=EVALUATION_TIME,
            )
            for example in examples
        )
        identity = f"{keyword}:{fingerprint}"
        return AnalysisDataset(
            run_id=uuid5(NAMESPACE_URL, f"luvcraft-eval-run:{identity}"),
            snapshot_id=uuid5(NAMESPACE_URL, f"luvcraft-eval-snapshot:{identity}"),
            keyword=keyword,
            stage=AnalysisStage.FINAL,
            revision=1,
            timeframe=AnalysisTimeframe(
                start=EVALUATION_TIME - timedelta(days=1),
                end=EVALUATION_TIME + timedelta(days=1),
            ),
            signals=signals,
            filter_statistics=FilterStatistics(
                collected_count=len(signals),
                eligible_count=len(signals),
                excluded_count=0,
            ),
            input_fingerprint=f"sha256:{fingerprint}",
            preprocessing_version="human-validation-v1",
            configuration_version="sentiment-evaluation-v1",
        )

    @staticmethod
    def _signal_id(example_id: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"luvcraft-sentiment-example:{example_id}")


def load_labelled_examples(path: Path) -> tuple[LabelledSentimentExample, ...]:
    examples: list[LabelledSentimentExample] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                example = LabelledSentimentExample.model_validate(raw)
            except Exception as exc:
                raise ValueError(
                    f"invalid validation example at line {line_number}"
                ) from exc
            if example.example_id in seen_ids:
                raise ValueError(
                    f"duplicate validation example_id at line {line_number}"
                )
            seen_ids.add(example.example_id)
            examples.append(example)
    if not examples:
        raise ValueError("validation dataset must contain at least one example")
    _validate_unique_content(examples)
    return tuple(examples)


def load_dataset_manifest(path: Path) -> SentimentDatasetManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SentimentDatasetManifest.model_validate(raw)
    except Exception as exc:
        raise ValueError("invalid sentiment dataset manifest") from exc


def dataset_fingerprint(
    examples: Sequence[LabelledSentimentExample],
) -> str:
    canonical = json.dumps(
        [
            example.model_dump(mode="json")
            for example in sorted(examples, key=lambda item: item.example_id)
        ],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def evaluate_sentiment(
    *,
    examples: tuple[LabelledSentimentExample, ...],
    predictor: SentimentEvaluationPredictor,
    threshold: float = 0.75,
    minimum_sample_count: int = 500,
    require_full_llm_coverage: bool = False,
    annotation_manifest_verified: bool = False,
) -> SentimentEvaluationReport:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("agreement threshold must be between zero and one")
    if minimum_sample_count < 1:
        raise ValueError("minimum sample count must be positive")
    _validate_unique_content(examples)

    raw_predictions = predictor.predict(examples)
    predictions = {prediction.example_id: prediction for prediction in raw_predictions}
    if len(predictions) != len(raw_predictions):
        raise ValueError("predictor returned duplicate example IDs")
    unknown_ids = set(predictions) - {example.example_id for example in examples}
    if unknown_ids:
        raise ValueError("predictor returned unknown example IDs")

    labels = tuple(SentimentLabel)
    confusion: dict[SentimentLabel, Counter[str]] = {
        label: Counter() for label in labels
    }
    route_counts: Counter[str] = Counter()
    language_totals: Counter[str] = Counter()
    language_correct: Counter[str] = Counter()
    correct_count = 0
    prediction_count = 0
    llm_count = 0

    for example in examples:
        prediction = predictions.get(example.example_id)
        predicted_label = prediction.predicted_label if prediction else None
        route = prediction.route if prediction else "missing"
        route_counts[route] += 1
        language_totals[example.language] += 1
        if predicted_label is None:
            confusion[example.human_label]["missing"] += 1
            continue
        prediction_count += 1
        confusion[example.human_label][predicted_label.value] += 1
        if route in {
            SentimentInferenceRoute.LLM.value,
            SentimentInferenceRoute.CACHE.value,
        }:
            llm_count += 1
        if predicted_label == example.human_label:
            correct_count += 1
            language_correct[example.language] += 1

    sample_count = len(examples)
    agreement = _ratio(correct_count, sample_count)
    prediction_coverage = _ratio(prediction_count, sample_count)
    llm_coverage = _ratio(llm_count, sample_count)
    per_label = tuple(
        _label_metric(label=label, confusion=confusion, labels=labels)
        for label in labels
    )
    macro_f1 = round(
        sum(metric.f1 for metric in per_label) / len(per_label),
        4,
    )
    meets_agreement = _meets_ratio(correct_count, sample_count, threshold)
    meets_minimum = sample_count >= minimum_sample_count
    meets_capstone_agreement = _meets_ratio(
        correct_count,
        sample_count,
        CAPSTONE_AGREEMENT_THRESHOLD,
    )
    meets_capstone_minimum = sample_count >= CAPSTONE_MINIMUM_SAMPLE_COUNT
    full_prediction_coverage = prediction_count == sample_count
    full_llm_coverage = llm_count == sample_count
    label_support = Counter(example.human_label for example in examples)
    has_required_languages = all(
        language_totals[language] > 0 for language in SUPPORTED_LANGUAGES
    )
    has_required_labels = all(label_support[label] > 0 for label in labels)
    meets_per_language_capstone = has_required_languages and all(
        _meets_ratio(
            language_correct[language],
            language_totals[language],
            CAPSTONE_AGREEMENT_THRESHOLD,
        )
        for language in SUPPORTED_LANGUAGES
    )
    is_hybrid = predictor.classifier_version.startswith("hybrid-")
    release_ready = (
        is_hybrid
        and meets_capstone_agreement
        and meets_capstone_minimum
        and meets_per_language_capstone
        and has_required_labels
        and full_prediction_coverage
        and full_llm_coverage
        and annotation_manifest_verified
    )

    return SentimentEvaluationReport(
        dataset_fingerprint=dataset_fingerprint(examples),
        classifier_name=predictor.classifier_name,
        classifier_version=predictor.classifier_version,
        provider=predictor.provider,
        model_identifier=predictor.model_identifier,
        prompt_version=predictor.prompt_version,
        prompt_hash=predictor.prompt_hash,
        actual_models=tuple(getattr(predictor, "actual_models", ())),
        provider_call_count=int(getattr(predictor, "provider_call_count", 0)),
        usage=getattr(predictor, "usage", SentimentTokenUsage()),
        estimated_cost_usd=getattr(predictor, "estimated_cost_usd", None),
        truncated_count=int(getattr(predictor, "truncated_count", 0)),
        threshold=threshold,
        minimum_sample_count=minimum_sample_count,
        require_full_llm_coverage=require_full_llm_coverage,
        sample_count=sample_count,
        prediction_count=prediction_count,
        correct_count=correct_count,
        human_agreement=agreement,
        prediction_coverage=prediction_coverage,
        llm_coverage=llm_coverage,
        macro_f1=macro_f1,
        meets_agreement_threshold=meets_agreement,
        meets_minimum_sample_count=meets_minimum,
        meets_capstone_agreement=meets_capstone_agreement,
        meets_capstone_minimum_sample_count=meets_capstone_minimum,
        meets_per_language_capstone_agreement=meets_per_language_capstone,
        has_required_languages=has_required_languages,
        has_required_labels=has_required_labels,
        annotation_manifest_verified=annotation_manifest_verified,
        release_ready=release_ready,
        confusion_matrix=tuple(
            ConfusionRow(
                actual_label=label,
                positive=confusion[label][SentimentLabel.POSITIVE.value],
                neutral=confusion[label][SentimentLabel.NEUTRAL.value],
                negative=confusion[label][SentimentLabel.NEGATIVE.value],
                missing=confusion[label]["missing"],
            )
            for label in labels
        ),
        per_label=per_label,
        per_language=tuple(
            LanguageMetric(
                language=language,
                sample_count=language_totals[language],
                correct_count=language_correct[language],
                agreement=_ratio(
                    language_correct[language],
                    language_totals[language],
                ),
            )
            for language in SUPPORTED_LANGUAGES
        ),
        routes=tuple(
            RouteCount(route=route, count=count)
            for route, count in sorted(route_counts.items())
        ),
    )


def _label_metric(
    *,
    label: SentimentLabel,
    confusion: dict[SentimentLabel, Counter[str]],
    labels: Iterable[SentimentLabel],
) -> LabelMetric:
    true_positive = confusion[label][label.value]
    false_positive = sum(
        confusion[actual][label.value] for actual in labels if actual != label
    )
    false_negative = sum(
        count
        for predicted, count in confusion[label].items()
        if predicted != label.value
    )
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision + recall
        else 0.0
    )
    return LabelMetric(
        label=label,
        precision=precision,
        recall=recall,
        f1=f1,
        support=sum(confusion[label].values()),
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _meets_ratio(numerator: int, denominator: int, threshold: float) -> bool:
    if denominator == 0:
        return False
    return Decimal(numerator) / Decimal(denominator) >= Decimal(str(threshold))


def _validate_unique_content(
    examples: Sequence[LabelledSentimentExample],
) -> None:
    identities: set[tuple[str, str, str]] = set()
    for example in examples:
        identity = (
            example.keyword.strip().casefold(),
            example.language,
            " ".join(example.text.split()).casefold(),
        )
        if identity in identities:
            raise ValueError("validation dataset contains duplicate normalized text")
        identities.add(identity)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate sentiment against human-labelled JSONL data.",
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--classifier",
        choices=("lexicon", "hybrid"),
        default="hybrid",
    )
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--min-samples", type=int, default=500)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Human-labelling and data-governance manifest for release runs.",
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        examples = load_labelled_examples(args.dataset)
        manifest = (
            load_dataset_manifest(args.manifest) if args.manifest is not None else None
        )
        if args.classifier == "hybrid":
            from app.analysis import create_sentiment_analysis_module

            module = create_sentiment_analysis_module(engine="hybrid")
            require_full_llm_coverage = True
        else:
            module = SentimentAnalysisModule()
            require_full_llm_coverage = False
        report = evaluate_sentiment(
            examples=examples,
            predictor=AnalysisModuleSentimentPredictor(module),
            threshold=args.threshold,
            minimum_sample_count=args.min_samples,
            require_full_llm_coverage=require_full_llm_coverage,
            annotation_manifest_verified=(
                manifest.verified if manifest is not None else False
            ),
        )
    except Exception as exc:
        print(f"sentiment evaluation configuration error: {exc}", file=sys.stderr)
        return 2

    serialized = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{serialized}\n", encoding="utf-8")
    print(serialized)
    return 0 if report.release_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
