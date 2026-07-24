# Opus review: economy-mode tagger (paste-to-outline tool)

You reviewed the definition rule for this project's sibling tool once before
(subject-anchored `is_definition`). That worked well. Now I need the same kind
of rule review for a NEW second mode. This doc is self-contained.

## What the tool does

User pastes an article into a textarea and gets a **verbatim sentence
outline**: every sentence of the original appears, unchanged, as a bullet.
Sentences get tags from deterministic regex heuristics — **no LLM at
runtime**. The tool has two modes:

- **theology** — for dense expository prose (Aquinas, C. S. Lewis). Tags are
  *argument relations*: how a sentence relates to its paragraph's claim.
  REVIEWED ALREADY, shown below only for contrast.
- **economy** — for financial journalism (WSJ, Seeking Alpha). Tags are
  *sentence functions* (price move, causal claim, expectation, …) plus a
  structured panel that fills the user's WSJ reading template.
  **THIS IS WHAT I NEED REVIEWED.**

## Shared machinery (reused unchanged by both modes)

```python
def strip_opener(sent):
    # tag rules are checked against the sentence with leading
    # quotes/brackets stripped, case-insensitive
    return re.sub(r"^[\"“‘'(\[\]… ]+", "", sent)

def outline_chapter(paragraphs, tag_fn):
    # first sentence of each paragraph = claim (top-level bullet)
    # tag = tag_fn(sentence); tagged -> child of the claim
    # untagged -> corroborated attachment:
    #     previous ends with ':'        -> [example]
    #     subject-anchored 'means' test -> [definition]
    #     anaphoric opener or shared content words -> [restatement]
    # otherwise -> plain UNMARKED top-level bullet (provisional: no relation
    # asserted, nothing hidden). Corroboration happens at attach time.
```

Sentence splitting is a regex splitter with abbreviation protection
(`Mr.`, `e.g.`, initials, plus finance additions: `Inc. Corp. Ltd. U.S.`,
month names). Verification is a token-multiset comparison of outline vs.
source — must stay 100% coverage, 0 insertions, since everything is verbatim.

## NORMAL mode (theology) — existing code, for contrast

Key property: **opener-anchored**. Argument relations are signaled by
connective openers, so every pattern is `^`-anchored. Ordered, first match
wins:

```python
TAG_RULES = [
    ("concession", r"^(of course|no doubt|doubtless|admittedly|it is true|certainly|to be sure|"
                   r"i know|i admit|you may (say|think|ask|object|feel)|"
                   r"some (people|one|of you) (may |might |will )?(say|think|ask|object|feel)|"
                   r"it may be (said|thought|urged|objected)|we (may|might) be told|"
                   r"it is (often|sometimes) (said|thought))"),
    ("example", r"^(for example|for instance|take |think of |consider |suppose, for example)"),
    ("analogy", r"^(just as|it is as if|as if|imagine|suppose|like |similarly|in the same way)"),
    ("contrast", r"^((so )?far from|but|however|yet\b|nevertheless|none the less|nonetheless|still\b|"
                 r"on the other hand|on the contrary|whereas|while\b(?!\s+it\s+is\s+true)|"
                 r"conversely|in contrast|at the same time)"),
    ("evidence", r"^(because|for\b|since\b|after all|the reason|in fact|as a matter of fact|"
                 r"the fact (is|remains)|we know|it is a fact|that is (the reason|why we know))"),
    # qualification must precede consequence: consequence's `so` would
    # otherwise eat "so long as" / "so far as" before qualification sees them
    ("qualification", r"^(?:now\s+)?(if\b|unless|provided|although|though\b|even if|"
                      r"even though|when\b|whenever|as long as|so long as|as far as|so far as|"
                      r"while it is true|only\b)"),
    ("consequence", r"^(therefore|thus|hence|consequently|accordingly|"
                    r"so\b(?!\s+(?:long|far|much|many|great|be\b))|then\b|it follows|"
                    r"which means|that is why|the result is|and so|in that case)"),
    ("restatement", r"^(that is\b|in other words|i mean|or rather|namely|again\b|"
                    r"to put it (another way|differently)|put another way|"
                    r"(first|firstly|second|secondly|third|thirdly|fourth|fourthly|"
                    r"fifth|finally|lastly|next\b)[,.\)])"),
    ("definition", r"^(by .{1,40} i mean|what (do )?(we|i) mean|let me (define|explain)|"
                   r"i am using|we mean by|i mean by)"),
]

def tag_sentence(sent):
    s = strip_opener(sent)
    for tag, rx in TAG_RES:      # compiled TAG_RULES
        if rx.match(s):
            return tag
    return None
```

