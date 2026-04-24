"""Scorers: deterministic graders that run on each item's output during an experiment.

A scorer implements `.score(...)` and returns a `ScoreResult`. The runner wraps it
into a Langfuse `Evaluation`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import isclose
from typing import Any, Protocol, runtime_checkable


@dataclass
class ScoreResult:
    name: str
    value: float | str
    comment: str | None = None
    data_type: str = "NUMERIC"  # NUMERIC | CATEGORICAL | BOOLEAN


@runtime_checkable
class Scorer(Protocol):
    name: str

    def score(
        self,
        *,
        output: dict[str, Any],
        expected_output: dict[str, Any],
        input: dict[str, Any],
        metadata: dict[str, Any],
    ) -> ScoreResult: ...


# ---------------------------------------------------------------------------
# ExactMatchScorer — byte-level equality (strict regression gate)
# ---------------------------------------------------------------------------


def _normalize_list_string(s: str) -> list[str] | None:
    try:
        parsed = json.loads(s)
    except Exception:
        return None
    if isinstance(parsed, list):
        return sorted(str(x).strip().lower() for x in parsed)
    return None


def exact_match(got: str, expected: str) -> bool:
    got = (got or "").strip()
    expected = (expected or "").strip()
    got_list = _normalize_list_string(got)
    exp_list = _normalize_list_string(expected)
    if got_list is not None and exp_list is not None:
        return got_list == exp_list
    return got.lower().rstrip(".") == expected.lower().rstrip(".")


class ExactMatchScorer:
    name = "exact_match"

    def score(
        self,
        *,
        output: dict[str, Any],
        expected_output: dict[str, Any],
        input: dict[str, Any],  # noqa: A002, ARG002
        metadata: dict[str, Any],  # noqa: ARG002
    ) -> ScoreResult:
        got = str((output or {}).get("answer", ""))
        expected = str((expected_output or {}).get("answer", ""))
        return ScoreResult(
            name=self.name,
            value=1.0 if exact_match(got, expected) else 0.0,
            comment=f"got={got!r} expected={expected!r}",
        )


# ---------------------------------------------------------------------------
# MMLongBenchOfficialScorer — verbatim port of MMLongBench-Doc's eval_score.py
# (NeurIPS 2024). Preserved algorithmically so scores are leaderboard-comparable.
#   Upstream: https://github.com/mayubo2333/MMLongBench-Doc/blob/main/eval/eval_score.py
# ---------------------------------------------------------------------------


def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    distances = list(range(len(s1) + 1))
    for index2, char2 in enumerate(s2):
        distances_ = [index2 + 1]
        for index1, char1 in enumerate(s1):
            if char1 == char2:
                distances_.append(distances[index1])
            else:
                distances_.append(1 + min((distances[index1], distances[index1 + 1], distances_[-1])))
        distances = distances_
    return distances[-1]


def _anls_compute(groundtruth: str, prediction: str, threshold: float = 0.5) -> float:
    dist = _levenshtein_distance(groundtruth, prediction)
    length = max(len(groundtruth.upper()), len(prediction.upper()))
    value = 0.0 if length == 0 else float(dist) / float(length)
    anls = 1.0 - value
    if anls <= threshold:
        anls = 0.0
    return anls


def _is_float_equal(
    reference: float | str,
    prediction: float | str,
    include_percentage: bool = False,
    is_close: bool = False,
) -> bool:
    def _get_precision(gt_ans: float) -> int:
        return len(str(gt_ans).split(".")[-1]) if "." in str(gt_ans) else 3

    reference = float(str(reference).strip().rstrip("%").strip())
    try:
        prediction = float(str(prediction).strip().rstrip("%").strip())
    except Exception:
        return False

    candidates = [reference / 100, reference, reference * 100] if include_percentage else [reference]
    for item in candidates:
        try:
            if is_close and isclose(item, prediction, rel_tol=0.01):
                return True
            precision = max(min(_get_precision(prediction), _get_precision(item)), 2)
            if round(prediction, precision) == round(item, precision):
                return True
        except Exception:
            continue
    return False


def _get_clean_string(s: Any) -> str:
    s = str(s).lower().strip()
    # Upstream applies .rstrip() + .strip() without reassigning — preserved for parity
    if s.endswith("mile"):
        s.rstrip("mile").strip()  # noqa: B005
    if s.endswith("miles"):
        s.rstrip("miles").strip()  # noqa: B005
    if s.endswith("million"):
        s.rstrip("million").strip()  # noqa: B005
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()
    s = re.sub(r"^['\"]|['\"]$", "", s).strip()
    s = s.strip().lstrip("$").strip().rstrip("%").strip()
    return s


def _is_exact_match(s: str) -> bool:
    if "https://" in s:
        return True
    if s.endswith((".py", "ipynb")):
        return True
    if s.startswith("page"):
        return True
    if re.fullmatch(r"\b\d+(-\d+|\s\d+)?\b", s):
        return True
    if "a.m." in s or "p.m." in s:
        return True
    if re.fullmatch(r"\b\d{4}[-\s]\d{2}[-\s]\d{2}\b", s):
        return True
    if re.fullmatch(r"\b\d{4}[-\s]\d{2}\b", s):
        return True
    if re.fullmatch(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", s):
        return True
    return False


def _isfloat(num: Any) -> bool:
    try:
        float(num)
        return True
    except ValueError:
        return False


def eval_score_official(gt: Any, pred: Any, answer_type: str) -> float:
    """Verbatim MMLongBench-Doc scoring. answer_type ∈ {Int, Float, Str, None, List...}."""
    if answer_type == "Int":
        try:
            return float(int(gt) == int(float(pred)))
        except Exception:
            return 0.0

    if answer_type == "Float":
        try:
            gt_f = float(_get_clean_string(gt))
            pred_f = float(_get_clean_string(pred))
        except Exception:
            return 0.0
        return float(_is_float_equal(gt_f, pred_f, include_percentage=True, is_close=True))

    if answer_type in ("Str", "None"):
        gt_s = _get_clean_string(gt)
        pred_s = _get_clean_string(pred)
        return float(gt_s == pred_s) if _is_exact_match(gt_s) else float(_anls_compute(gt_s, pred_s))

    # List branch
    gt_list = _coerce_list(gt)
    pred_list = _coerce_list(pred)
    if len(gt_list) != len(pred_list):
        return 0.0
    gt_clean = sorted([_get_clean_string(a) for a in gt_list])
    pred_clean = sorted([_get_clean_string(a) for a in pred_list])
    if _isfloat(gt_clean[0]) or _is_exact_match(gt_clean[0]):
        return float("-".join(gt_clean) == "-".join(pred_clean))
    return float(min(_anls_compute(gt_v, pred_v) for gt_v, pred_v in zip(gt_clean, pred_clean, strict=True)))


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, str) and value.startswith("["):
        try:
            return eval(value)  # noqa: S307
        except Exception:
            return [value]
    return list(value) if isinstance(value, list) else [value]


# ---------------------------------------------------------------------------
# LengthHitScorer — generic; checks whether output length meets the target
# ---------------------------------------------------------------------------


def _word_count(text: str) -> int:
    return len(text.split())


def _target_word_count(length_hint: str, default: int = 150) -> int | None:
    """Resolve a length hint to a target word count.

    Accepts: 'short' | 'medium' | 'long' | '<N> words' | '<N>' | '' (→ default).
    Returns None when unknown (caller should treat as unscorable).
    """
    if not length_hint:
        return default
    hint = length_hint.strip().lower()
    buckets = {"short": 50, "medium": 150, "long": 400}
    if hint in buckets:
        return buckets[hint]
    number_match = re.search(r"\d+", hint)
    return int(number_match.group(0)) if number_match else None


class LengthHitScorer:
    """Output-length vs. target hit-rate (±tolerance).

    Reads the summary text from `output["summary"]` and resolves a target from:
      1. `input["length"]["content"]["text"]` (our Summary primitive's shape)
      2. `metadata["length"]` fallback
    Returns 1.0 if within tolerance, 0.0 otherwise.
    """

    name = "length_hit"

    def __init__(self, tolerance: float = 0.2) -> None:
        self.tolerance = tolerance

    def score(
        self,
        *,
        output: dict[str, Any],
        expected_output: dict[str, Any],  # noqa: ARG002
        input: dict[str, Any],  # noqa: A002
        metadata: dict[str, Any],
    ) -> ScoreResult:
        text = str((output or {}).get("summary", ""))
        actual = _word_count(text)

        length_hint = ""
        if isinstance(input, dict):
            hint_node = input.get("length")
            if isinstance(hint_node, dict):
                content = hint_node.get("content") or {}
                if isinstance(content, dict):
                    length_hint = str(content.get("text", ""))
        if not length_hint and isinstance(metadata, dict):
            length_hint = str(metadata.get("length", ""))

        target = _target_word_count(length_hint)
        if target is None or target == 0:
            return ScoreResult(
                name=self.name,
                value=0.0,
                comment=f"could not resolve target from hint={length_hint!r}; actual={actual}",
            )
        lower, upper = target * (1 - self.tolerance), target * (1 + self.tolerance)
        hit = lower <= actual <= upper
        return ScoreResult(
            name=self.name,
            value=1.0 if hit else 0.0,
            comment=f"actual={actual} target={target} ±{int(self.tolerance * 100)}% → {'hit' if hit else 'miss'}",
        )


# ---------------------------------------------------------------------------
# EntityPreservationScorer — generic; fraction of source entities kept in output
# ---------------------------------------------------------------------------


_CAPITALIZED_ENTITY = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*\b")
_NUMBER_WITH_UNIT = re.compile(r"\b\d[\d,]*\.?\d*\s*(?:%|million|billion|trillion|thousand|M|B|K)?")


def _extract_naive_entities(text: str) -> set[str]:
    """Cheap entity anchor via regex: capitalized multi-word spans + numbers-with-units.

    Deliberately primitive. This is a faithfulness ANCHOR, not a NER system. Over-detects
    (e.g. sentence-initial words); that only makes the scorer more forgiving, which is the
    right error direction for an anchor metric.
    """
    entities: set[str] = set()
    for match in _CAPITALIZED_ENTITY.finditer(text):
        span = match.group(0).strip()
        if len(span) > 2:
            entities.add(span)
    for match in _NUMBER_WITH_UNIT.finditer(text):
        span = match.group(0).strip()
        if span and any(c.isdigit() for c in span):
            entities.add(span)
    return entities


class EntityPreservationScorer:
    """Fraction of source entities that survive into the output text.

    Reads source from `input["text"]["content"]["text"]` or falls back to
    `metadata["source_text"]`. Reads output text from `output["summary"]`.
    Returns preservation rate in [0, 1]. Missing input → 0.
    """

    name = "entity_preservation_rate"

    def score(
        self,
        *,
        output: dict[str, Any],
        expected_output: dict[str, Any],  # noqa: ARG002
        input: dict[str, Any],  # noqa: A002
        metadata: dict[str, Any],
    ) -> ScoreResult:
        summary = str((output or {}).get("summary", ""))
        source = ""
        if isinstance(input, dict):
            text_node = input.get("text")
            if isinstance(text_node, dict):
                content = text_node.get("content") or {}
                if isinstance(content, dict):
                    source = str(content.get("text", ""))
        if not source and isinstance(metadata, dict):
            source = str(metadata.get("source_text", ""))

        source_entities = _extract_naive_entities(source)
        if not source_entities:
            return ScoreResult(name=self.name, value=0.0, comment="no entities detected in source")
        summary_entities = _extract_naive_entities(summary)
        preserved = source_entities & summary_entities
        rate = len(preserved) / len(source_entities)
        return ScoreResult(
            name=self.name,
            value=round(rate, 3),
            comment=f"preserved {len(preserved)}/{len(source_entities)} source entities",
        )


# ---------------------------------------------------------------------------
# MMLongBenchOfficialScorer — verbatim port of the benchmark's eval_score.py
# ---------------------------------------------------------------------------


class MMLongBenchOfficialScorer:
    """Leaderboard-comparable accuracy using the benchmark's official scoring protocol."""

    name = "mmlongbench_acc"

    def score(
        self,
        *,
        output: dict[str, Any],
        expected_output: dict[str, Any],
        input: dict[str, Any],  # noqa: A002
        metadata: dict[str, Any],
    ) -> ScoreResult:
        answer_format = (metadata or {}).get("answer_format") or (input or {}).get("answer_format") or "Str"
        got = str((output or {}).get("answer", ""))
        expected = str((expected_output or {}).get("answer", ""))
        return ScoreResult(
            name=self.name,
            value=eval_score_official(expected, got, answer_format),
            comment=f"format={answer_format} got={got!r} expected={expected!r}",
        )
