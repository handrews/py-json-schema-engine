"""The divergences that make this package necessary.

Every assertion here states the *ECMA-262* answer. Most of them are the
opposite of what Python's ``re`` gives for the same pattern text, and each
one is a place where a JSON Schema implementation that forwarded the
pattern to ``re`` unchanged would report the wrong verdict.
"""

import re

import pytest

import ecma_regex
from ecma_regex import EcmaRegexSyntaxError, UnsupportedPatternError


def matches(pattern: str, text: str, flags: str = "") -> bool:
    return ecma_regex.compile(pattern, flags=flags).search(text)


# -- anchors -------------------------------------------------------------


def test_dollar_does_not_match_before_a_trailing_newline() -> None:
    assert matches("^a+$", "aaa") is True
    assert matches("^a+$", "aaa\n") is False
    # ... which is exactly where bare `re` disagrees.
    assert re.search("^a+$", "aaa\n") is not None


def test_multiline_anchors_use_ecma_line_terminators() -> None:
    assert matches("^b$", "a\nb\nc", flags="m") is True
    assert matches("^b$", "a\u2028b\u2028c", flags="m") is True
    assert matches("^b$", "a\rb\rc", flags="m") is True
    assert matches("^b$", "a\u2028b\u2028c") is False
    # `re` with MULTILINE knows only \n, so U+2028 is invisible to it.
    assert re.search("^b$", "a\u2028b\u2028c", re.MULTILINE) is None


# -- the dot -------------------------------------------------------------


def test_dot_excludes_every_ecma_line_terminator() -> None:
    assert matches("f.o", "fxo") is True
    assert matches("f.o", "f\ro") is False
    assert matches("f.o", "f\no") is False
    assert matches("f.o", "f\u2028o") is False
    assert matches("f.o", "f\u2029o") is False
    # `re` excludes only \n from the dot.
    assert re.search("f.o", "f\ro") is not None


def test_dot_all_flag_matches_line_terminators() -> None:
    assert matches("f.o", "f\no", flags="s") is True
    assert matches("f.o", "f\u2028o", flags="s") is True


# -- class escapes -------------------------------------------------------


def test_digit_escape_is_ascii_only() -> None:
    assert matches(r"\d", "5") is True
    assert matches(r"\d", "٣") is False  # ARABIC-INDIC DIGIT THREE
    assert re.search(r"\d", "٣") is not None


def test_word_escape_is_ascii_only() -> None:
    assert matches(r"\w", "a") is True
    assert matches(r"\w", "é") is False
    assert re.search(r"\w", "é") is not None


def test_space_escape_uses_the_ecma_whitespace_set() -> None:
    assert matches(r"\s", "\ufeff") is True  # ZWNBSP is ECMA WhiteSpace
    assert matches(r"\s", "\x1c") is False  # FILE SEPARATOR is not
    assert matches(r"\s", "\u00a0") is True
    assert matches(r"\s", "\u2028") is True
    assert re.search(r"\s", "\ufeff") is None
    assert re.search(r"\s", "\x1c") is not None


def test_negated_class_escapes_are_the_exact_complements() -> None:
    assert matches(r"\D", "٣") is True
    assert matches(r"\D", "5") is False
    assert matches(r"\W", "é") is True
    assert matches(r"\S", "\ufeff") is False
    assert matches(r"\S", "\x1c") is True


def test_negated_class_escape_inside_a_character_class() -> None:
    assert matches(r"[^\d]", "a") is True
    assert matches(r"[^\d]", "5") is False
    assert matches(r"[^\d]", "٣") is True
    # `re` cannot even express a negated class escape inside a class the
    # way ECMA means it; the translation expands to explicit ranges.
    assert matches(r"[\D]", "٣") is True
    assert matches(r"[\Da-z]", "5") is False
    assert matches(r"[\W\d]", "5") is True


# -- word boundaries -----------------------------------------------------


