"""Output units, annotation selection, and the document renderers over a
hand-built located tree (D5, D6)."""

from typing import Any, cast

import pytest

from json_schema_engine.core.channel import KeywordTrace
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationsOption,
    AnnotationUnit,
    ErrorUnit,
    RenderInput,
    RenderNode,
    make_record_predicate,
    render_basic,
    render_detailed,
    render_flag,
    render_hierarchical,
    render_list,
    render_trace,
    render_verbose,
    select_units,
)


def make_annotation(
    *,
    keyword: str = "title",
    vocabulary: str | None = "https://json-schema.org/vocab/meta-data",
    annotation: JsonValue = "A title",
    evaluation_path: str = "/title",
    schema_location: str = "https://example.com/s#/title",
    input_location: str = "",
) -> AnnotationUnit:
    unit: AnnotationUnit = {
        "evaluationPath": evaluation_path,
        "schemaLocation": schema_location,
        "inputLocation": input_location,
        "keyword": keyword,
        "annotation": annotation,
    }
    if vocabulary is not None:
        unit["vocabulary"] = vocabulary
    return unit


def make_error(
    *,
    evaluation_path: str = "/type",
    schema_location: str = "https://example.com/s#/type",
    input_location: str = "",
    error: str = "not a string",
) -> ErrorUnit:
    return {
        "evaluationPath": evaluation_path,
        "schemaLocation": schema_location,
        "inputLocation": input_location,
        "error": error,
    }


# --- make_record_predicate / select_units: selection semantics (D5) --------


def test_false_selection_records_and_selects_nothing():
    assert make_record_predicate(False) is None
    assert select_units([make_annotation()], False) == []


def test_true_selection_keeps_everything():
    predicate = make_record_predicate(True)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("anything", "urn:whatever") is True
    units = [
        make_annotation(keyword="title"),
        make_annotation(keyword="x-vendor", vocabulary=None),
    ]
    assert select_units(units, True) == units


def test_both_allow_lists_none_allows_everything():
    selection = AnnotationSelection()
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("description", "urn:example:vocab") is True


