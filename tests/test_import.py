def test_core_module_imports_and_has_docstring():
    import json_schema_engine.core as core

    assert isinstance(core.__doc__, str)
    assert core.__doc__.strip() != ""


def test_json_schema_engine_is_a_namespace_package():
    import json_schema_engine

    assert json_schema_engine.__file__ is None
    assert list(json_schema_engine.__path__)
