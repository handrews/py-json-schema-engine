# Facts consistency (DESIGN.md D1; M6): for every built-in keyword, the
# `applications` a schema declares resolve through the registry to walked
# positions, and every applied `subschemas` position is one an application
# names — so the planner's edges and the registration walk cannot drift.

import pytest

from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_07,
    JsonValue,
    create_engine,
)
from json_schema_engine.core.json_model import is_object

FIXTURES: list[tuple[str, JsonValue]] = [
    (
        DIALECT_2020_12,
        {
            "$defs": {"t": {"type": "string"}},
            "$ref": "#/$defs/t",
            "allOf": [{}],
            "anyOf": [{}, {}],
            "oneOf": [{}],
            "not": {},
            "if": {},
            "then": {},
            "else": {},
            "dependentSchemas": {"a": {}},
            "properties": {"a": {}, "b": {}},
            "patternProperties": {"^x": {}},
            "additionalProperties": {},
            "propertyNames": {},
            "prefixItems": [{}, {}],
            "items": {},
            "contains": {},
            "unevaluatedProperties": {},
            "unevaluatedItems": {},
        },
    ),
    (
        DIALECT_2019_09,
        {
            "$defs": {"t": {}},
            "$ref": "#/$defs/t",
            "items": [{}, {}],
            "additionalItems": {},
            "contains": {},
            "unevaluatedItems": {},
            "unevaluatedProperties": {},
        },
    ),
    (
        DIALECT_DRAFT_07,
        {
            "definitions": {"t": {}},
            "items": {},
            "dependencies": {"a": {}, "b": ["c"]},
            "contains": {},
        },
    ),
]


@pytest.mark.parametrize(("dialect", "schema"), FIXTURES, ids=[f[0] for f in FIXTURES])
def test_applications_resolve_and_cover_applied_positions(
    dialect: str, schema: JsonValue
) -> None:
    engine = create_engine(default_dialect=dialect)
    uri = engine.register_schema(schema, "https://facts.example/s")
    registry = engine.schemas
    root = registry.root_ref(uri)
    node = root.node
    assert is_object(node)
    keywords = registry.dialect_for(uri).keywords
    for name, value in node.items():
        entry = keywords[name]
        facts = entry.behavior.facts(value, node)
        for app in facts.applications:
            if app.ref is not None:
                registry.resolve_ref(app.ref, uri)
                continue
            head = app.sibling if app.sibling is not None else name
            target = registry.child(root, [head, *app.path])
            assert target.node is not None or target.node is None  # resolved
            # An application into this keyword's own value lands on a
            # position the walk claimed.
            if app.sibling is None:
                assert app.path in facts.subschemas, (name, app)
        # Every walked position is either applied by this keyword, applied
        # by a sibling (`then`/`else`), or reachable only by reference
        # (`$defs`/`definitions`, structural).
        if entry.behavior.structural or name in ("then", "else"):
            continue
        applied = {app.path for app in facts.applications if app.sibling is None}
        assert set(facts.subschemas) <= applied, (name, facts.subschemas, applied)