def test_keyword_allow_list_excludes_unlisted_keywords():
    selection = AnnotationSelection(keywords=frozenset({"title"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("description", None) is False


def test_vocabulary_allow_list_excludes_unlisted_vocabularies():
    selection = AnnotationSelection(vocabularies=frozenset({"urn:v1"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("anything", "urn:v1") is True
    assert predicate("anything", "urn:v2") is False
    # No vocabulary at all cannot match a vocabulary allow-list.
    assert predicate("anything", None) is False


def test_allow_lists_are_ored():
    selection = AnnotationSelection(
        keywords=frozenset({"title"}), vocabularies=frozenset({"urn:v1"})
    )
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", "urn:other") is True  # matches keywords
    assert predicate("other", "urn:v1") is True  # matches vocabularies
    assert predicate("other", "urn:other") is False


def test_deny_lists_subtract_after_allow():
    selection = AnnotationSelection(exclude_keywords=frozenset({"description"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("description", None) is False


def test_deny_vocabulary_subtracts_after_allow():
    selection = AnnotationSelection(exclude_vocabularies=frozenset({"urn:v1"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("anything", "urn:v1") is False
    assert predicate("anything", "urn:v2") is True


def test_allow_and_deny_combine_deny_wins():
    # A keyword can be both allow-listed and deny-listed; the deny list is
    # subtracted after, so it wins.
    selection = AnnotationSelection(
        keywords=frozenset({"title"}), exclude_keywords=frozenset({"title"})
    )
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is False


def test_keep_does_not_affect_make_record_predicate():
    # D5: keep runs only at render time; the record-time predicate must
    # record the superset keep might narrow, never elide on its behalf.
    selection = AnnotationSelection(keep=lambda unit: False)
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True


def test_select_units_applies_keep_last():
    selection = AnnotationSelection(keep=lambda unit: unit["annotation"] != "hidden")
    units = [
        make_annotation(keyword="title", annotation="shown"),
        make_annotation(keyword="description", annotation="hidden"),
    ]
    selected = select_units(units, selection)
    assert [u["keyword"] for u in selected] == ["title"]


def test_select_units_applies_allow_then_keep():
    selection = AnnotationSelection(
        keywords=frozenset({"title", "description"}),
        keep=lambda unit: unit["keyword"] == "title",
    )
    units = [
        make_annotation(keyword="title"),
        make_annotation(keyword="description"),
        make_annotation(keyword="x-vendor", vocabulary=None),
    ]
    selected = select_units(units, selection)
    assert [u["keyword"] for u in selected] == ["title"]


def test_predicate_ignores_vocabulary_none_against_deny_vocab():
    # A `None` vocabulary_uri can never match a deny-list of vocabularies.
    selection = AnnotationSelection(exclude_vocabularies=frozenset({"urn:v1"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("x-vendor", None) is True


# --- render_flag -------------------------------------------------------


def test_render_flag_document():
    assert render_flag(True) == {"valid": True}
    assert render_flag(False) == {"valid": False}


# --- render_basic (IETF draft-03 §13.4.2) ----------------------------------

ROOT = "https://example.com/s#"


def _root(valid: bool) -> dict[str, object]:
    return {
        "valid": valid,
        "keywordLocation": "",
        "absoluteKeywordLocation": ROOT,
        "instanceLocation": "",
    }


def test_render_basic_valid_with_no_annotations_omits_both_keys():
    assert render_basic(True, ROOT, [], []) == _root(True)


def test_render_basic_valid_with_annotations_uses_draft_names():
    annotation = make_annotation(
        evaluation_path="/properties/x/title", input_location="/x"
    )
    assert render_basic(True, ROOT, [], [annotation]) == {
        **_root(True),
        "annotations": [
            {
                "keywordLocation": "/properties/x/title",
                "absoluteKeywordLocation": "https://example.com/s#/title",
                "instanceLocation": "/x",
                "annotation": "A title",
            }
        ],
    }


def test_render_basic_invalid_always_carries_errors_key():
    assert render_basic(False, ROOT, [make_error()], []) == {
        **_root(False),
        "errors": [
            {
                "keywordLocation": "/type",
                "absoluteKeywordLocation": "https://example.com/s#/type",
                "instanceLocation": "",
                "error": "not a string",
            }
        ],
    }


def test_render_basic_is_mutually_exclusive():
    error = make_error()
    annotation = make_annotation()
    assert "errors" not in render_basic(True, ROOT, [error], [annotation])
    assert "annotations" not in render_basic(False, ROOT, [error], [annotation])


# --- the located tree, built by hand ---------------------------------------


def node(
    path: str = "",
    *,
    valid: bool = True,
    location: str | None = None,
    instance: str = "",
    keywords: tuple[tuple[str, bool], ...] = (),
    errors: tuple[int, ...] = (),
    dropped_errors: tuple[int, ...] = (),
    annotations: tuple[int, ...] = (),
    dropped_annotations: tuple[int, ...] = (),
    children: tuple[RenderNode, ...] = (),
) -> RenderNode:
    return RenderNode(
        evaluation_path=path,
        schema_location=ROOT + path if location is None else location,
        input_location=instance,
        valid=valid,
        keywords=tuple(KeywordTrace(n, v) for n, v in keywords),
        errors=errors,
        dropped_errors=dropped_errors,
        annotations=annotations,
        dropped_annotations=dropped_annotations,
        children=children,
    )


def render_input(
    root: RenderNode,
    *,
    errors: list[ErrorUnit] | None = None,
    dropped_errors: list[ErrorUnit] | None = None,
    annotations: list[AnnotationUnit] | None = None,
    dropped_annotations: list[AnnotationUnit] | None = None,
) -> RenderInput:
    return RenderInput(
        errors=errors or [],
        dropped_errors=dropped_errors or [],
        annotations=annotations or [],
        dropped_annotations=dropped_annotations or [],
        root=root,
    )


def loose(document: object) -> dict[str, Any]:
    """A document as a plain dict: the tests index `NotRequired` keys on
    purpose, asserting presence by access."""
    return cast(dict[str, Any], document)


def _err(path: str, error: str, instance: str = "") -> ErrorUnit:
    return make_error(
        evaluation_path=path,
        schema_location=ROOT + path,
        input_location=instance,
        error=error,
    )


def _ann(
    path: str, keyword: str, value: JsonValue, instance: str = ""
) -> AnnotationUnit:
    return make_annotation(
        keyword=keyword,
        evaluation_path=path,
        schema_location=ROOT + path,
        input_location=instance,
        annotation=value,
    )


# anyOf over two failing branches: the branches' errors precede the
# combiner's own error in encounter order, `required` reports twice, and
# each branch's title annotation was dropped with its frame.
ANYOF_ERRORS = [
    _err("/anyOf/0/required", "missing 'a'"),
    _err("/anyOf/0/required", "missing 'b'"),
    _err("/anyOf/1/type", "not a string"),
    _err("/anyOf", "no branch"),
]
ANYOF_DROPPED = [
    _ann("/anyOf/0/title", "title", "zero"),
    _ann("/title", "title", "root"),
]
ANYOF_TREE = node(
    valid=False,
    keywords=(("anyOf", False), ("title", True)),
    errors=(3,),
    dropped_annotations=(1,),
    children=(
        node(
            "/anyOf/0",
            valid=False,
            keywords=(("required", False), ("title", True)),
            errors=(0, 1),
            dropped_annotations=(0,),
        ),
        node("/anyOf/1", valid=False, keywords=(("type", False),), errors=(2,)),
    ),
)
ANYOF_INPUT = render_input(
    ANYOF_TREE, errors=ANYOF_ERRORS, dropped_annotations=ANYOF_DROPPED
)


def test_hierarchical_keys_errors_by_keyword_and_joins_messages():
    assert render_hierarchical(ANYOF_INPUT, "omit") == {
        "valid": False,
        "evaluationPath": "",
        "schemaLocation": ROOT,
        "instanceLocation": "",
        "errors": {"anyOf": "no branch"},
        "details": [
            {
                "valid": False,
                "evaluationPath": "/anyOf/0",
                "schemaLocation": ROOT + "/anyOf/0",
                "instanceLocation": "",
                "errors": {"required": "missing 'a'; missing 'b'"},
            },
            {
                "valid": False,
                "evaluationPath": "/anyOf/1",
                "schemaLocation": ROOT + "/anyOf/1",
                "instanceLocation": "",
                "errors": {"type": "not a string"},
            },
        ],
    }


def test_hierarchical_marks_dropped_records_only_at_the_verbose_level():
    marked = loose(render_hierarchical(ANYOF_INPUT, "mark"))
    assert marked["droppedAnnotations"] == {"title": "root"}
    assert marked["details"][0]["droppedAnnotations"] == {"title": "zero"}
    assert "droppedAnnotations" not in marked["details"][1]
    omitted = loose(render_hierarchical(ANYOF_INPUT, "omit"))
    assert "droppedAnnotations" not in omitted
    assert "droppedAnnotations" not in omitted["details"][0]


def test_hierarchical_prunes_empty_units_but_keeps_the_root():
    tree = node(
        keywords=(("properties", True),),
        children=(
            node("/properties/a", instance="/a", keywords=(("type", True),)),
            node(
                "/properties/b",
                instance="/b",
                keywords=(("title", True),),
                annotations=(0,),
            ),
        ),
    )
    ann = _ann("/properties/b/title", "title", "B", "/b")
    assert render_hierarchical(render_input(tree, annotations=[ann]), "omit") == {
        "valid": True,
        "evaluationPath": "",
        "schemaLocation": ROOT,
        "instanceLocation": "",
        "details": [
            {
                "valid": True,
                "evaluationPath": "/properties/b",
                "schemaLocation": ROOT + "/properties/b",
                "instanceLocation": "/b",
                "annotations": {"title": "B"},
            }
        ],
    }
    # Nothing at all: the root unit alone.
    bare = node(
        keywords=(("properties", True),),
        children=(
            node("/properties/a", instance="/a", keywords=(("type", True),)),
            node("/properties/b", instance="/b", keywords=(("title", True),)),
        ),
    )
    assert render_hierarchical(render_input(bare), "omit") == {
        "valid": True,
        "evaluationPath": "",
        "schemaLocation": ROOT,
        "instanceLocation": "",
    }
    # The verbose level keeps every unit.
    marked = loose(render_hierarchical(render_input(bare), "mark"))
    assert [u["evaluationPath"] for u in marked["details"]] == [
        "/properties/a",
        "/properties/b",
    ]


def test_hierarchical_keys_a_false_schema_error_under_the_empty_name():
    tree = node(
        valid=False,
        keywords=(("properties", False),),
        children=(node("/properties/x", valid=False, instance="/x", errors=(0,)),),
    )
    error = _err("/properties/x", "schema is false", "/x")
    document = loose(render_hierarchical(render_input(tree, errors=[error]), "omit"))
    assert document["details"] == [
        {
            "valid": False,
            "evaluationPath": "/properties/x",
            "schemaLocation": ROOT + "/properties/x",
            "instanceLocation": "/x",
            "errors": {"": "schema is false"},
        }
    ]


def test_hierarchical_decodes_escaped_keyword_segments():
    tree = node(valid=False, keywords=(("a/b", False),), errors=(0,))
    error = _err("/a~1b", "custom")
    document = loose(render_hierarchical(render_input(tree, errors=[error]), "omit"))
    assert document["errors"] == {"a/b": "custom"}


def test_list_flattens_in_preorder_and_keeps_only_reporting_units():
    assert render_list(ANYOF_INPUT, "omit") == {
        "valid": False,
        "details": [
            {
                "valid": False,
                "evaluationPath": "",
                "schemaLocation": ROOT,
                "instanceLocation": "",
                "errors": {"anyOf": "no branch"},
            },
            {
                "valid": False,
                "evaluationPath": "/anyOf/0",
                "schemaLocation": ROOT + "/anyOf/0",
                "instanceLocation": "",
                "errors": {"required": "missing 'a'; missing 'b'"},
            },
            {
                "valid": False,
                "evaluationPath": "/anyOf/1",
                "schemaLocation": ROOT + "/anyOf/1",
                "instanceLocation": "",
                "errors": {"type": "not a string"},
            },
        ],
    }


def test_list_verbose_level_includes_every_unit_with_markers():
    tree = node(
        keywords=(("properties", True),),
        children=(node("/properties/a", instance="/a", keywords=(("type", True),)),),
    )
    assert render_list(render_input(tree), "omit") == {"valid": True, "details": []}
    document = render_list(render_input(tree), "mark")
    assert [u["evaluationPath"] for u in document["details"]] == ["", "/properties/a"]
    assert all("details" not in u for u in document["details"])
    marked = loose(render_list(ANYOF_INPUT, "mark"))
    assert marked["details"][0]["droppedAnnotations"] == {"title": "root"}


# --- detailed / verbose: the draft-03 keyword-level tree ------------------


def test_verbose_renders_one_node_per_keyword_in_order():
    document = loose(render_verbose(ANYOF_INPUT))
    assert document["valid"] is False
    assert document["keywordLocation"] == ""
    nested = document["errors"]
    assert [(n["keywordLocation"], n["valid"]) for n in nested] == [
        ("/anyOf", False),
        ("/title", True),
    ]
    any_of = nested[0]
    assert any_of["error"] == "no branch"
    assert any_of["absoluteKeywordLocation"] == ROOT + "/anyOf"
    branches = any_of["errors"]
    assert [b["keywordLocation"] for b in branches] == ["/anyOf/0", "/anyOf/1"]
    # A failed branch nests its keyword nodes under `errors`.
    required = branches[0]["errors"][0]
    assert required["keywordLocation"] == "/anyOf/0/required"
    assert required["error"] == "missing 'a'; missing 'b'"
    # Dropped annotations render as the keyword node's own annotation.
    assert branches[0]["errors"][1] == {
        "valid": True,
        "keywordLocation": "/anyOf/0/title",
        "absoluteKeywordLocation": ROOT + "/anyOf/0/title",
        "instanceLocation": "",
        "annotation": "zero",
    }
    assert nested[1]["annotation"] == "root"


def test_detailed_condenses_and_omits_dropped_records():
    document = render_detailed(ANYOF_INPUT)
    # `title` had no relevant result and no children: removed. `anyOf`
    # keeps its own error and its two branches; each branch is replaced by
    # its single keyword node.
    assert document == {
        "valid": False,
        "keywordLocation": "",
        "absoluteKeywordLocation": ROOT,
        "instanceLocation": "",
        "errors": [
            {
                "valid": False,
                "keywordLocation": "/anyOf",
                "absoluteKeywordLocation": ROOT + "/anyOf",
                "instanceLocation": "",
                "error": "no branch",
                "errors": [
                    {
                        "valid": False,
                        "keywordLocation": "/anyOf/0/required",
                        "absoluteKeywordLocation": ROOT + "/anyOf/0/required",
                        "instanceLocation": "",
                        "error": "missing 'a'; missing 'b'",
                    },
                    {
                        "valid": False,
                        "keywordLocation": "/anyOf/1/type",
                        "absoluteKeywordLocation": ROOT + "/anyOf/1/type",
                        "instanceLocation": "",
                        "error": "not a string",
                    },
                ],
            }
        ],
    }


def test_detailed_keeps_the_root_even_when_empty():
    tree = node(keywords=(("type", True),))
    assert render_detailed(render_input(tree)) == {
        "valid": True,
        "keywordLocation": "",
        "absoluteKeywordLocation": ROOT,
        "instanceLocation": "",
    }


def test_draft03_tree_attaches_a_false_schema_error_to_the_application():
    tree = node(
        valid=False,
        keywords=(("properties", False),),
        children=(node("/properties/x", valid=False, instance="/x", errors=(0,)),),
    )
    error = _err("/properties/x", "schema is false", "/x")
    document = loose(render_verbose(render_input(tree, errors=[error])))
    application = document["errors"][0]["errors"][0]
    assert application["keywordLocation"] == "/properties/x"
    assert application["error"] == "schema is false"
    assert "errors" not in application


def test_draft03_tree_keeps_a_null_annotation():
    # A JSON null is a real annotation value: presence, not truthiness.
    tree = node(keywords=(("default", True),), annotations=(0,))
    ann = _ann("/default", "default", None)
    document = loose(render_verbose(render_input(tree, annotations=[ann])))
    leaf = document["annotations"][0]
    assert "annotation" in leaf and leaf["annotation"] is None
    condensed = loose(render_detailed(render_input(tree, annotations=[ann])))
    assert condensed["annotations"] == [leaf]


def test_draft03_tree_keeps_a_stray_application_under_its_parent():
    # A custom keyword applying with no segment of its own: the child shares
    # the parent's path and cannot be attributed to a keyword entry.
    tree = node(
        valid=False,
        keywords=(("custom", False),),
        children=(node("", valid=False, location=ROOT + "/$defs/t", errors=(0,)),),
    )
    error = _err("", "schema is false")
    document = loose(render_verbose(render_input(tree, errors=[error])))
    assert [n["keywordLocation"] for n in document["errors"]] == ["/custom", ""]


# --- trace -----------------------------------------------------------------


def test_trace_decodes_segments_below_the_parent_and_indexes_errors():
    tree = node(
        valid=False,
        keywords=(("properties", False),),
        errors=(1,),
        children=(
            node(
                "/properties/a~1b~0c",
                valid=False,
                instance="/a~1b~0c",
                keywords=(("type", False),),
                errors=(0,),
                children=(node("/properties/a~1b~0c/$ref", location=ROOT + "/x"),),
            ),
        ),
    )
    assert render_trace(tree) == {
        "segments": [],
        "schemaLocation": ROOT,
        "inputLocation": "",
        "valid": False,
        "errorIndexes": [1],
        "children": [
            {
                "segments": ["properties", "a/b~c"],
                "schemaLocation": ROOT + "/properties/a~1b~0c",
                "inputLocation": "/a~1b~0c",
                "valid": False,
                "errorIndexes": [0],
                "children": [
                    {
                        "segments": ["$ref"],
                        "schemaLocation": ROOT + "/x",
                        "inputLocation": "",
                        "valid": True,
                        "errorIndexes": [],
                        "children": [],
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize("selection", [False, True, AnnotationSelection()])
def test_annotations_option_accepts_bool_or_selection(
    selection: AnnotationsOption,
) -> None:
    # Type-level smoke test: every AnnotationsOption member is accepted.
    make_record_predicate(selection)
