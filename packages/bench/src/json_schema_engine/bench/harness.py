# Bench harness (M6 Step 5). Report-only: nothing here gates CI (the
# `bench` job runs with `continue-on-error: true`); it exists to make the
# numbers reproducible, locally and as a CI artifact.
#
# Methodology (ported intent, not code, from the TS reference engine's
# `bench/harness.ts` — see DESIGN.md D15):
# - ORACLE FIRST. Every subject must agree with the corpus's expected
#   verdict (itself derived from the interpreter, `Engine.evaluate` — the
#   reference semantics) on every instance before anything about that
#   subject is timed. A subject that cannot even be prepared (e.g. `jse
#   standalone` on a schema `emit_standalone` cannot emit), or that
#   disagrees with the oracle on any instance, is recorded as an
#   `exclusion` with a reason instead of timed.
# - `--filter <regex>` restricts which corpus/subject pairs run at all
#   (oracle included) — not just which are timed — so iterating on one
#   corpus does not pay for the rest (compiling every subject's cold
#   artifact for every corpus is real work: standalone emission and
#   fastjsonschema/jsonschema compilation are not free).
# - Each surviving corpus/subject pair is timed over three partitions —
#   `hot` (every instance), `valid`, `invalid` — round-robin over the
#   partition's instances, plus a `compile` partition timing `prepare`
#   itself (the cold artifact build) for every subject except the plain
#   interpreter (which has no separate compile step worth reporting).
# - Timing loops are a `timeit.Timer.autorange`-style doubling search for
#   a batch size that takes a few milliseconds, then repeated batches
#   until `budget_ms` (per task) is spent.

from __future__ import annotations

import importlib.metadata
import itertools
import platform
import re
import subprocess
import sys
import timeit
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from json_schema_engine.bench.corpora import CORPUS_NAMES, Corpus, load_corpus
from json_schema_engine.bench.subjects import SUBJECTS, Subject, Validate
from json_schema_engine.compiler import StandaloneUnsupportedError
from json_schema_engine.core import JsonValue

Partition = str  # "compile" | "hot" | "valid" | "invalid"
_PARTITION_NAMES = ("compile", "hot", "valid", "invalid")

_MIN_BATCH_SECONDS = 0.005

# The plain interpreter subjects have no separate cold-artifact build step
# worth reporting (`prepare` just registers the schema) — `jse interpreter
# flag` and its `list`-output counterpart both skip the "compile" partition.
_NO_COMPILE_PARTITION = {"jse interpreter flag", "jse interpreter list"}

# .../packages/bench/src/json_schema_engine/bench/harness.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SUBJECT_PACKAGES = ("json-schema-engine", "ecma-regex", "fastjsonschema", "jsonschema")


