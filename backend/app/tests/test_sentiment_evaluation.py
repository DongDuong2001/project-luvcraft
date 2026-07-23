import json
from pathlib import Path

import pytest

from app.analysis.modules.sentiment import SentimentAnalysisModule
from app.analysis.sentiment_evaluation import (
    AnalysisModuleSentimentPredictor,
    LabelledSentimentExample,
    SentimentEvaluationPrediction,
    dataset_fingerprint,
    evaluate_sentiment,
    load_labelled_examples,
    main,
)


def example(
    example_id: str,
    human_label: str,
    *,
    language: str = "en",
    text: str | None = None,
) -> LabelledSentimentExample:
    return LabelledSentimentExample(
        example_id=example_id,
        keyword="Demon Slayer",
        language=language,
        text=text or f"Example text {example_id}",
        human_label=human_label,
    )


class FakePredictor:
    classifier_name = "sentiment"
    classifier_version = "hybrid-test-v1"
    provider = "fake"
    model_identifier = "fake-model"
    prompt_version = "prompt-v1"
    prompt_hash = f"sha256:{'e' * 64}"

    def __init__(self, predictions):
        self._predictions = predictions

    def predict(self, examples):
        del examples
        return tuple(self._predictions)


def prediction(example_id, label, *, route="llm"):
    return SentimentEvaluationPrediction(
        example_id=example_id,
        predicted_label=label,
        confidence=0.8 if label is not None else None,
        route=route,
    )


def four_examples():
    return (
        example("one", "positive"),
        example("two", "negative"),
        example("three", "neutral", language="vi"),
        example("four", "positive", language="vi"),
    )


def test_exactly_75_percent_meets_alignment_gate():
    report = evaluate_sentiment(
        examples=four_examples(),
        predictor=FakePredictor(
            (
                prediction("one", "positive"),
                prediction("two", "negative"),
                prediction("three", "neutral"),
                prediction("four", "negative"),
            )
        ),
        threshold=0.75,
        minimum_sample_count=4,
        require_full_llm_coverage=True,
    )

    assert report.human_agreement == 0.75
    assert report.meets_agreement_threshold is True
    assert report.meets_capstone_agreement is True
    assert report.prediction_coverage == 1.0
    assert report.llm_coverage == 1.0
    assert report.release_ready is False
    assert report.per_language[0].agreement == 1.0
    assert report.per_language[1].agreement == 0.5


def test_missing_prediction_counts_wrong_and_reduces_coverage():
    report = evaluate_sentiment(
        examples=four_examples(),
        predictor=FakePredictor(
            (
                prediction("one", "positive"),
                prediction("two", "negative"),
                prediction("three", "neutral"),
            )
        ),
        threshold=0.75,
        minimum_sample_count=4,
    )

    assert report.human_agreement == 0.75
    assert report.prediction_coverage == 0.75
    assert report.release_ready is False
    positive_row = next(
        row for row in report.confusion_matrix if row.actual_label == "positive"
    )
    assert positive_row.missing == 1


def test_fallback_predictions_cannot_pass_hybrid_llm_coverage_gate():
    examples = four_examples()
    report = evaluate_sentiment(
        examples=examples,
        predictor=FakePredictor(
            tuple(
                prediction(
                    item.example_id,
                    item.human_label,
                    route="lexicon_fallback",
                )
                for item in examples
            )
        ),
        threshold=0.75,
        minimum_sample_count=4,
        require_full_llm_coverage=True,
    )

    assert report.human_agreement == 1.0
    assert report.llm_coverage == 0.0
    assert report.release_ready is False


def test_report_has_fingerprint_metrics_and_never_echoes_source_text():
    private_text = "private validation sentence"
    examples = (example("one", "neutral", text=private_text),)
    report = evaluate_sentiment(
        examples=examples,
        predictor=FakePredictor((prediction("one", "neutral"),)),
        threshold=0,
        minimum_sample_count=1,
    )

    serialized = report.model_dump_json()
    assert report.dataset_fingerprint == dataset_fingerprint(examples)
    assert report.per_label
    assert report.macro_f1 >= 0
    assert private_text not in serialized


