# Shared RFC 3986/3987 ABNF fragments (M7): plain string pieces composed
# by the URI family and reused by `uri-template`. Step 1 (agent B) fills
# this module; the names below are the contract the other modules import.
#
# Dependency direction: standard library only.

ALPHA = "[A-Za-z]"
DIGIT = "[0-9]"
HEXDIG = "[0-9A-Fa-f]"
