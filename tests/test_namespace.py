def test_json_schema_engine_is_a_namespace_package():
    import json_schema_engine

    assert json_schema_engine.__file__ is None


def test_core_and_test_kit_both_import_under_the_namespace():
    import json_schema_engine.core
    import json_schema_engine.test_kit

    assert json_schema_engine.core
    assert json_schema_engine.test_kit
