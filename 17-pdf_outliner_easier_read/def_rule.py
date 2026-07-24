"""Test harness for app.is_definition — the definition-sense test for `means`.

Cases from OPUS_HEURISTIC_REVIEW.md (real mis-tags from the book) plus
adversarial ones. The implementation lives in app.py; this file is the case
set — extend it as new mis-tags are found. Run: python def_rule.py
"""
from app import is_definition

CASES = [
    # (expected, sentence)
    (True,  "'Charity' now means simply what used to be called 'alms'—that is, giving to the poor."),
    (True,  "Charity' now means simply what used to be called 'alms'—that is, giving to the poor."),
    (True,  "Dualism means the belief that there are two equal and independent powers at the back of everything."),
    (True,  "It now usually means teetotalism."),
    (True,  "Pride means the loss of everything else."),
    (True,  "The word 'gentleman' originally meant a man with a coat of arms."),
    (False, "He has his own, different, means of bringing out the key words and ought to use them."),
    (False, "I am afraid it means they are worshipping an imaginary God."),
    (False, "He means both."),
    (False, "That means creatures which can go either wrong or right."),
    (False, "This means we must try harder."),
    (False, "She means well."),
    (False, "It means that we are lost."),          # deliberate false negative
    (False, "There is no other means of doing it."),
    (False, "Christ means to save us."),
]

if __name__ == "__main__":
    bad = 0
    for expected, s in CASES:
        got = is_definition(s)
        flag = "ok " if got == expected else "FAIL"
        if got != expected:
            bad += 1
        print(f"{flag} expected={str(expected):5} got={str(got):5} {s[:70]}")
    print(f"\n{len(CASES)-bad}/{len(CASES)} passed")
