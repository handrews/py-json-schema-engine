# The lowering IR (DESIGN.md D1, M6): data-only nodes and their shorthands,
# and the `lower` slot's default on behaviors.

from json_schema_engine.core.dialect import KeywordBehavior, StaticFacts
from json_schema_engine.core.keywords.core import CORE_VOCABULARY, annotation_only
from json_schema_engine.core.lowering import (
    HERE,
    INSTANCE,
    Apply,
    Const,
    If,
    Logic,
    LowerApply,
    Not,
    TypeIs,
    and_,
    apply,
    child,
    fail,
    in_consts,
    lower_nothing,
    not_,
    type_is,
    when,
)


def test_shorthands_build_frozen_nodes() -> None:
    stmt = when(
        and_(type_is(INSTANCE, "object"), not_(in_consts(INSTANCE, ("a", 1)))),
        (
            fail(
                ("expected one of ", Const(["a", 1])),
            ),
        ),
    )
    assert isinstance(stmt, If)
    assert isinstance(stmt.cond, Logic) and stmt.cond.op == "and"
    assert isinstance(stmt.cond.parts[0], TypeIs)
    assert isinstance(stmt.cond.parts[1], Not)
    assert stmt.orelse == ()
    applied = apply(("a",), child(HERE, "a"))
    assert isinstance(applied, Apply)
    assert applied.apply == LowerApply(("a",), child(HERE, "a"), "all_must_pass")


def test_behaviors_default_to_no_lowering_and_no_applications() -> None:
    behavior = KeywordBehavior("urn:x", lambda v, c, ctx: True)
    assert behavior.lower is None
    assert StaticFacts().applications == ()
    # Structural and annotation-only keywords lower to nothing rather than
    # forcing interpretation.
    assert CORE_VOCABULARY["$id"].lower is lower_nothing
    # Annotation-only keywords lower to an `Annotate` (M9), not to nothing.
    assert annotation_only("urn:t").lower is not None
    # `$dynamicRef` lowers like `$ref` since M9: the plan decides its target.
    assert CORE_VOCABULARY["$dynamicRef"].lower is not None