def test_word_boundary_uses_the_ascii_word_definition() -> None:
    assert matches(r"\bfoo\b", "éfoo") is True
    assert matches(r"\bfoo\b", "xfoo") is False
    assert matches(r"\Bfoo", "xfoo") is True
    assert matches(r"\Bfoo", "éfoo") is False
    # `re` treats é as a word character, so there is no boundary there.
    assert re.search(r"\bfoo\b", "éfoo") is None


# -- property escapes ----------------------------------------------------


def test_property_escapes_translate_to_explicit_ranges() -> None:
    assert matches(r"\p{Letter}", "é") is True
    assert matches(r"\p{Letter}", "字") is True
    assert matches(r"\p{Letter}", "1") is False
    assert matches(r"^\p{Letter}+$", "olé") is True
    assert matches(r"^\p{Letter}+$", "olé1") is False


def test_negated_property_escape() -> None:
    assert matches(r"\P{L}", "1") is True
    assert matches(r"\P{L}", "é") is False
    assert matches(r"^\P{L}+$", "123 ") is True


def test_property_escape_spellings_and_valued_form() -> None:
    assert matches(r"\p{L}", "a") is True
    assert matches(r"\p{Lu}", "A") is True
    assert matches(r"\p{Lu}", "a") is False
    assert matches(r"\p{General_Category=Decimal_Number}", "7") is True
    assert matches(r"\p{Nd}", "٣") is True
    assert matches(r"\p{White_Space}", "\t") is True
    assert matches(r"\p{ASCII}", "é") is False


def test_property_escape_inside_a_character_class() -> None:
    assert matches(r"[\p{Nd}_]", "_") is True
    assert matches(r"[\p{Nd}_]", "٣") is True
    assert matches(r"[\p{Nd}_]", "a") is False
    assert matches(r"[^\p{L}]", "a") is False
    assert matches(r"[^\p{L}]", "1") is True


def test_unknown_property_name_is_a_syntax_error() -> None:
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"\p{Nope}")
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"\p{Script}")  # valued property, no value
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"\p{General_Category=Nope}")


def test_scripts_parse_but_do_not_translate_on_the_re_backend() -> None:
    parsed = ecma_regex.parse(r"\p{Script=Greek}")
    assert isinstance(parsed.root, ecma_regex.PropertyEscape)
    with pytest.raises(UnsupportedPatternError):
        ecma_regex.translate(parsed, backend="re")


def test_uncomputable_binary_property_is_unsupported_not_invalid() -> None:
    parsed = ecma_regex.parse(r"\p{Alphabetic}")
    with pytest.raises(UnsupportedPatternError):
        ecma_regex.translate(parsed, backend="re")


# -- groups, backreferences, lookaround ----------------------------------


def test_backreference() -> None:
    assert matches(r"(a)\1", "aa") is True
    assert matches(r"(a)\1", "ab") is False
    # A digit literal right after a backreference must not be absorbed
    # by the emitted `\1`; ECMA writes that literal as an escape, since
    # `\12` on its own would be a reference to group 12.
    assert matches(r"(a)\1\u0032", "aa2") is True
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"(a)\12")
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"(a)\2")


def test_named_group_and_named_backreference() -> None:
    assert matches(r"(?<pair>a)\k<pair>", "aa") is True
    assert matches(r"(?<pair>a)\k<pair>", "ab") is False
    compiled = ecma_regex.compile(r"(?<pair>ab)")
    assert "(?P<pair>" in compiled.translated
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"(?<a>x)(?<a>y)")
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"\k<missing>")


def test_group_name_with_a_dollar_sign_is_rewritten_for_python() -> None:
    compiled = ecma_regex.compile(r"(?<a$b>x)\k<a$b>")
    assert "$" not in compiled.translated
    assert compiled.search("xx") is True


def test_lookahead_and_fixed_width_lookbehind() -> None:
    assert matches("(?<=a)b", "ab") is True
    assert matches("(?<=a)b", "cb") is False
    assert matches("(?<!a)b", "cb") is True
    assert matches("a(?=b)", "ab") is True
    assert matches("a(?!b)", "ab") is False
    assert matches("(?<=ab|cd)e", "cde") is True


