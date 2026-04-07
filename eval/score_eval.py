"""Automated scorer for the RIS pipeline evaluation framework.

Scores predictions against gold answers across multiple dimensions:
correctness, citation precision/recall, temporal accuracy, source type
classification, and hallucination detection.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_PASS_THRESHOLDS = {
    "citation_precision": 0.95,
    "source_type_correct": 0.98,
    "temporal_accuracy": 0.95,
    "hallucination_rate_max": 0.02,
}


@dataclass
class QueryScore:
    query_id: str
    correctness: float = 0.0
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    source_type_correct: float = 0.0
    temporal_accuracy: float = 0.0
    hallucination: float = 1.0
    completeness: float = 0.0
    overall_score: float = 0.0
    review_notes: str = ""


@dataclass
class EvalRun:
    run_id: str
    scores: list[QueryScore] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def load_gold_answers(path: Path) -> dict[str, dict[str, Any]]:
    """Load gold answers keyed by query_id."""
    answers: dict[str, dict[str, Any]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            answers[row["query_id"]] = row
    return answers


def load_queries(path: Path) -> dict[str, dict[str, Any]]:
    """Load queries keyed by query_id."""
    queries: dict[str, dict[str, Any]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            queries[row["query_id"]] = row
    return queries


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    """Load predictions keyed by query_id."""
    predictions: dict[str, dict[str, Any]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            predictions[row["query_id"]] = row
    return predictions


def _parse_pipe_list(value: str | None) -> set[str]:
    if not value:
        return set()
    return {v.strip() for v in value.split("|") if v.strip()}


def score_single_query(
    query: dict[str, Any],
    gold: dict[str, Any],
    prediction: dict[str, Any],
) -> QueryScore:
    """Score a single prediction against gold."""
    query_id = query["query_id"]
    notes: list[str] = []

    answer_text = str(prediction.get("answer_text", "")).lower()
    gold_short = str(gold.get("gold_short_answer", "")).lower()

    # Correctness: keyword overlap
    gold_keywords = {w for w in gold_short.split() if len(w) > 3}
    if gold_keywords:
        matched = sum(1 for kw in gold_keywords if kw in answer_text)
        correctness = matched / len(gold_keywords)
    else:
        correctness = 1.0 if answer_text else 0.0

    # Citation precision & recall
    required_docs = _parse_pipe_list(gold.get("required_doc_ids"))
    used_docs = _parse_pipe_list(prediction.get("used_doc_ids"))

    if used_docs:
        correct_citations = used_docs & required_docs
        citation_precision = len(correct_citations) / len(used_docs) if used_docs else 0.0
    else:
        citation_precision = 0.0

    citation_recall = (
        len(used_docs & required_docs) / len(required_docs) if required_docs else 1.0
    )

    # Forbidden docs check
    forbidden_docs = _parse_pipe_list(gold.get("forbidden_doc_ids"))
    used_forbidden = used_docs & forbidden_docs
    if used_forbidden:
        notes.append(f"FORBIDDEN_DOCS_USED: {used_forbidden}")
        citation_precision = max(0.0, citation_precision - 0.5)

    # Source type correctness
    expected_source_class = query.get("expected_source_class", "")
    claimed_source_class = prediction.get("source_class_claimed", "")
    source_type_correct = 1.0 if claimed_source_class == expected_source_class else 0.0

    # Temporal accuracy
    task_type = query.get("task_type", "")
    temporal_accuracy = 1.0
    if task_type == "temporal_version":
        temporal_ok = prediction.get("model_flags", "")
        if "temporal_ok=true" in temporal_ok:
            temporal_accuracy = 1.0
        elif "temporal_ok=false" in temporal_ok:
            temporal_accuracy = 0.0
            notes.append("TEMPORAL_MISMATCH")
        else:
            temporal_accuracy = 0.5
            notes.append("TEMPORAL_NOT_VERIFIED")

    # Hallucination check (non-binding claimed as binding)
    must_flag = gold.get("must_flag_non_binding", "false").lower() == "true"
    hallucination = 1.0
    if must_flag:
        flags = prediction.get("model_flags", "")
        if "non_binding_flagged=true" in flags:
            hallucination = 1.0
        else:
            hallucination = 0.0
            notes.append("HALLUCINATION: non-binding source not flagged")

    completeness = min(1.0, correctness * 0.7 + citation_recall * 0.3)

    overall = (
        0.30 * correctness
        + 0.20 * citation_precision
        + 0.10 * citation_recall
        + 0.15 * temporal_accuracy
        + 0.10 * source_type_correct
        + 0.10 * hallucination
        + 0.05 * completeness
    )

    return QueryScore(
        query_id=query_id,
        correctness=round(correctness, 3),
        citation_precision=round(citation_precision, 3),
        citation_recall=round(citation_recall, 3),
        source_type_correct=round(source_type_correct, 3),
        temporal_accuracy=round(temporal_accuracy, 3),
        hallucination=round(hallucination, 3),
        completeness=round(completeness, 3),
        overall_score=round(overall, 3),
        review_notes="; ".join(notes),
    )


def run_evaluation(
    queries_path: Path,
    gold_path: Path,
    predictions_path: Path,
    output_dir: Path,
) -> EvalRun:
    """Run full evaluation and write results."""
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    queries = load_queries(queries_path)
    gold_answers = load_gold_answers(gold_path)
    predictions = load_predictions(predictions_path)

    eval_run = EvalRun(run_id=run_id)

    for query_id, query in queries.items():
        gold = gold_answers.get(query_id)
        prediction = predictions.get(query_id)
        if not gold or not prediction:
            eval_run.errors.append({
                "query_id": query_id,
                "error": "missing_gold" if not gold else "missing_prediction",
                "category": "R1",
            })
            continue
        score = score_single_query(query, gold, prediction)
        eval_run.scores.append(score)

    _write_scores_csv(eval_run, output_dir / "scores.csv")
    _write_error_log(eval_run, output_dir / "error_log.md")
    _write_summary(eval_run, output_dir / "summary.json")

    return eval_run


def _write_scores_csv(eval_run: EvalRun, path: Path) -> None:
    fieldnames = [
        "run_id", "query_id", "correctness", "citation_precision",
        "citation_recall", "source_type_correct", "temporal_accuracy",
        "hallucination", "completeness", "overall_score", "review_notes",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for score in eval_run.scores:
            writer.writerow({
                "run_id": eval_run.run_id,
                "query_id": score.query_id,
                "correctness": score.correctness,
                "citation_precision": score.citation_precision,
                "citation_recall": score.citation_recall,
                "source_type_correct": score.source_type_correct,
                "temporal_accuracy": score.temporal_accuracy,
                "hallucination": score.hallucination,
                "completeness": score.completeness,
                "overall_score": score.overall_score,
                "review_notes": score.review_notes,
            })


def _write_error_log(eval_run: EvalRun, path: Path) -> None:
    lines = [f"# Error Log — {eval_run.run_id}\n"]

    hallucination_fails = [s for s in eval_run.scores if s.hallucination < 1.0]
    if hallucination_fails:
        lines.append("\n## G1 Grounding Failures (hallucination)\n")
        for s in hallucination_fails:
            lines.append(f"- **{s.query_id}**: {s.review_notes}\n")

    low_citation = [s for s in eval_run.scores if s.citation_precision < 0.5]
    if low_citation:
        lines.append("\n## C1 Citation Errors\n")
        for s in low_citation:
            lines.append(f"- **{s.query_id}**: precision={s.citation_precision}\n")

    temporal_misses = [s for s in eval_run.scores if s.temporal_accuracy < 0.5]
    if temporal_misses:
        lines.append("\n## T1 Temporal Mismatches\n")
        for s in temporal_misses:
            lines.append(f"- **{s.query_id}**: {s.review_notes}\n")

    if eval_run.errors:
        lines.append("\n## R1 Retrieval / Data Errors\n")
        for err in eval_run.errors:
            lines.append(f"- **{err['query_id']}**: {err['error']}\n")

    if len(lines) == 1:
        lines.append("\nNo errors detected.\n")

    path.write_text("".join(lines), encoding="utf-8")


def _write_summary(eval_run: EvalRun, path: Path) -> None:
    if not eval_run.scores:
        summary = {"run_id": eval_run.run_id, "status": "no_scores", "errors": len(eval_run.errors)}
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    n = len(eval_run.scores)
    avg = lambda attr: round(sum(getattr(s, attr) for s in eval_run.scores) / n, 4)

    metrics = {
        "correctness": avg("correctness"),
        "citation_precision": avg("citation_precision"),
        "citation_recall": avg("citation_recall"),
        "source_type_correct": avg("source_type_correct"),
        "temporal_accuracy": avg("temporal_accuracy"),
        "hallucination": avg("hallucination"),
        "completeness": avg("completeness"),
        "overall_score": avg("overall_score"),
    }

    hallucination_rate = 1.0 - metrics["hallucination"]
    gates = {
        "citation_precision_pass": metrics["citation_precision"] >= _PASS_THRESHOLDS["citation_precision"],
        "source_type_correct_pass": metrics["source_type_correct"] >= _PASS_THRESHOLDS["source_type_correct"],
        "temporal_accuracy_pass": metrics["temporal_accuracy"] >= _PASS_THRESHOLDS["temporal_accuracy"],
        "hallucination_rate_pass": hallucination_rate <= _PASS_THRESHOLDS["hallucination_rate_max"],
        "all_gates_pass": True,
    }
    gates["all_gates_pass"] = all(v for k, v in gates.items() if k != "all_gates_pass")

    summary = {
        "run_id": eval_run.run_id,
        "query_count": n,
        "error_count": len(eval_run.errors),
        "metrics": metrics,
        "hallucination_rate": round(hallucination_rate, 4),
        "gates": gates,
        "thresholds": _PASS_THRESHOLDS,
    }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    eval_dir = Path(__file__).parent
    if len(sys.argv) > 1:
        predictions_path = Path(sys.argv[1])
    else:
        print("Usage: python score_eval.py <predictions.csv> [output_dir]")
        print("\nPredictions CSV schema:")
        print("  query_id,answer_text,used_doc_ids,source_class_claimed,model_flags")
        sys.exit(1)

    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else eval_dir / "runs" / "latest"

    result = run_evaluation(
        queries_path=eval_dir / "queries.csv",
        gold_path=eval_dir / "gold_answers.csv",
        predictions_path=predictions_path,
        output_dir=output_dir,
    )

    print(f"Evaluation complete: {result.run_id}")
    print(f"  Scored: {len(result.scores)} queries")
    print(f"  Errors: {len(result.errors)}")
    if result.scores:
        avg_overall = sum(s.overall_score for s in result.scores) / len(result.scores)
        print(f"  Average overall score: {avg_overall:.3f}")
    print(f"  Results written to: {output_dir}")


if __name__ == "__main__":
    main()
