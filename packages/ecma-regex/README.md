# ecma-regex

ECMA-262 regular expressions for Python: parse them, translate them to `re`
(or `regex`), and match with JavaScript semantics.

Several widely used data formats specify their regular expressions as
ECMA-262 patterns — JSON Schema above all. A Python program that hands
those patterns straight to `re` does not get an error; it gets *different
answers*, quietly, for `^`, `$`, `.`, `\d`, `\w`, `\s` and `\b`, and a hard
failure for `\p{...}`. This package closes that gap.

It has **no dependencies** and imports nothing from any consumer. It
happens to power [json-schema-engine][engine], but it does not depend on
it, and it is useful anywhere an ECMA-262 pattern has to run under Python.

[engine]: https://github.com/handrews/py-json-schema-engine

## Install

```sh
pip install ecma-regex
# optional: the `regex` backend, which adds variable-width lookbehind
# and native \p{Script=...} support
pip install 'ecma-regex[regex]'
```

Python 3.12+.

## Usage

```python
import ecma_regex

pattern = ecma_regex.compile(r"^\p{Letter}+$")
pattern.search("olé")  # True
pattern.search("olé1")  # False
pattern.translated  # the emitted `re` pattern
pattern.compiled  # the underlying re.Pattern

ecma_regex.compile("^a+$").search("aaa\n")  # False  (re says True)
ecma_regex.compile("f.o").search("f\ro")  # False  (re says True)
ecma_regex.compile(r"\d").search("٣")  # False  (re says True)
ecma_regex.compile("^b$", flags="m").search("a\u2028b")  # True
```

`search` has `RegExp.prototype.test` semantics: unanchored, boolean.

Lower-level entry points, if you want the pieces:

```python
tree = ecma_regex.parse(r"(?<year>\d{4})-\d{2}")  # an AST
source = ecma_regex.translate(tree)  # a backend pattern string
flags = ecma_regex.translate_flags(tree)  # re.IGNORECASE, or 0
depth = ecma_regex.star_height(tree)  # ReDoS screening
```

`star_height` reports the nesting depth of unbounded quantifiers — `a+` is
1, `(a+)+` is 2 — which is the classic necessary condition for
catastrophic backtracking. It over-reports; it is a screen, not a proof.

Nothing is cached at the `compile` level. Put your own cache in front of it
if you compile the same pattern repeatedly.

## Scope

The dialect is ECMA-262 §22.2 with the **`u` flag**: the Unicode-mode
pattern grammar. Annex B's web-compatibility leniencies (legacy octal
escapes, quantifiable assertions, a bare `{` as a literal, identity escapes
of arbitrary characters) are early errors under `u`, and they are errors
here too. `a{,3}`, `a**` and `(?=a)*` all raise.

| Flag | Status |
| --- | --- |
| `i` | supported (`re.IGNORECASE` at compile time) |
| `m` | supported (spelled out with lookarounds, not `re.MULTILINE`) |
| `s` | supported (spelled out, not `re.DOTALL`) |
| `u` | accepted and always implied |
| `g`, `y`, `d`, `v` | rejected — this models one stateless match |

Everything the grammar allows is parsed: lookbehind, backreferences, named
groups and `\k<name>`, `\uXXXX` (surrogate pairs combined), `\u{...}`,
`\xHH`, `\cX`, `\0`, `\t\n\v\f\r`, and `\p{...}` / `\P{...}`.

Invalid patterns raise `EcmaRegexSyntaxError`; valid-but-untranslatable
ones raise `UnsupportedPatternError`. Both subclass `EcmaRegexError` and
carry a `position`.

## Divergence table

What the translation fixes — each row is a silent change of verdict if the
pattern goes to `re` unchanged.

| Construct | Python `re` | ECMA-262 (what is emitted) |
| --- | --- | --- |
| `^` / `$` | `$` also matches before a final `\n` | `\A` / `\Z` |
| `^` / `$` with `m` | line breaks are `\n` only | lookarounds over LF, CR, U+2028, U+2029 |
| `.` | excludes `\n` only | excludes LF, CR, U+2028, U+2029 |
| `.` with `s` | `re.DOTALL` | `[\s\S]` |
| `\d` | any Unicode decimal digit | `[0-9]` |
| `\w` | any Unicode word character | `[A-Za-z0-9_]` |
| `\s` | a different set; misses U+FEFF, includes U+001C–U+001F | ECMA WhiteSpace ∪ LineTerminator |
| `\b` / `\B` | Unicode word boundary | ASCII word boundary, as explicit lookarounds |
| `\D` `\W` `\S` | as above, negated | explicit complement ranges |
| `\D` `\W` `\S` **inside a class** | not expressible | explicit complement ranges |
| `\p{...}` / `\P{...}` | `re.error` | explicit ranges (`re`) or native (`regex`) |
| `(?<name>…)` | different spelling | `(?P<name>…)`, with `$` in names rewritten |
| `\k<name>` | different spelling | `(?P=name)` |
| literal `{`, `#`, `-`, … | may be metacharacters | escaped |

## Residual divergences

These cannot be closed inside a backend pattern, so they are documented
rather than fixed.

| Area | Difference |
| --- | --- |
| Case folding | `i` compiles with `re.IGNORECASE`, which is Python's *full* case folding; ECMA-262 `u` mode uses *simple* case folding. They agree except on a handful of code points. |
| `\b` with `i` and `u` | ECMA-262 adds U+017F and U+212A to the word set in that combination; this package does not. |
| Variable-width lookbehind | `re` requires a fixed width, so `(?<=ab?)c` raises `UnsupportedPatternError` on the `re` backend. It works on `regex`. |
| `\p{Script=…}`, `\p{Script_Extensions=…}` | Parsed, but the standard library ships no script data: translatable only on the `regex` backend, and script *names* are not validated. |
| Some binary properties | `Alphabetic`, `Math`, `Emoji`, `Cased`, … are recognized as valid syntax but not derivable from the standard library; they raise `UnsupportedPatternError` on `re` and are emitted natively on `regex`. |
| Unicode version | Property sets come from the running interpreter's `unicodedata`, not from whatever version a given JavaScript engine ships. |

Properties that *are* derivable everywhere: every `General_Category` value
(including `\p{L}`, `\p{Letter}`, `\p{General_Category=Nd}`) plus `ASCII`,
`ASCII_Hex_Digit`, `Any`, `Assigned`, `Bidi_Control`, `Bidi_Mirrored`,
`Hex_Digit`, `Join_Control`, `Lowercase`, `Noncharacter_Code_Point`,
`Regional_Indicator`, `Uppercase`, `White_Space`, `XID_Continue`,
`XID_Start`.

## Backends

| Backend | Notes |
| --- | --- |
| `re` (default) | Standard library, no dependencies. `\p{...}` becomes an explicit range class. |
| `regex` | Optional extra. Keeps `\p{...}` native, allows variable-width lookbehind, supports scripts. |

```python
ecma_regex.compile(r"\p{Script=Greek}+", backend="regex")
```

Neither backend is linear-time; both backtrack. Use `star_height` to screen
untrusted patterns.

### Cost

The first `\p{...}` translated on the `re` backend scans every code point
to build its range list — about 40 ms on CPython 3.12. The result is cached
process-wide, so later uses are dict hits, and every later
`General_Category` property reuses the same scan.

## License

MIT.