def _machine() -> str:
    """A best-effort CPU brand string; results metadata, never a gate, so
    this must never raise regardless of platform or missing tools."""
    system = platform.system()
    try:
        if system == "Darwin":
            brand = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
            if brand:
                return brand
        elif system == "Linux":
            with Path("/proc/cpuinfo").open(encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("model name"):
                        _, _, value = line.partition(":")
                        value = value.strip()
                        if value:
                            return value
    except Exception:  # best-effort metadata, never a gate
        pass
    return platform.processor() or "unknown"


def _commit() -> str | None:
    """The repo's short commit hash, or `None` on any failure (a shallow
    clone, a missing `git`, or running outside a repo at all)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception:  # best-effort metadata, never a gate
        return None
    commit = result.stdout.strip()
    return commit or None


def _subject_versions() -> dict[str, str]:
    """Installed versions of every package a subject depends on."""
    versions: dict[str, str] = {}
    for name in _SUBJECT_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unknown"
    return versions


@dataclass(frozen=True, slots=True)
class TaskResult:
    task: str
    corpus: str
    partition: Partition
    subject: str
    ops_per_sec: float
    mean_ns: float
    samples: int


@dataclass(frozen=True, slots=True)
class Exclusion:
    corpus: str
    subject: str
    reason: str


@dataclass(frozen=True, slots=True)
class CorpusMeta:
    name: str
    instances: int
    invalid: int


@dataclass(frozen=True, slots=True)
class Results:
    generated_at: str
    python: str
    platform: str
    machine: str
    commit: str | None
    subjects: dict[str, str]
    budget_ms: int
    corpora: list[CorpusMeta]
    exclusions: list[Exclusion]
    results: list[TaskResult]

    def to_dict(self) -> dict[str, JsonValue]:
        return asdict(self)  # type: ignore[return-value]


def _task_name(corpus: str, partition: Partition, subject: str) -> str:
    return f"{corpus} | {partition} | {subject}"


def _matches(pattern: re.Pattern[str] | None, task: str) -> bool:
    return pattern is None or pattern.search(task) is not None


def _corpus_could_match(pattern: re.Pattern[str] | None, corpus_name: str) -> bool:
    """Whether *any* task name for `corpus_name` could match `pattern`.

    A coarse, cheap pre-check run before `load_corpus` — which, for the
    generated records corpora, pays for 2000 oracle evaluations — so a
    filter naming one corpus (or one subject, or one partition) skips
    building the corpora it can never select, without having to actually
    build a corpus just to test its instances against the filter.
    """
    if pattern is None:
        return True
    candidates = (corpus_name, *(s.name for s in SUBJECTS), *_PARTITION_NAMES)
    return any(pattern.search(candidate) for candidate in candidates)


def _autorange(fn: Callable[[], object], budget_s: float) -> tuple[int, float]:
    """Total (calls, seconds) for `fn`, spending about `budget_s`.

    Doubles/quintuples the batch size (1, 2, 5, 10, 20, 50, ...) until one
    batch takes at least `_MIN_BATCH_SECONDS`, then keeps running batches
    of that size until the budget is spent — `timeit.Timer.autorange`'s
    own progression, but stopping on a caller-supplied budget rather than
    the library's fixed 0.2 s threshold.
    """
    timer = timeit.Timer(fn)
    batch = 1
    elapsed = 0.0
    for scale in itertools.count():
        found = False
        for mult in (1, 2, 5):
            batch = mult * (10**scale)
            elapsed = timer.timeit(number=batch)
            if elapsed >= _MIN_BATCH_SECONDS or elapsed >= budget_s:
                found = True
                break
        if found:
            break
    total_calls = batch
    total_time = elapsed
    while total_time < budget_s:
        elapsed = timer.timeit(number=batch)
        total_time += elapsed
        total_calls += batch
    return total_calls, total_time


@dataclass(frozen=True, slots=True)
class _Timing:
    ops_per_sec: float
    mean_ns: float
    samples: int


def _time_task(fn: Callable[[], object], budget_ms: int) -> _Timing | None:
    calls, seconds = _autorange(fn, budget_ms / 1000)
    if calls == 0 or seconds <= 0:
        return None
    mean_s = seconds / calls
    return _Timing(ops_per_sec=1.0 / mean_s, mean_ns=mean_s * 1e9, samples=calls)


def _round_robin(
    validate: Validate, instances: Iterable[JsonValue]
) -> Callable[[], object]:
    cycle = itertools.cycle(list(instances))

    def run() -> object:
        return validate(next(cycle))

    return run


def _expected(corpus: Corpus) -> list[bool]:
    return (
        corpus.expected
        if corpus.expected is not None
        else [True] * len(corpus.instances)
    )


def _partition_instances(corpus: Corpus) -> dict[str, list[JsonValue]]:
    expected = _expected(corpus)
    valid = [i for i, ok in zip(corpus.instances, expected, strict=True) if ok]
    invalid = [i for i, ok in zip(corpus.instances, expected, strict=True) if not ok]
    return {"hot": corpus.instances, "valid": valid, "invalid": invalid}


def _check_oracle(corpus: Corpus, subject: Subject, validate: Validate) -> str | None:
    """`None` if `validate` agrees with the oracle on every instance,
    otherwise a reason summarizing the first mismatch."""
    expected = _expected(corpus)
    for index, (instance, want) in enumerate(
        zip(corpus.instances, expected, strict=True)
    ):
        got = validate(instance)
        if got != want:
            return (
                f"{subject.name} disagrees with the oracle on "
                f"{corpus.name}#{index}: got {got!r}, expected {want!r}"
            )
    return None


def run(budget_ms: int = 250, filter_regex: str | None = None) -> Results:
    """Run the bench: oracle-check, then time, every corpus x subject pair.

    `filter_regex`, when given, restricts which corpus/subject pairs run
    at all (oracle included) to those whose `"<corpus> | <subject>"` name
    matches; timed partitions are filtered again by their full task name.
    """
    pattern = re.compile(filter_regex) if filter_regex is not None else None
    exclusions: list[Exclusion] = []
    results: list[TaskResult] = []
    corpora_meta: list[CorpusMeta] = []

    for name in CORPUS_NAMES:
        if not _corpus_could_match(pattern, name):
            continue
        corpus = load_corpus(name)
        expected = _expected(corpus)
        corpora_meta.append(
            CorpusMeta(
                name=corpus.name,
                instances=len(corpus.instances),
                invalid=sum(1 for ok in expected if not ok),
            )
        )
        partitions = _partition_instances(corpus)

        for subject in SUBJECTS:
            if not _matches(pattern, f"{corpus.name} | {subject.name}"):
                continue

            try:
                validate = subject.prepare(corpus.schema)
            except StandaloneUnsupportedError as error:
                exclusions.append(Exclusion(corpus.name, subject.name, str(error)))
                continue

            reason = _check_oracle(corpus, subject, validate)
            if reason is not None:
                exclusions.append(Exclusion(corpus.name, subject.name, reason))
                continue

            if subject.name not in _NO_COMPILE_PARTITION:
                task = _task_name(corpus.name, "compile", subject.name)
                if _matches(pattern, task):
                    timed = _time_task(
                        lambda schema=corpus.schema, s=subject: s.prepare(schema),
                        budget_ms,
                    )
                    if timed is not None:
                        results.append(
                            TaskResult(
                                task=task,
                                corpus=corpus.name,
                                partition="compile",
                                subject=subject.name,
                                ops_per_sec=timed.ops_per_sec,
                                mean_ns=timed.mean_ns,
                                samples=timed.samples,
                            )
                        )

            for partition_name, instances in partitions.items():
                if not instances:
                    continue
                task = _task_name(corpus.name, partition_name, subject.name)
                if not _matches(pattern, task):
                    continue
                timed = _time_task(_round_robin(validate, instances), budget_ms)
                if timed is None:
                    continue
                results.append(
                    TaskResult(
                        task=task,
                        corpus=corpus.name,
                        partition=partition_name,
                        subject=subject.name,
                        ops_per_sec=timed.ops_per_sec,
                        mean_ns=timed.mean_ns,
                        samples=timed.samples,
                    )
                )

    return Results(
        generated_at=datetime.now(UTC).isoformat(),
        python=sys.version.split()[0],
        platform=platform.platform(),
        machine=_machine(),
        commit=_commit(),
        subjects=_subject_versions(),
        budget_ms=budget_ms,
        corpora=corpora_meta,
        exclusions=exclusions,
        results=results,
    )
