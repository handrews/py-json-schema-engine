# M6 Step 4: the differential fuzzer (DESIGN.md D12; M6.3-equivalent). Every
# group in the official suite's four dialect directories, seeded with its own
# suite instances plus Hypothesis-driven mutations of them, evaluated by the
# interpreter and by both compiled artifacts (default and `conservative`);
# verdicts and exception classes must agree. A genuine divergence here is a
# compiler bug: the interpreter is the reference semantics (compiler/__init__.py).
#
# One test function per dialect directory so each gets its own Hypothesis
# budget (`conftest.py`'s `ci`/`deep` profiles); `HYPOTHESIS_PROFILE=deep` runs
# a long, non-derandomized pass meant to be invoked by hand, never as part of
# the default gate.

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from json_schema_engine.compiler import CompiledValidator, compile_validator
from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
    Engine,
    JsonSchemaEngineError,
    JsonValue,
    create_engine,
)
from json_schema_engine.formats import FORMATS_2020_12, format_table_for
from json_schema_engine.test_kit import load_suite_file, suite_remotes_loader

from .fuzz_support import is_json_shaped, mutated
from .test_smoke import outcome

ROOT = Path(__file__).resolve().parents[2]
SUITE_ROOT = ROOT / "test-suite" / "tests"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
RETRIEVAL_URI = "https://fuzz.example/schema"

DIALECT_DIRS: dict[str, str] = {
    "draft2020-12": DIALECT_2020_12,
    "draft2019-09": DIALECT_2019_09,
    "draft7": DIALECT_DRAFT_07,
    "draft6": DIALECT_DRAFT_06,
}


@dataclass(frozen=True, slots=True)
class CorpusGroup:
    """One suite group: a loaded schema plus the suite's own instances for it.

    `engine`/`uri` are built once, at corpus-construction time (registration
    is cheap and needed anyway to decide whether the group belongs in the
    corpus at all); the expensive step — compiling `validate`/`conservative`
    artifacts — is deferred to `_artifacts`, on first use, and cached there.
    """

    key: str
    dialect_dir: str
    dialect_uri: str
    engine: Engine
    uri: str
    seeds: tuple[JsonValue, ...]


def _file_groups(path: Path) -> dict[str, tuple[JsonValue, list[JsonValue]]]:
    """(schema, seed instances) per group description, in first-seen order."""
    by_group: dict[str, tuple[JsonValue, list[JsonValue]]] = {}
    for case in load_suite_file(path):
        entry = by_group.setdefault(case.group, (case.schema, []))
        entry[1].append(case.data)
    return by_group


def _build_corpus() -> tuple[list[CorpusGroup], int]:
    groups: list[CorpusGroup] = []
    skipped = 0
    for dialect_dir, dialect_uri in DIALECT_DIRS.items():
        suite_dir = SUITE_ROOT / dialect_dir
        for path in sorted(suite_dir.glob("*.json")):
            for index, (group_desc, (schema, seeds)) in enumerate(
                _file_groups(path).items()
            ):
                engine = create_engine(
                    default_dialect=dialect_uri,
                    loaders=[suite_remotes_loader(REMOTES_DIR)],
                )
                try:
                    uri = engine.load_schema(schema, RETRIEVAL_URI)
                except JsonSchemaEngineError:
                    # Other legs (the suite runner itself) cover registration
                    # failures; a group that can't even load contributes no
                    # differential coverage.
                    skipped += 1
                    continue
                groups.append(
                    CorpusGroup(
                        key=f"{dialect_dir}/{path.stem}/{group_desc}#{index}",
                        dialect_dir=dialect_dir,
                        dialect_uri=dialect_uri,
                        engine=engine,
                        uri=uri,
                        seeds=tuple(seeds),
                    )
                )
    return groups, skipped


CORPUS, SKIPPED_GROUPS = _build_corpus()
assert len(CORPUS) > 1000, (len(CORPUS), SKIPPED_GROUPS)

CORPUS_BY_DIR: dict[str, list[CorpusGroup]] = {}
for _group in CORPUS:
    CORPUS_BY_DIR.setdefault(_group.dialect_dir, []).append(_group)
assert set(CORPUS_BY_DIR) == set(DIALECT_DIRS)