## ECONOMY mode — NEW code, please review

Two key differences from theology mode, both deliberate:

1. **Full-sentence matching.** Finance signals live mid-sentence ("Shares
   fell 3.2% **because** the Fed…"), so these patterns `.search()` the whole
   sentence, not `^`. This is noisier — see constraints.
2. **Two-condition tags.** `[price-move]` requires BOTH a move verb and a
   magnitude in the same sentence.

### The tagger

```python
# magnitude: 3.2% | 4 percent | 25 basis points | $4.50
_MAG_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%|percent|percentage\s+points?|basis\s+points?|\bbp\b)"
    r"|\$\s?\d[\d,.]*)", re.I)

_MOVE_RE = re.compile(
    r"\b(?:rose|fell|gained|lost|dropped|slid|jumped|surged|tumbled|plunged|"
    r"climbed|slipped|rallied|declined|advanced|retreated|soared|sank|spiked|"
    r"tanked|cratered|edged (?:higher|lower)|settled|"
    r"closed (?:higher|lower|up|down)|ended (?:higher|lower|up|down)|"
    r"hit a record)\b", re.I)

_SOURCE_RE = re.compile(r"\b(?:said|says|told|wrote|according to)\b", re.I)

_UNNAMED_RE = re.compile(
    r"\b(?:people familiar|some (?:analysts?|investors?|traders?)|"
    r"(?:analysts?|traders?|investors?|sources?) (?:said|say)|"
    r"according to (?:sources?|people))\b", re.I)

_NAME_PROPER_RE = re.compile(r"[A-Z][a-z]+\s+(?:[A-Z][a-z]+|[A-Z]\.)")   # "Jane Smith"
_NAME_INST_RE = re.compile(
    r"\b(?:company|firm|manufacturer|retailer|bank|federal reserve|treasury|"
    r"white house|commerce department|labor department)\b|\bFed\b")

_CAUSE_RE = re.compile(
    r"\b(?:because|due to|thanks to|as a result of|driven by|fueled by|"
    r"fuelled by|amid|after|on the back of|led to|caused|prompted|sparked|"
    r"triggered)\b"
    r"|\bsince\b(?!\s+(?:\d|the\s+(?:start|beginning|end)|last))", re.I)

_EXPECT_RE = re.compile(
    r"\b(?:expects?|expected|forecast\w*|projects?|projected|anticipates?|"
    r"predicts?|price target|target price|guidance|outlook|consensus|"
    r"estimates?)\b", re.I)

_DISCONFIRM_RE = re.compile(
    r"\b(?:unless|could change if|would reverse|fails to|threatens?|downside|"
    r"risk is|risks are|the risk that|biggest risk|caveat)\b", re.I)

_DATA_RE = re.compile(
    r"\b(?:filing|filed with|10-K|10-Q|SEC\b|balance sheet|cash flow|"
    r"free cash flow|revenue|earnings per share|\bEPS\b|same-store|"
    r"comparable sales|trading volume|volume|quarterly results|net income|"
    r"margin\w*)\b", re.I)

_INFER_RE = re.compile(
    r"\b(?:suggests?|signals?|seems?|appears?|points? to|indicates?|"
    r"looks? like|reads? as|smacks of|in our view|we believe)\b", re.I)

_OPINION_RE = re.compile(
    r"\b(?:overvalued|undervalued|attractive|compelling|cheap|expensive|"
    r"worrisome|alarming|impressive|disappointing|frothy|stretched)\b", re.I)

_MISS_RE = re.compile(
    r"\b(?:missed|fell short|underperformed?|disappointed|"
    r"below (?:expectations?|forecasts?|estimates?)|despite)\b", re.I)

_LINK_RE = re.compile(
    r"\b(?:led to|caused|prompted|sparked|triggered|pushing|driving|fueling|"
    r"fuelling|which in turn|as a result)\b", re.I)

# opener-anchored tail, kept from theology mode: still first-words-only
_ECON_TAIL_RES = [
    ("concession", re.compile(
        r"^(of course|no doubt|doubtless|admittedly|it is true|certainly|"
        r"to be sure)", re.I)),
    ("contrast", re.compile(
        r"^(but|however|yet\b|nevertheless|nonetheless|still\b|"
        r"on the other hand|whereas|while\b(?!\s+it\s+is\s+true))", re.I)),
]


def econ_tag_sentence(sent):
    """Finance-function tag for one sentence, or None.
    Order matters: a sentence can match several patterns; the first wins."""
    s = strip_opener(sent)
    if _MOVE_RE.search(s) and _MAG_RE.search(s):
        return "price-move"                 # needs BOTH verb and magnitude
    if _SOURCE_RE.search(s):
        if _UNNAMED_RE.search(s):
            return "source-unnamed"
        if _NAME_PROPER_RE.search(s) or _NAME_INST_RE.search(s):
            return "source-named"
        return "source-unnamed"
    if _CAUSE_RE.search(s):
        return "cause"
    if _EXPECT_RE.search(s):
        return "expectation"
    if _DISCONFIRM_RE.search(s):
        return "disconfirmer"
    if _DATA_RE.search(s):
        return "data"
    if _INFER_RE.search(s) or _OPINION_RE.search(s):
        return "inference"
    for tag, rx in _ECON_TAIL_RES:
        if rx.match(s):
            return tag
    return None
```

### The structured panel (fills the user's WSJ reading template)

Separate from the tree: scans the flat sentence list with the same regexes.
Every entry is a verbatim sentence; empty sections are flagged
("not stated" / "none offered"), never filled. Sections: Type, What moved,
Causal claims (each sub-tagged + backing), Chains, Forward-looking,
Disconfirmers, Inference dressed as fact, Expectation vs. outcome.

```python
def econ_structure(sents):
    n_attr = sum(1 for s in sents if _SOURCE_RE.search(s))
    n_op = sum(1 for s in sents if _INFER_RE.search(s) or _OPINION_RE.search(s))
    if n_attr and n_op:
        ptype = "mixed"
    elif n_attr:
        ptype = "reported news"
    else:
        ptype = "analysis-opinion"

    moved = [s for s in sents if _MOVE_RE.search(s) and _MAG_RE.search(s)]

    claims = []
    for i, s in enumerate(sents):
        if not _CAUSE_RE.search(s):
            continue
        if _UNNAMED_RE.search(s):
            attr = "unnamed source"
        elif _SOURCE_RE.search(s) and (_NAME_PROPER_RE.search(s)
                                       or _NAME_INST_RE.search(s)):
            attr = "named source"
        elif _INFER_RE.search(s):
            attr = "author inference"
        else:
            attr = "reported fact (asserted flatly)"
        # backing: check the claim sentence AND the following one
        ctx = s + " " + (sents[i + 1] if i + 1 < len(sents) else "")
        if _DATA_RE.search(ctx):
            backing = "hard data"
        elif _SOURCE_RE.search(ctx):
            backing = "third-party opinion"
        else:
            backing = "none"
        claims.append({"text": s, "attr": attr, "backing": backing})

    chains = []
    for s in sents:
        if len(_LINK_RE.findall(s)) >= 2:          # need X -> Y -> Z
            parts = [p.strip(" ,.;:") for p in _LINK_RE.split(s)]
            parts = [p for p in parts if p]
            if len(parts) >= 3:
                chains.append(" → ".join(parts))

    forward = [s for s in sents if _EXPECT_RE.search(s)]
    disconfirmers = [s for s in sents if _DISCONFIRM_RE.search(s)]
    inf_fact = [s for s in sents
                if (_INFER_RE.search(s) or _OPINION_RE.search(s))
                and not _SOURCE_RE.search(s)]
    miss = [s for s in sents if _MISS_RE.search(s)]
    exp_vs_out = {"applicable": bool(miss), "outcome": miss, "expected": forward}
    return {"ptype": ptype, "n_attr": n_attr, "n_opinion": n_op,
            "moved": moved, "claims": claims, "chains": chains,
            "forward": forward, "disconfirmers": disconfirmers,
            "inf_fact": inf_fact, "exp_vs_out": exp_vs_out}
```

## Worked example (I wrote this fake WSJ-style piece; output traced by hand)

```
S1  Stocks fell on Tuesday as investors weighed fresh inflation data.
S2  The Dow Jones Industrial Average dropped 1.2%, while the S&P 500 slid 0.8%.
S3  The decline came after the Labor Department reported that consumer
    prices rose 3.4% in April from a year earlier.
S4  "The Fed has less room to cut rates this year," said Jane Smith, chief
    economist at Northern Trust.
S5  Some analysts said the selloff was overdone.
S6  The report suggests that price pressures remain sticky.
S7  Nvidia shares rose 2.5% after the company forecast quarterly revenue
    above estimates.
S8  The chip maker expects sales to reach $28 billion in the current quarter.
S9  The rally could reverse if inflation fails to cool.
S10 Despite the broader decline, Treasury yields climbed.
S11 Higher yields led to heavier borrowing costs, which in turn caused
    companies to pull back.
```

Tree tags + panel sections as the rules above produce them:

| # | tree tag | panel appearances | correct? |
|---|---|---|---|
| S1 | *(none — provisional)* | nowhere | **FN**: "as investors weighed…" is a causal claim; bare "as" not in `_CAUSE_RE` |
| S2 | price-move | What moved ✓ | ✓ |
| S3 | price-move (rose + 3.4%) | What moved; Causal claims ("after" → attr: *reported fact*, backing: *third-party opinion* — "reported" not in `_SOURCE_RE`, CPI data not in `_DATA_RE`) | tag OK (CPI is "a metric that moved"), but attr/backing are **wrong**: "the Labor Department reported" is a named source with hard data |
| S4 | source-named ✓ ("Jane Smith") | — | ✓ (note: the quote is also a forward-looking claim — "less room to cut rates this year" — but `_EXPECT_RE` misses it) |
| S5 | source-unnamed ✓ | — | ✓ |
| S6 | inference ✓ | Inference dressed as fact ✓ | ✓ |
| S7 | price-move (first match wins over cause/expectation) | What moved; Causal claims ("after"); Forward-looking ("forecast", "estimates") | ✓ — one sentence legitimately in three sections |
| S8 | expectation ✓ | Forward-looking ✓ (has $28B + timeframe) | ✓ |
| S9 | disconfirmer ✓ ("fails to") | Disconfirmers ✓ | ✓ |
| S10 | *(none)* | Expectation vs. outcome (via "despite") | OK — "yields climbed" has no magnitude, correctly not price-move |
| S11 | cause ("led to") | Causal claims; Chains: "Higher yields → heavier borrowing costs → companies to pull back" | ✓, but the chain is crude fragments |

Type: n_attr=2 (S4, S5), n_opinion=1 (S6) → **mixed** ✓.

## Constraints (same as last time)

- Deterministic and offline. No LLM call at runtime — you are an offline
  rule-design consultant; I apply your rewrite to the code.
- **False negatives are acceptable; false positives are the enemy.** A
  missed tag leaves a plain bullet (honest); a wrong tag lies.
- First-match-wins ordering; order is a design decision, not an accident.
- Verbatim only: no outside knowledge, no verdict on whether claims are
  sound. Gaps are flagged ("not stated" / "none offered"), never filled.
- The user's goal is easier READING of articles, not perfect NLP. A rough
  hint that survives scanning beats a precise rule that fires wrongly.

## Questions for you

1. **Ordering**: `price-move` before `cause` means S3/S7 land in What moved
   (their causal content still reaches the Causal claims section, which scans
   independently). Is there a sentence shape where this ordering actually
   hurts?
2. **Bare "as" as causal** (S1 FN): worth including with a guard, or too
   noisy? What guard?
3. **Source verbs**: "reported / announced / disclosed / said in a filing"
   (S3) — add to `_SOURCE_RE`? Any that backfire?
4. **Default attribution** for an unattributed causal claim is currently
   "reported fact (asserted flatly)". Should the honest default instead be
   "author inference"? Which default misleads the reader less?
5. **Backing window** = claim sentence + the NEXT sentence. Should it also
   look BACK one sentence ("…, filings show." preceding the claim)?
6. **`_DATA_RE` gaps**: CPI +3.4% is hard data but no marker word fires.
   What markers am I missing without opening the floodgates ("prices"?
   "rose/fell + %" = already a price-move)?
7. **Move forms**: "shares are up 2%" / "X is down 4% this quarter" —
   "is/are up/down" isn't in `_MOVE_RE`. Add with the magnitude condition
   (already required) or is that too loose?
8. **Expectation without the verb "expect"**: S4's quoted forward claim
   ("has less room to cut rates this year"). Any pattern worth adding
   (e.g. "room to", "on track to", "set to") or accept the FN?
9. **Chains**: the split-on-connectives arrow rendering is crude. Keep,
   improve, or drop the section?
10. Anything in the regexes that will visibly misfire on ordinary WSJ /
    Seeking Alpha prose that I haven't anticipated?

Please return concrete rule rewrites (patterns + ordering + rationale), not
general prose — I'll paste them into the code and add the cases above as a
test harness.