def test_variable_width_lookbehind_is_unsupported_on_re() -> None:
    with pytest.raises(UnsupportedPatternError):
        ecma_regex.compile("(?<=ab?)c")
    with pytest.raises(UnsupportedPatternError):
        ecma_regex.compile(r"(?<=(a)\1)b")


# -- literals and escapes ------------------------------------------------


def test_code_point_escapes() -> None:
    assert matches(r"\u{1F600}", "\U0001f600") is True
    assert matches(r"😀", "\U0001f600") is True  # surrogate pair
    assert matches(r"A", "A") is True
    assert matches(r"\x41", "A") is True
    assert matches(r"\cJ", "\n") is True
    assert matches(r"\0", "\x00") is True
    assert matches(r"[\t\n\v\f\r]", "\v") is True
    assert matches(r"[\b]", "\b") is True  # backspace inside a class


def test_characters_that_are_literal_in_ecma_are_escaped_for_python() -> None:
    assert matches(r"a\{2\}", "a{2}") is True
    assert matches("#", "#") is True
    assert matches(r"[a\-b]", "-") is True
    assert matches("[.^$]", ".") is True
    # `\-` is a class-only escape in u-mode; outside a class it is invalid.
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse(r"a\-b")


def test_empty_character_classes() -> None:
    assert matches("[]", "") is False
    assert matches("[]", "a") is False
    assert matches("[^]", "a") is True
    assert matches("[^]", "\n") is True


# -- quantifiers ---------------------------------------------------------


def test_quantifier_forms() -> None:
    assert matches("^a{2,3}$", "aa") is True
    assert matches("^a{2,3}$", "aaaa") is False
    assert matches("^a{2,}$", "aaaa") is True
    assert matches("^a{2}$", "aa") is True
    assert matches("^a{2}$", "aaa") is False
    assert matches("^(?:ab)+$", "abab") is True
    assert matches("^a+?b$", "aab") is True


def test_open_brace_must_begin_a_quantifier_in_unicode_mode() -> None:
    # In u-mode `{` is not a literal: `a{,3}` is a syntax error, not a
    # five-character match the way Annex B's web grammar would read it.
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse("a{,3}")
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse("a{2")
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse("{")
    assert matches(r"^a\{,3\}$", "a{,3}") is True


def test_nested_quantifiers_are_a_syntax_error() -> None:
    for pattern in ("a**", "a*+", "a??*", "a{1,2}{3}"):
        with pytest.raises(EcmaRegexSyntaxError):
            ecma_regex.parse(pattern)


def test_assertions_may_not_be_quantified_in_unicode_mode() -> None:
    for pattern in ("(?=a)*", r"\b*", "^*"):
        with pytest.raises(EcmaRegexSyntaxError):
            ecma_regex.parse(pattern)


# -- other syntax errors -------------------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        "(",
        ")",
        "a)",
        "[a",
        "[b-a]",
        "[\\d-z]",
        "\\",
        "\\1",
        "\\a",
        "]",
        "}",
        "\\u{110000}",
        "\\u12",
        "\\x1",
        "(?#comment)",
        "\\p{L",
    ],
)
def test_invalid_patterns_raise_a_syntax_error(pattern: str) -> None:
    with pytest.raises(EcmaRegexSyntaxError) as info:
        ecma_regex.parse(pattern)
    assert isinstance(info.value.position, int)
    assert info.value.position >= 0


# -- flags ---------------------------------------------------------------


def test_flags_are_recorded_and_applied() -> None:
    assert ecma_regex.parse("a", flags="ims").flags == ecma_regex.Flags(
        ignore_case=True, multiline=True, dot_all=True, unicode=True
    )
    assert ecma_regex.parse("a", flags="u").flags.unicode is True
    assert matches("^ABC$", "abc", flags="i") is True
    assert matches("^ABC$", "abc") is False
    assert matches(r"^\p{Lu}$", "a", flags="i") is True


