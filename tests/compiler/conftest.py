# M6 Step 4: Hypothesis profiles for the differential fuzzer
# (tests/compiler/test_fuzz.py). `ci` is the default, fast enough for every
# regular test run; `deep` is a long, non-derandomized run meant to be
# invoked explicitly (`HYPOTHESIS_PROFILE=deep uv run pytest ...`) — never
# part of the default gate.

import os

from hypothesis import settings

settings.register_profile(
    "ci",
    max_examples=300,
    deadline=None,
    derandomize=True,
    database=None,
    print_blob=True,
)
settings.register_profile(
    "deep",
    max_examples=20_000,
    deadline=None,
    derandomize=False,
    print_blob=True,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
