def test_ecma_regex_module_imports_and_has_docstring() -> None:
    import ecma_regex

    assert isinstance(ecma_regex.__doc__, str)
    assert ecma_regex.__doc__.strip() != ""
