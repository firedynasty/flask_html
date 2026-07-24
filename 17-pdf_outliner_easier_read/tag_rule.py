"""Test harness for app.tag_sentence — the ordered TAG_RULES opener tagger.

Cases exercise the rule-ordering and guard fixes (qualification before
consequence, `so`/`while` guards). The rules live in app.py; this file is the
case set — extend it as new mis-tags are found. Run: python tag_rule.py
"""
from app import tag_sentence

CASES = [
    ("qualification", "So long as we write and talk about them we are much more likely to deter him."),
    ("contrast", "So far from killing the taste of the egg, it actually brings it out."),
    ("consequence", "So we must try to understand it."),
    ("consequence", "So it follows that we were wrong."),
    ("contrast", "Far from being a comfort, it is a warning."),
    ("qualification", "While it is true that we are fallen, we are not beasts."),
    ("contrast", "While the one is easy, the other is hard."),
    ("qualification", "As far as we can tell, it holds."),
    ("evidence", "For he had no choice."),
    ("evidence", "For most people, the question never arises."),  # known remaining FP
]

if __name__ == "__main__":
    bad = 0
    for expected, s in CASES:
        got = tag_sentence(s)
        flag = "ok " if got == expected else "FAIL"
        if got != expected:
            bad += 1
        print(f"{flag} want={expected:14} got={str(got):14} {s[:62]}")
    print(f"\n{len(CASES)-bad}/{len(CASES)} passed")