def test_loader_supports_utf8_and_rejects_duplicate_ids(tmp_path: Path):
    path = tmp_path / "validation.jsonl"
    row = {
        "example_id": "vi-1",
        "keyword": "Demon Slayer",
        "language": "vi",
        "text": "Mình rất thích nội dung này",
        "human_label": "positive",
    }
    path.write_text(
        f"{json.dumps(row, ensure_ascii=False)}\n"
        f"{json.dumps(row, ensure_ascii=False)}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_labelled_examples(path)


def test_real_lexicon_module_can_be_evaluated_through_module_contract():
    examples = (
        example("en-good", "positive", text="I love this amazing trailer"),
        example("vi-bad", "negative", language="vi", text="Tôi thất vọng vì quá tệ"),
        example("en-fact", "neutral", text="The episode airs Friday"),
    )

    report = evaluate_sentiment(
        examples=examples,
        predictor=AnalysisModuleSentimentPredictor(SentimentAnalysisModule()),
        threshold=1.0,
        minimum_sample_count=3,
    )

    assert report.human_agreement == 1.0
    assert report.release_ready is False
    assert dict((route.route, route.count) for route in report.routes) == {"lexicon": 3}


def test_cli_returns_gate_status_and_writes_report(tmp_path: Path, capsys):
    dataset_path = tmp_path / "validation.jsonl"
    output_path = tmp_path / "report.json"
    rows = [
        {
            "example_id": "one",
            "keyword": "Demon Slayer",
            "language": "en",
            "text": "I love this",
            "human_label": "positive",
        }
    ]
    dataset_path.write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dataset",
            str(dataset_path),
            "--classifier",
            "lexicon",
            "--threshold",
            "1",
            "--min-samples",
            "1",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assert json.loads(output_path.read_text())["release_ready"] is False
    assert "private validation sentence" not in capsys.readouterr().out


def release_examples(count: int):
    labels = ("positive", "neutral", "negative")
    return tuple(
        example(
            f"sample-{index}",
            labels[index % len(labels)],
            language="en" if index < count // 2 else "vi",
            text=f"Unique human-labelled content {index}",
        )
        for index in range(count)
    )


def test_fixed_capstone_gate_requires_500_hybrid_predictions_and_manifest():
    examples = release_examples(500)
    predictions = tuple(
        prediction(item.example_id, item.human_label) for item in examples
    )

    report = evaluate_sentiment(
        examples=examples,
        predictor=FakePredictor(predictions),
        threshold=0,
        minimum_sample_count=1,
        annotation_manifest_verified=True,
    )

    assert report.meets_capstone_minimum_sample_count is True
    assert report.meets_per_language_capstone_agreement is True
    assert report.has_required_languages is True
    assert report.has_required_labels is True
    assert report.release_ready is True


def test_499_examples_cannot_pass_fixed_capstone_gate():
    examples = release_examples(499)
    report = evaluate_sentiment(
        examples=examples,
        predictor=FakePredictor(
            tuple(prediction(item.example_id, item.human_label) for item in examples)
        ),
        threshold=0,
        minimum_sample_count=1,
        annotation_manifest_verified=True,
    )

    assert report.meets_agreement_threshold is True
    assert report.meets_minimum_sample_count is True
    assert report.meets_capstone_minimum_sample_count is False
    assert report.release_ready is False


def test_duplicate_normalized_content_is_rejected_even_with_unique_ids():
    examples = (
        example("one", "positive", text="Same   Text"),
        example("two", "positive", text="same text"),
    )

    with pytest.raises(ValueError, match="duplicate normalized text"):
        evaluate_sentiment(
            examples=examples,
            predictor=FakePredictor(()),
        )
