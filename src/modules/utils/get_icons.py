# ---- Emoji / Icon options ----
# A small set of handy icons you can use in log messages.
# Common options (name: glyph — Unicode codepoint / description):
#   check         : ✅  (U+2705) - White Heavy Check Mark (green rounded box in many renderers)
#   ballot        : ☑️  (U+2611 + VS16) - Ballot Box With Check (checkbox)
#   red_box       : 🟥  (U+1F7E5) - Red Square
#   stop          : 🛑  (U+1F6D1) - Octagonal Sign (stop)
#   cross         : ❌  (U+274C) - Cross Mark
#   info          : ℹ️  (U+2139 + VS16) - Information Source
#   warning       : ⚠️  (U+26A0 + VS16) - Warning Sign
#
# Note: Emoji rendering depends on the terminal/OS. If an emoji is not supported,
# it may appear as a box or fallback glyph. You can always use plain ASCII like "[OK]".
ICONS = {
    "check": "✅",
    "ballot": "☑️",
    "red_box": "🟥",
    "stop": "🛑",
    "cross": "❌",
    "info": "ℹ️",
    "warning": "⚠️",
    "ok_ascii": "[OK]",
    "fail_ascii": "[FAIL]",
}


def get_icon(name: str, fallback: str = "") -> str:
    """Return a printable icon by name; fallback used if the key is unknown."""
    return ICONS.get(name, fallback)