# --- the format-directory corpus (M7 Step 3) --------------------------
#
# Every group in `optional/format/*.json` across the four dialect
# directories, with the standard format table asserted (best-effort, every
# dialect); draft2020-12's `optional/format-assertion.json` is added too,
# with `formats=` alone (assertion there comes from the schema's own
# `$vocabulary`, not the engine option). A suite group's schema is
# registered once and shared; the corpus records one `CorpusGroup` per
# (group, individual seed instance) rather than one per group, since the
# format directories hold few groups (a `date`/`email`/... file is
# typically a single group with many `tests` entries) — group-level
# records alone can't clear the size floor below, and per-seed records
# also give every suite instance its own uniform sampling weight instead
# of diluting rare cases inside a large shared seed pool.

_FORMAT_SUITE_SUBDIR = "optional/format"


def _build_format_corpus() -> tuple[list[CorpusGroup], int]:
    groups: list[CorpusGroup] = []
    skipped = 0
    for dialect_dir, dialect_uri in DIALECT_DIRS.items():
        format_dir = SUITE_ROOT / dialect_dir / "optional" / "format"
        for path in sorted(format_dir.glob("*.json")):
            for index, (group_desc, (schema, seeds)) in enumerate(
                _file_groups(path).items()
            ):
                engine = create_engine(
                    default_dialect=dialect_uri,
                    formats=format_table_for(dialect_uri),
                    assert_formats=True,
                    loaders=[suite_remotes_loader(REMOTES_DIR)],
                )
                try:
                    uri = engine.load_schema(schema, RETRIEVAL_URI)
                except JsonSchemaEngineError:
                    skipped += len(seeds)
                    continue
                for seed_index, seed in enumerate(seeds):
                    groups.append(
                        CorpusGroup(
                            key=(
                                f"{dialect_dir}/{_FORMAT_SUITE_SUBDIR}/{path.stem}/"
                                f"{group_desc}#{index}.{seed_index}"
                            ),
                            dialect_dir=dialect_dir,
                            dialect_uri=dialect_uri,
                            engine=engine,
                            uri=uri,
                            seeds=(seed,),
                        )
                    )
    fa_path = SUITE_ROOT / "draft2020-12" / "optional" / "format-assertion.json"
    fa_groups = enumerate(_file_groups(fa_path).items())
    for index, (group_desc, (schema, seeds)) in fa_groups:
        engine = create_engine(
            default_dialect=DIALECT_2020_12,
            formats=FORMATS_2020_12,
            loaders=[suite_remotes_loader(REMOTES_DIR)],
        )
        try:
            uri = engine.load_schema(schema, RETRIEVAL_URI)
        except JsonSchemaEngineError:
            skipped += len(seeds)
            continue
        for seed_index, seed in enumerate(seeds):
            groups.append(
                CorpusGroup(
                    key=(
                        "draft2020-12/optional/format-assertion/"
                        f"{group_desc}#{index}.{seed_index}"
                    ),
                    dialect_dir="draft2020-12",
                    dialect_uri=DIALECT_2020_12,
                    engine=engine,
                    uri=uri,
                    seeds=(seed,),
                )
            )
    return groups, skipped


FORMAT_CORPUS, FORMAT_SKIPPED_GROUPS = _build_format_corpus()
assert len(FORMAT_CORPUS) > 100, (len(FORMAT_CORPUS), FORMAT_SKIPPED_GROUPS)


_ARTIFACT_CACHE: dict[str, tuple[CompiledValidator, CompiledValidator]] = {}


def _artifacts(group: CorpusGroup) -> tuple[CompiledValidator, CompiledValidator]:
    """The (default, conservative) compiled artifacts for `group`, built and
    cached on first use."""
    cached = _ARTIFACT_CACHE.get(group.key)
    if cached is None:
        fast = compile_validator(group.engine, group.uri)
        conservative = compile_validator(group.engine, group.uri, conservative=True)
        cached = (fast, conservative)
        _ARTIFACT_CACHE[group.key] = cached
    return cached


def _instances_for(group: CorpusGroup) -> st.SearchStrategy[JsonValue]:
    seeds = group.seeds if group.seeds else (None,)
    return st.sampled_from(seeds).flatmap(
        lambda seed: st.one_of(st.just(seed), mutated(seed))
    )


