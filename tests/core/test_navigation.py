# Navigation follows registration (DESIGN.md P16). An `$id` identifies only
# in a schema position, and only the registration walk knows which
# positions those are; pointer navigation and `child` rebase only where the
# registry holds a resource and the node they stepped onto is it.

import copy

from json_schema_engine.core import JsonValue, create_engine

# The §7 example, with the data under `examples` rather than `enum` so the
# verdict is the `$ref`'s alone.
GHOST: JsonValue = {
    "$id": "https://r.example/",
    "$ref": "#/examples/0/properties/a",
    "examples": [
        {"$id": "https://ghost.example/", "properties": {"a": {"type": "string"}}}
    ],
}


def test_an_id_in_data_does_not_rebase() -> None:
    # Used to raise `unknown schema 'https://ghost.example/'`: navigation
    # rebased onto an identifier the walk correctly never indexed.
    engine = create_engine()
    uri = engine.register_schema(GHOST, "https://r.example/")
    assert engine.evaluate(uri, "s").valid is True
    assert engine.evaluate(uri, 1).valid is False
    hit = engine.schemas.resolve_ref("#/examples/0/properties/a", uri)
    assert (hit.base_uri, hit.pointer) == (
        "https://r.example/",
        "/examples/0/properties/a",
    )


def test_the_enum_form_no_longer_raises() -> None:
    # The shape DESIGN.md recorded: `enum` data, which fails the instance
    # on its own account but must not make evaluation raise.
    engine = create_engine()
    uri = engine.register_schema(
        {
            "$id": "https://r.example/e",
            "$ref": "#/enum/0/properties/a",
            "enum": [{"$id": "https://ghost.example/", "properties": {"a": {}}}],
        },
        "https://r.example/e",
    )
    assert engine.evaluate(uri, "s").valid is False


def test_an_id_in_data_naming_a_real_resource_does_not_rebase() -> None:
    # The suite's `optional/unknownKeyword.json` shape: the data `$id` is
    # the URI of a real resource with different content.
    real = "https://r.example/real"
    engine = create_engine()
    uri = engine.register_schema(
        {
            "$id": "https://r.example/doc",
            "$defs": {"real": {"$id": real, "type": "string"}},
            "x-unknown": {"$id": real, "properties": {"a": {"type": "integer"}}},
        },
        "https://r.example/doc",
    )
    hit = engine.schemas.resolve_ref("#/x-unknown/properties/a", uri)
    assert (hit.base_uri, hit.pointer) == (uri, "/x-unknown/properties/a")
    assert hit.location == "https://r.example/doc#/x-unknown/properties/a"


def test_a_relative_ref_inside_an_unknown_keyword_uses_the_enclosing_base() -> None:
    engine = create_engine()
    engine.register_schema({"type": "integer"}, "https://r.example/target")
    uri = engine.register_schema(
        {
            "$id": "https://r.example/outer",
            "$ref": "#/x-foo/properties/a",
            "x-foo": {
                "$id": "https://elsewhere.example/dir/",
                "properties": {"a": {"$ref": "target"}},
            },
        },
        "https://r.example/outer",
    )
    # `target` resolves against `outer`, not against the data `$id`.
    assert engine.evaluate(uri, 1).valid is True
    assert engine.evaluate(uri, "s").valid is False


def test_an_equal_copy_that_was_taken_over_still_rebases() -> None:
    # After B's equal copy takes `r` over (P15), A's copy is a different
    # object with the same content; entering it must still rebase, or the
    # relative `$ref` inside would resolve against A.
    engine = create_engine()
    engine.register_schema({"type": "integer"}, "https://r.example/lib/target")
    body: JsonValue = {
        "$ref": "#/$defs/r",
        "$defs": {"r": {"$id": "https://r.example/lib/r", "$ref": "target"}},
    }
    a = engine.register_schema(body, "https://r.example/a")
    # A separate parse, as a second document always is: equal, not identical.
    engine.register_schema(copy.deepcopy(body), "https://r.example/b")
    hit = engine.schemas.resolve_ref("#/$defs/r", a)
    assert (hit.base_uri, hit.pointer) == ("https://r.example/lib/r", "")
    assert engine.evaluate(a, 1).valid is True
    assert engine.evaluate(a, "s").valid is False


def test_child_follows_the_same_rule() -> None:
    engine = create_engine()
    uri = engine.register_schema(GHOST, "https://r.example/")
    root = engine.schemas.root_ref(uri)
    step = engine.schemas.child(root, ["examples", 0])
    assert (step.base_uri, step.pointer) == ("https://r.example/", "/examples/0")
