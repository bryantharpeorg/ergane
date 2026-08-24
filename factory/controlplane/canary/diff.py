"""The judge canary's known-bad diff fixture.

A canary that generates its own test case cannot distinguish a wrong model from
a wrong fixture, so the diff, criteria and required schema are committed as data
(spec 103 FR-005, trap 3).
"""

from __future__ import annotations

import json
from typing import Any


#: A minimal, obviously incorrect change: a function that returns a constant
#: instead of doing its job.
KNOWN_BAD_DIFF = """\
--- a/factory/heart.py
+++ b/factory/heart.py
@@ -1,5 +1,5 @@
 def beat():
-    return "thump"
+    return False
"""


#: The criteria the judge would read off the spec.  Kept deliberately small so
#: the canary prompt fits comfortably under a modest context budget.
CANARY_CRITERIA = [
    "The change must keep beat() returning a string.",
    "The change must not introduce a boolean return value.",
]


#: Required JSON schema for the canary verdict.  The canary passes only when the
#: model returns a JSON object matching this schema with `verdict: "FAIL"` on
#: the known-bad diff.
VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


#: Compact, stringified schema for use in prompts to the LLM.
VERDICT_SCHEMA_TEXT = json.dumps(VERDICT_SCHEMA, indent=None, separators=(",", ":"))
