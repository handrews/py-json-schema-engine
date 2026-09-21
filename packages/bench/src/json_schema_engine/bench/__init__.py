"""Internal benchmark harness for json-schema-engine (M6 Step 5).

Not published for external use. Measures the compiler tier's flag and
standalone artifacts against the interpreter and two competitors
(fastjsonschema, jsonschema) over a small set of named corpora — see
`corpora.py`, `subjects.py`, `harness.py`, and `report.py`. Report-only:
nothing here gates CI.
"""

from json_schema_engine.bench.corpora import CORPUS_NAMES, Corpus, load_corpus
from json_schema_engine.bench.harness import Exclusion, Results, TaskResult, run
from json_schema_engine.bench.report import format_table
from json_schema_engine.bench.subjects import SUBJECTS, Subject

__all__ = [
    "CORPUS_NAMES",
    "SUBJECTS",
    "Corpus",
    "Exclusion",
    "Results",
    "Subject",
    "TaskResult",
    "format_table",
    "load_corpus",
    "run",
]
