def test_test_kit_module_imports_and_has_docstring():
    import json_schema_engine.test_kit as test_kit

    assert isinstance(test_kit.__doc__, str)
    assert test_kit.__doc__.strip() != ""
