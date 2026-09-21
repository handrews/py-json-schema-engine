"""ECMA-262 regular expressions for Python.

Parse an ECMA-262 pattern, translate it into a pattern string for Python's
:mod:`re` (or the third-party ``regex`` module), and match with JavaScript
semantics. This exists because several widely used data formats -- JSON
Schema above all -- specify their regular expressions as ECMA-262
patterns, and a Python program that hands those patterns straight to
:mod:`re` silently gets different answers.

    >>> import ecma_regex
    >>> ecma_regex.compile("^a+$").search("aaa\\n")
    False
    >>> ecma_regex.compile(r"^\\p{Letter}+$").search("ol\\u00e9")
    True

Scope
-----
The dialect implemented is ECMA-262 22.2 with the ``u`` flag: the
Unicode-mode pattern grammar, which is strict where the web-compatibility
grammar of Annex B is lenient. ``i``, ``m`` and ``s`` are supported and
recorded on the AST; ``u`` is accepted and implied. The stateful flags
``g`` and ``y``, the index flag ``d`` and the ``v`` set-notation flag are
rejected: this package models a single stateless, unanchored match.

Everything the grammar allows is parsed, including lookbehind, named
groups and named backreferences, ``\\uXXXX`` (with surrogate-pair
combining), ``\\u{...}``, ``\\xHH``, ``\\cX``, ``\\0``, and ``\\p{...}`` /
``\\P{...}`` property escapes.

What the translation fixes
--------------------------
Each of these silently changes a verdict if a pattern is handed to
:mod:`re` unchanged. The emitted pattern spells out the ECMA-262 meaning.

==================  =========================  ============================
Construct           Python ``re``              ECMA-262 (what is emitted)
==================  =========================  ============================
``^`` / ``$``       ``$`` also matches before  ``\\A`` / ``\\Z``
                    a final ``\\n``
``^`` / ``$`` (m)   line breaks are ``\\n``    lookarounds over LF, CR,
                    only                       LS (U+2028), PS (U+2029)
``.``               excludes ``\\n`` only      excludes LF, CR, LS, PS
``\\d``             any Unicode decimal        ``[0-9]``
``\\w``             any Unicode word char      ``[A-Za-z0-9_]``
``\\s``             a different space set      ECMA WhiteSpace plus
                                               LineTerminator, incl. U+FEFF
                                               and excl. U+001C-U+001F
``\\b``             Unicode word boundary      ASCII word boundary
``\\D \\W \\S``     as above, negated          explicit complement ranges,
                                               inside classes too
``\\p{...}``        rejected outright          explicit ranges (``re``) or
                                               native (``regex``)
``(?<name>)``       ``(?P<name>)``             rewritten, ``$`` in names
                                               escaped
``\\k<name>``       ``(?P=name)``              rewritten
==================  =========================  ============================

Residual divergences
--------------------
These cannot be closed inside a backend pattern and are documented rather
than fixed:

* **Case folding.** The ``i`` flag compiles with ``re.IGNORECASE``, which
  applies Python's full case folding. ECMA-262 ``u`` mode uses *simple*
  case folding. The two agree on everything but a handful of code points
  (for example Python folds ``ß`` to ``ss``-like equivalences that
  ECMA-262 does not).
* **``\\b`` with both ``i`` and ``u``.** ECMA-262 adds U+017F and U+212A
  to the word-character set in that combination. This package does not.
* **Variable-width lookbehind.** Python's :mod:`re` requires a fixed
  width, so a variable-width lookbehind raises
  :class:`UnsupportedPatternError` on the ``re`` backend. It works on the
  ``regex`` backend.
* **Unicode scripts.** ``\\p{Script=...}`` and
  ``\\p{Script_Extensions=...}`` parse, but the standard library ships no
  script data, so they are only translatable on the ``regex`` backend, and
  script *names* are not validated. General_Category values are validated
  and translatable everywhere.
* **Binary properties.** Those derivable from the standard library
  (``ASCII``, ``Assigned``, ``Any``, ``White_Space``, ``Lowercase``,
  ``Uppercase``, ``XID_Start``, ``XID_Continue``, ``Hex_Digit``,
  ``ASCII_Hex_Digit``, ``Bidi_Control``, ``Bidi_Mirrored``,
  ``Join_Control``, ``Noncharacter_Code_Point``, ``Regional_Indicator``)
  are translatable on both backends. The remaining ECMA-262 binary
  properties (``Alphabetic``, ``Math``, ``Emoji``, ...) are recognized as
  valid syntax but raise :class:`UnsupportedPatternError` on ``re``.
* **Unicode version.** Property sets come from the running interpreter's
  :mod:`unicodedata`, not from the Unicode version a given JavaScript
  engine ships.

Cost
----
The first ``\\p{...}`` translated on the ``re`` backend scans every code
point to build its range list (roughly 50 ms for a General_Category
property, up to a few hundred for a predicate-derived binary property).
The result is cached process-wide, so every later use is a dict hit.
"""

from .analysis import star_height, width
from .ast import (
    Alternation,
    Anchor,
    Backreference,
    CharClass,
    ClassEscape,
    ClassItem,
    ClassRange,
    Concatenation,
    Dot,
    Flags,
    Group,
    Literal,
    Lookaround,
    Node,
    Pattern,
    PropertyEscape,
    Quantifier,
    WordBoundary,
)
from .errors import EcmaRegexError, EcmaRegexSyntaxError, UnsupportedPatternError
from .matcher import CompiledPattern, EcmaRegex, compile
from .parser import parse
from .translator import BackendName, translate, translate_flags

__all__ = [
    "Alternation",
    "Anchor",
    "BackendName",
    "Backreference",
    "CharClass",
    "ClassEscape",
    "ClassItem",
    "ClassRange",
    "CompiledPattern",
    "Concatenation",
    "Dot",
    "EcmaRegex",
    "EcmaRegexError",
    "EcmaRegexSyntaxError",
    "Flags",
    "Group",
    "Literal",
    "Lookaround",
    "Node",
    "Pattern",
    "PropertyEscape",
    "Quantifier",
    "UnsupportedPatternError",
    "WordBoundary",
    "compile",
    "parse",
    "star_height",
    "translate",
    "translate_flags",
    "width",
]