@pytest.mark.parametrize("flags", ["g", "y", "d", "v"])
def test_stateful_and_set_notation_flags_are_unsupported(flags: str) -> None:
    with pytest.raises(UnsupportedPatternError):
        ecma_regex.parse("a", flags=flags)


@pytest.mark.parametrize("flags", ["x", "ii", "z"])
def test_unknown_or_duplicated_flags_are_syntax_errors(flags: str) -> None:
    with pytest.raises(EcmaRegexSyntaxError):
        ecma_regex.parse("a", flags=flags)


# -- star height ---------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("abc", 0),
        ("a{2,3}", 0),
        ("a?", 0),
        ("a+", 1),
        ("a*", 1),
        ("a{2,}", 1),
        ("a+b+", 1),
        ("(a+)+", 2),
        ("(?:a{1,}){2,}", 2),
        ("((a+)*)+", 3),
        ("(a+|b)*", 2),
        ("(?=a+)b", 1),
    ],
)
def test_star_height(pattern: str, expected: int) -> None:
    assert ecma_regex.star_height(ecma_regex.parse(pattern)) == expected


# -- the public surface --------------------------------------------------


def test_compiled_object_exposes_the_pieces() -> None:
    compiled = ecma_regex.compile("^foo$", flags="i")
    assert compiled.pattern == "^foo$"
    assert compiled.flags == "i"
    assert compiled.translated == "\\Afoo\\Z"
    assert compiled.backend == "re"
    assert compiled.compiled.search("FOO") is not None
    assert ecma_regex.translate_flags(ecma_regex.parse("a", flags="i")) == re.IGNORECASE
    assert ecma_regex.translate_flags(ecma_regex.parse("a")) == 0


def test_errors_share_a_base_and_carry_a_position() -> None:
    assert issubclass(EcmaRegexSyntaxError, ecma_regex.EcmaRegexError)
    assert issubclass(UnsupportedPatternError, ecma_regex.EcmaRegexError)
    with pytest.raises(ecma_regex.EcmaRegexError) as info:
        ecma_regex.parse("a{,3}")
    assert info.value.position == 1
    assert info.value.message


def test_translation_output_is_stable() -> None:
    assert ecma_regex.translate(ecma_regex.parse(r"\d")) == "[0-9]"
    assert ecma_regex.translate(ecma_regex.parse(r"\w")) == "[0-9A-Z_a-z]"
    assert ecma_regex.translate(ecma_regex.parse("a|b")) == "a|b"
    assert ecma_regex.translate(ecma_regex.parse("(?:a|b)+")) == "(?:a|b)+"


# -- the optional `regex` backend ----------------------------------------


def test_regex_backend_emits_property_escapes_natively() -> None:
    pytest.importorskip("regex")
    compiled = ecma_regex.compile(r"\p{L}+", backend="regex")
    assert compiled.translated == r"\p{L}+"
    assert compiled.backend == "regex"
    assert compiled.search("olé") is True
    assert ecma_regex.compile(r"[^\p{L}]", backend="regex").translated == r"[^\p{L}]"


def test_regex_backend_supports_scripts_and_variable_lookbehind() -> None:
    pytest.importorskip("regex")
    greek = ecma_regex.compile(r"^\p{Script=Greek}+$", backend="regex")
    assert greek.search("αβγ") is True
    assert greek.search("abc") is False
    variable = ecma_regex.compile("(?<=ab?)c", backend="regex")
    assert variable.search("ac") is True
    assert variable.search("bc") is False


def test_regex_backend_still_uses_the_ecma_class_escape_sets() -> None:
    pytest.importorskip("regex")
    assert ecma_regex.compile(r"\d", backend="regex").search("٣") is False
    assert ecma_regex.compile(r"\s", backend="regex").search("﻿") is True
    assert ecma_regex.compile(r"\w", backend="regex").search("é") is False
