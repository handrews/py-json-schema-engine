# M6 Step 4: the codegen-injection corpus (DESIGN.md D1 amendment, D10,
# D20). Every schema-derived string that could reach emitted source arrives
# only through `emit.const()` (the gated `ast` builder in
# `compiler/emit.py`) and becomes an `ast.Constant`; identifiers come from a
# fixed, machine-minted vocabulary (`Names`) that never depends on schema
# data. These cases prove that, for hostile property names, pattern
# sources, `required` entries, `enum`/`const` values, `title` values, and
# unknown keyword names, the artifact:
#   - compiles (both the default and `conservative` flag artifacts),
#   - agrees with the interpreter on matching and non-matching instances,
#   - round-trips through `ast.unparse(ast.parse(source))`,
#   - never turns a hostile string into an identifier: every `ast.Name`,
#     `ast.arg`, and `ast.FunctionDef` in the module is one of the fixed
#     helper names, the emitter's builtins, or a minted `[ubtgcrk]\d+`
#     name — even when a hostile string is itself spelled exactly like one
#     of those (e.g. the corpus includes literal "validate", "v", "u0"),
#   - carries the hostile string only as a string `ast.Constant`, present
#     or absent exactly as the schema shape dictates (a `properties`/
#     `pattern`/`enum`/`const` value reaches source; a `title` value or an
#     unknown keyword's value does not — flag mode elides annotation
#     production entirely, the safest outcome, per DESIGN.md D9/D10),
#   - and, for every shape here (all are fully static — no interpreted
#     units), emits an equally clean `emit_standalone` module that binds no
#     name at module level beyond the imports and the same vocabulary.
#
# IP policy (DESIGN.md D15): the exemplar shapes (hostile property/pattern/
# anchor/enum/const/annotation/keyword-name payloads) are ported as IDEAS
# from the TS reference engine's `packages/compiler/test/injection.test.ts`
# — our own prior work — not translated line-for-line; the Python-flavored
# additions (`__class__`, `__import__`, an `import os` payload, null bytes,
# triple-quote strings, a bare backslash, and the compiler's own vocabulary
# names) are new. No third-party validator's source was read.

import ast
import re

import pytest

from json_schema_engine.compiler import compile_validator, emit_standalone
from json_schema_engine.compiler.emit import BUILTINS_USED
from json_schema_engine.core import (
    Engine,
    JsonSchemaEngineError,
    JsonValue,
    create_engine,
)

from .test_smoke import outcome

# Built from code points, not written literally, so this source file itself
# never carries a raw U+2028/U+2029 (which would be indistinguishable from
# the hazard the corpus means to exercise).
_LS = chr(0x2028)
_PS = chr(0x2029)

HOSTILE: tuple[str, ...] = (
    'quote" + globalThis.polluted = 1 + "',
    "backtick` + `${x}`",
    "${injected}",
    "*/ dead(); /*",
    "line" + _LS + "sep" + _PS + "arator",
    "__proto__",
    "constructor",
    "back\\slash",
    "new\nline",
    "__class__",
    "__import__",
    "'; import os; os.system('x')",
    "\n",
    "\x00",
    "'''",
    '"""',
    "\\",
    "H_EQ",
    "H_FRAG",
    "validate",
    "v",
    "d",
    "s",
    "R",
    "T",
    "u0",
    "k0",
)
_IDS = [f"h{i}" for i in range(len(HOSTILE))]

# The fixed helper vocabulary a runtime-mode module may use (test_goldens.py
# pins the same set for the fixture goldens); `re` is standalone-only (its
# module imports the stdlib `re` package to compile patterns ahead of time).
MINTED_VOCABULARY = {
    "validate",
    "v",
    "d",
    "s",
    "R",
    "T",
    "H_EQ",
    "H_MOF",
    "H_DUP",
    "H_FRAG",
    "H_DEEP",
    "H_MAXD",
    "MaxDepthExceededError",
} | BUILTINS_USED
_MINTED_PATTERN = re.compile(r"(?:[ubtgcrk]|fmt)\d+$")


def _is_minted(name: str) -> bool:
    return name in MINTED_VOCABULARY or bool(_MINTED_PATTERN.fullmatch(name))


def _assert_only_minted_identifiers(module: ast.Module) -> list[str]:
    """Walk `module`, asserting every identifier is one the emitter minted,
    and return every string `ast.Constant` value found — schema data's only
    entry point into the module, per `emit.const()`."""
    constants: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Name):
            assert _is_minted(node.id), node.id
        elif isinstance(node, ast.arg):
            assert node.arg in ("v", "d", "s"), node.arg
        elif isinstance(node, ast.FunctionDef):
            assert node.name == "validate" or re.fullmatch(r"u\d+", node.name), (
                node.name
            )
        elif isinstance(node, ast.alias):
            # None expected in runtime mode (`assemble` never emits an
            # import); audited the same way if that ever changes.
            assert _is_minted(node.name), node.name
            if node.asname is not None:
                assert _is_minted(node.asname), node.asname
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            constants.append(node.value)
    return constants