def _cases_for(dialect_dir: str) -> st.SearchStrategy[tuple[CorpusGroup, JsonValue]]:
    groups = st.sampled_from(CORPUS_BY_DIR[dialect_dir])
    return groups.flatmap(
        lambda group: st.tuples(st.just(group), _instances_for(group))
    )


def _check_case(case: tuple[CorpusGroup, JsonValue]) -> None:
    group, instance = case
    expected = outcome(lambda: group.engine.evaluate(group.uri, instance).valid)
    fast, conservative = _artifacts(group)
    assert outcome(lambda: fast.validate(instance)) == expected, (group.key, instance)
    assert outcome(lambda: conservative.validate(instance)) == expected, (
        group.key,
        instance,
        "conservative",
    )


# --- one property per dialect directory, its own Hypothesis budget --------


@given(case=_cases_for("draft2020-12"))
def test_differential_draft2020_12(case: tuple[CorpusGroup, JsonValue]) -> None:
    _check_case(case)


@given(case=_cases_for("draft2019-09"))
def test_differential_draft2019_09(case: tuple[CorpusGroup, JsonValue]) -> None:
    _check_case(case)


@given(case=_cases_for("draft7"))
def test_differential_draft7(case: tuple[CorpusGroup, JsonValue]) -> None:
    _check_case(case)


@given(case=_cases_for("draft6"))
def test_differential_draft6(case: tuple[CorpusGroup, JsonValue]) -> None:
    _check_case(case)


# --- one property over the format-directory corpus, across all four
# dialects at once (its own Hypothesis budget, same as the properties
# above) -----------------------------------------------------------------


def _cases_for_formats() -> st.SearchStrategy[tuple[CorpusGroup, JsonValue]]:
    groups = st.sampled_from(FORMAT_CORPUS)
    return groups.flatmap(
        lambda group: st.tuples(st.just(group), _instances_for(group))
    )


@given(case=_cases_for_formats())
def test_differential_formats(case: tuple[CorpusGroup, JsonValue]) -> None:
    _check_case(case)


# --- mutator shape guarantee ------------------------------------------------

_REPRESENTATIVE_SEEDS: tuple[JsonValue, ...] = (
    None,
    True,
    False,
    0,
    1.5,
    "s",
    [],
    {},
    [1, "a", None],
    {"a": 1, "b": [1, 2], "c": {"d": None}},
)


@given(instance=st.sampled_from(_REPRESENTATIVE_SEEDS).flatmap(mutated))
def test_mutators_only_produce_json_shaped_values(instance: JsonValue) -> None:
    assert is_json_shaped(instance), instance


# --- planted-divergence self-test ------------------------------------------
#
# Proves the comparison in `_check_case` can actually see a wrong verdict,
# not just that it happens to agree on this corpus. A validator wrapped to
# flip its verdict whenever a deterministic hash of the instance is even
# must trip the comparison inside a bounded run; the honest artifact run
# through the identical comparison must not. `hashlib` (not the builtin
# `hash`, which is salted per process) keeps the flip reproducible.


def _flip_key(instance: JsonValue) -> int:
    text = json.dumps(instance, sort_keys=True)  # ensure_ascii=True: pure ASCII
    digest = hashlib.sha256(text.encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def test_planted_divergence_self_test() -> None:
    group = CORPUS[0]
    engine, uri = group.engine, group.uri
    fast, _conservative = _artifacts(group)
    honest = fast.validate

    def corrupted(instance: JsonValue) -> bool:
        verdict = honest(instance)
        return not verdict if _flip_key(instance) % 2 == 0 else verdict

    instances = _instances_for(group)

    @given(instance=instances)
    @settings(max_examples=200, deadline=None, database=None)
    def check(validate: Callable[[JsonValue], bool], instance: JsonValue) -> None:
        expected = outcome(lambda: engine.evaluate(uri, instance).valid)
        assert outcome(lambda: validate(instance)) == expected

    # The corrupted validator must be caught...
    with pytest.raises(AssertionError):
        check(corrupted)
    # ...and the honest one must pass the identical bounded comparison, so
    # the failure above is the plant, not a real divergence or a broken
    # comparison.
    check(honest)