def _assert_only_expected_bindings(namespace: dict[str, object]) -> None:
    """A standalone module's own namespace binds nothing beyond its import
    (`re`) and the same minted vocabulary."""
    allowed = MINTED_VOCABULARY | {"re"}
    for name in namespace:
        if name == "__builtins__":
            continue
        assert name in allowed or _MINTED_PATTERN.fullmatch(name), name


def _instances(h: str) -> list[JsonValue]:
    return [{h: "s"}, {h: 1}, {"other": 1}, h, [h], {h: h}]


def _run_checks(
    engine: Engine, registered: str, h: str, needle: str, expect_present: bool
) -> None:
    fast = compile_validator(engine, registered)
    conservative = compile_validator(engine, registered, conservative=True)
    instances = _instances(h)

    for inst in instances:
        expected = outcome(lambda inst=inst: engine.evaluate(registered, inst).valid)
        assert outcome(lambda inst=inst: fast.validate(inst)) == expected, (h, inst)
        assert outcome(lambda inst=inst: conservative.validate(inst)) == expected, (
            h,
            inst,
            "conservative",
        )

    for compiled in (fast, conservative):
        assert compiled.source == ast.unparse(ast.parse(compiled.source))
        constants = _assert_only_minted_identifiers(compiled.module)
        assert (needle in constants) is expect_present, (needle, expect_present, h)

    if not fast.plan.targets:  # fully static: emit_standalone must also work
        source = emit_standalone(engine, registered)
        ast.parse(source)
        namespace: dict[str, object] = {}
        exec(compile(source, "<standalone>", "exec"), namespace)
        _assert_only_expected_bindings(namespace)
        validate = namespace["validate"]
        for inst in instances:
            expected = outcome(
                lambda inst=inst: engine.evaluate(registered, inst).valid
            )
            assert outcome(lambda inst=inst: validate(inst)) == expected, (  # type: ignore[operator]
                h,
                inst,
                "standalone",
            )


def _check(
    schema: JsonValue, uri: str, h: str, needle: str, expect_present: bool
) -> None:
    engine = create_engine()
    registered = engine.register_schema(schema, uri)
    _run_checks(engine, registered, h, needle, expect_present)


def _check_pattern_based(schema: JsonValue, uri: str, h: str, needle: str) -> None:
    engine = create_engine()
    try:
        registered = engine.register_schema(schema, uri)
    except JsonSchemaEngineError as error:
        # `re.escape` should make every hostile string a valid ECMA-262
        # pattern, but a hostile string's escaped form is occasionally one
        # the engine's regex screen still rejects (e.g. an unsupported
        # escape); that failure mode is covered elsewhere. This corpus only
        # cares about strings that DO reach codegen.
        pytest.skip(f"{type(error).__name__}: pattern rejected by the engine")
        return
    _run_checks(engine, registered, h, needle, expect_present=True)


# --- property names, and the same names in `required` ----------------------


@pytest.mark.parametrize("h", HOSTILE, ids=_IDS)
def test_hostile_property_names_and_required(h: str) -> None:
    schema: JsonValue = {"properties": {h: {"type": "string"}}, "required": [h]}
    _check(schema, "https://inj.example/props-required", h, h, True)


# --- pattern sources (as patternProperties keys, and as `pattern` itself) ---


@pytest.mark.parametrize("h", HOSTILE, ids=_IDS)
def test_hostile_pattern_properties_keys(h: str) -> None:
    pattern = re.escape(h)
    schema: JsonValue = {"patternProperties": {pattern: {"type": "integer"}}}
    _check_pattern_based(schema, "https://inj.example/patprop", h, pattern)


@pytest.mark.parametrize("h", HOSTILE, ids=_IDS)
def test_hostile_pattern_sources(h: str) -> None:
    pattern = re.escape(h)
    schema: JsonValue = {"pattern": pattern}
    _check_pattern_based(schema, "https://inj.example/pattern", h, pattern)


# --- enum / const values, including nested inside arrays and objects -------


@pytest.mark.parametrize("h", HOSTILE, ids=_IDS)
def test_hostile_enum_values(h: str) -> None:
    schema: JsonValue = {"enum": [h, [h], {h: h}]}
    _check(schema, "https://inj.example/enum", h, h, True)


@pytest.mark.parametrize("h", HOSTILE, ids=_IDS)
def test_hostile_const_values(h: str) -> None:
    schema: JsonValue = {"const": {h: [h]}}
    _check(schema, "https://inj.example/const", h, h, True)


# --- title (an annotation-only keyword) reached through a safe $anchor/$ref -


@pytest.mark.parametrize(("i", "h"), list(enumerate(HOSTILE)), ids=_IDS)
def test_hostile_title_values_never_reach_source(i: int, h: str) -> None:
    anchor = f"x{i}"  # the anchor itself is deliberately safe; `title` is not
    schema: JsonValue = {
        "$defs": {"a": {"$anchor": anchor, "title": h}},
        "$ref": f"#{anchor}",
    }
    _check(schema, "https://inj.example/anchor-title", h, h, False)


# --- an unknown (dialect-unowned) keyword's value --------------------------


@pytest.mark.parametrize("h", HOSTILE, ids=_IDS)
def test_hostile_unknown_keyword_names(h: str) -> None:
    schema: JsonValue = {h: 1, "type": "integer"}
    _check(schema, "https://inj.example/unknown-keyword", h, h, False)
