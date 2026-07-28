"""
Paste-to-Outline — paste an article or chapter, get a verbatim outline.

Four modes:
  theology      — relation-tagged outline ported from 17-pdf_outliner
                  (concession / evidence / qualification / ... tags)
  general       — nonfiction / opinion prose at any length: op-eds, essays,
                  books (Gutenberg, Kindle paste). The same relation tagger;
                  strips Gutenberg markers, handles no-blank-line Kindle
                  pastes, auto-splits chapter headings in long texts
  economy       — WSJ-style reported-news read: what moved, causal claims +
                  backing, chains, forward-looking, disconfirmers, inference
                  dressed as fact, expectation vs. outcome
  seeking-alpha — opinion/analysis pieces: author position, modal
                  speculation, letter-grade valuation; opinion-density
                  weighting on the piece type

Everything is deterministic heuristics — no LLM calls. The economy/SA rules
went through two Opus review rounds (OPUS_ECON_REVIEW.md): temporal-since
killed, tense-flexible inference, pronoun-guarded reporting verbs, modal
speculation tag. Gaps are flagged ("not stated" / "none offered"), never
filled.

Usage:
    python app.py
    open http://localhost:5004
"""

import collections
import re

from flask import Flask, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# sentence machinery (ported from 17-pdf_outliner_easier_read/app.py)
# ---------------------------------------------------------------------------

SENT_SPLIT_RE = re.compile(r"[.?!]+[\"”’)\]]*\s+")
ABBR_MARK = "\x01"


def protect_abbrevs(text):
    t = re.sub(r"\b(Mr|Mrs|Dr|St|etc|vs|No|Jr|Sr|Messrs|Inc|Corp|Ltd|Co|Bros|Sen|Rep|Gov|Gen|Rev|Hon|Prof|Ave|Dept|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.",
               lambda m: m.group(1) + ABBR_MARK, text)
    t = re.sub(r"\b([ie])\. ?([ge])\.",
               lambda m: m.group(1) + ABBR_MARK + m.group(2) + ABBR_MARK, t)
    t = re.sub(r"\b([A-Z])\.", lambda m: m.group(1) + ABBR_MARK, text)
    return t


def split_sentences(para):
    t = protect_abbrevs(para)
    out, pos = [], 0
    for m in SENT_SPLIT_RE.finditer(t):
        # keep the terminal punctuation (17's splitter dropped it — invisible
        # to the token verifier, but a verbatim outline should keep it)
        seg = t[pos:m.end()].strip()
        nxt = t[m.end():m.end() + 1]
        # only split where the next sentence begins with capital/quote/digit
        if seg and (not nxt or nxt.isupper() or nxt in "\"“‘'(0123456789"):
            out.append(seg)
            pos = m.end()
    last = t[pos:].strip()
    if last:
        out.append(last)
    return [s.replace(ABBR_MARK, ".") for s in (x.strip() for x in out) if s]


STOPWORDS = {"their", "there", "which", "would", "could", "should", "about",
             "these", "those", "thing", "things", "people", "every", "being",
             "because", "before", "after", "other", "another", "between",
             "that", "this", "with", "from", "have", "been", "were", "what",
             "when", "where", "they", "them", "then", "than", "some", "into"}


def content_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", text.lower())} - STOPWORDS


# Anaphoric openers corroborate attachment to the previous sentence.
ANAPHORA_RE = re.compile(
    r"^(?:sometimes|often|usually|always|now|here|there|also|still|even|yes|no)?\s*"
    r"(this|that|these|those|it|its|he|she|they|and|indeed|nor|neither|either|"
    r"the same|such|so much|at any rate|in fact|anyway|none of us|we all|"
    r"all of us|you and i)\b", re.I)


def strip_opener(sent):
    return re.sub(r"^[\"“‘'(\[\]… ]+", "", sent)


# Subject-anchored `means` definition test (Opus round 1, ported verbatim).
_QL = "\"'‘“"
_QR = "\"'’”"

_HEDGE = (
    r"(?:\s+(?:now|then|here|also|again|really|simply|just|merely|usually|"
    r"normally|generally|originally|properly|strictly|literally|roughly|"
    r"nowadays|today|[a-z]+ly)){0,3}"
)

_DEF_MEANS_RE = re.compile(
    r"^\s*(?P<subj>"
    r"[" + _QL + r"][^" + _QR + r"]{1,40}[" + _QR + r"]"
    r"|the\s+(?:word|term|name|phrase|expression)\s+"
    r"[" + _QL + r"]?[\w-]{1,30}[" + _QR + r"]?"
    r"|[A-Za-z][\w-]{1,30}[" + _QR + r"]"
    r"|[A-Za-z][A-Za-z-]{1,30}"
    r")"
    + _HEDGE +
    r"\s+mean(?:s|t)\b\s*(?P<obj>.*)$",
    re.I,
)

_BAD_SUBJ = {
    "i", "he", "she", "we", "they", "you", "who", "one", "someone", "somebody",
    "anyone", "everyone", "everybody", "nobody", "that", "this", "these",
    "those", "there", "what", "which", "god", "christ", "jesus", "man",
    "people", "no",
}

_BAD_OBJ_RE = re.compile(
    r"^(?:that\b|to\b|of\b|as\b|for\b|in\b|with\b|by\b|from\b"
    r"|(?:i|he|she|we|they|you|it|there|one)\b"
    r"|(?:both|well|business|mischief|harm|so|otherwise|"
    r"nothing|everything|anything)\b)",
    re.I,
)


def is_definition(sentence):
    m = _DEF_MEANS_RE.match(sentence.strip())
    if not m:
        return False
    subj = m.group("subj").strip()
    core = subj.strip(_QL + _QR).lower()
    mentioned = subj[0] in _QL or subj[-1] in _QR or " " in core
    if not mentioned and core in _BAD_SUBJ:
        return False
    if _BAD_OBJ_RE.match(m.group("obj").lstrip(" ,;:—-")):
        return False
    return True


class Node:
    __slots__ = ("text", "tag", "children", "provisional")

    def __init__(self, text, tag=None, provisional=False):
        self.text = text
        self.tag = tag
        self.children = []
        self.provisional = provisional


def node_depth(node, depth=1):
    if not node.children:
        return depth
    return max(node_depth(c, depth + 1) for c in node.children)


# ---------------------------------------------------------------------------
# theology mode — opener-anchored argument-relation tagger (reviewed)
# ---------------------------------------------------------------------------

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
TAG_RES = [(tag, re.compile(rx, re.I)) for tag, rx in TAG_RULES]


def tag_sentence(sent):
    s = strip_opener(sent)
    for tag, rx in TAG_RES:
        if rx.match(s):
            return tag
    return None


# ---------------------------------------------------------------------------
# economy / seeking-alpha mode — sentence-function tagger (Opus v3)
# ---------------------------------------------------------------------------
# Unlike theology, these patterns .search() the WHOLE sentence: finance
# signals live mid-sentence. Order matters; first hit wins. [price-move]
# needs BOTH a move verb and a magnitude.

_MAG_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%|percent|percentage\s+points?|basis\s+points?|\bbp\b)"
    r"|\$\s?\d[\d,.]*)", re.I)

_MOVE_RE = re.compile(
    r"\b(?:rose|fell|gained|lost|dropped|slid|jumped|surged|tumbled|plunged|"
    r"climbed|slipped|rallied|declined|advanced|retreated|soared|sank|spiked|"
    r"tanked|cratered|edged (?:higher|lower)|settled|"
    r"closed (?:higher|lower|up|down)|ended (?:higher|lower|up|down)|"
    r"hit a record|(?:is|are|was|were)\s+(?:up|down)|"
    r"shot (?:up|higher|past)|pushed (?:up|higher|above|past|below)|topped|"
    r"sent\s+\w+\s+(?:up|down|higher|lower))\b", re.I)

# source verbs stay at the original five (Opus v3: "reported/announced"
# backfired on "It reported net debt" / "the U.S. announced tariffs")
_SOURCE_RE = re.compile(r"\b(?:said|says|told|wrote|according to)\b", re.I)

_UNNAMED_RE = re.compile(
    r"\b(?:people familiar|some (?:analysts?|investors?|traders?)|"
    r"(?:analysts?|traders?|investors?|sources?) (?:said|say)|"
    r"according to (?:sources?|people))\b", re.I)

_NAME_PROPER_RE = re.compile(r"[A-Z][a-z]+\s+(?:[A-Z][a-z]+|[A-Z]\.)")
_NAME_INST_RE = re.compile(
    r"\b(?:company|firm|manufacturer|retailer|bank|federal reserve|treasury|"
    r"white house|commerce department|labor department)\b|\bFed\b")

# reporting verbs count as a source ONLY with a proper, non-pronoun subject
# ("BLS reported" named; "It reported" is data; single-name "according to AAA")
_NAME_REPORT_RE = re.compile(
    r"according to\s+[A-Z][A-Za-z.&]+"
    r"|(?<![A-Za-z])(?!(?:It|He|She|They|This|That|These|Those|We|I|You)\b)"
    r"[A-Z][A-Za-z.&]+\s+(?:said|says|reported|disclosed)\b")

# lowercase institution subject + reporting verb ("the company reported…")
_INST_REPORT_RE = re.compile(
    r"\b(?:company|firm|manufacturer|retailer|bank|federal reserve|treasury|"
    r"white house|commerce department|labor department|fed)\s+"
    r"(?:said|says|reported|disclosed)\b", re.I)

# temporal `since` deleted entirely (Opus: 3 FPs on one WSJ article);
# +catalyst for (SA S32)
_CAUSE_RE = re.compile(
    r"\b(?:because|due to|thanks to|as a result of|driven by|fueled by|"
    r"fuelled by|amid|after|on the back of|led to|caused|prompted|sparked|"
    r"triggered|catalyst for)\b", re.I)

_EXPECT_RE = re.compile(
    r"\b(?:expects?|expected|forecast\w*|projects?|projected|anticipates?|"
    r"predicts?|price target|target price|guidance|outlook|consensus|"
    r"estimates?|set to|on track to|room to|poised to)\b", re.I)

# threatens?/bare downside dropped (thesis words, not disconfirmers)
_DISCONFIRM_RE = re.compile(
    r"\b(?:unless|could change if|would reverse|fails to|downside risk|"
    r"risk is|risks are|the risk that|biggest risk|caveat)\b", re.I)

_DATA_RE = re.compile(
    r"\b(?:filing|filed with|10-K|10-Q|SEC\b|balance sheet|cash flow|"
    r"free cash flow|revenue|earnings per share|\bEPS\b|same-store|"
    r"comparable sales|trading volume|volume|quarterly results|net income|"
    r"margin\w*|consumer prices|inflation|payrolls|jobless claims|"
    r"retail sales|GDP|CPI|PPI)\b", re.I)

# tense-flexible (v3: "indicated/suggested" missed) + guarded shows
_INFER_RE = re.compile(
    r"\b(?:suggest(?:s|ed)?|signal(?:s|ed)?|seem(?:s|ed)?|appear(?:s|ed)?|"
    r"point(?:s|ed)? to|indicat(?:es?|ed)|look(?:s|ed)? like|reads? as|"
    r"smacks of|in our view|we believe|"
    r"(?:data|moves?|figures?|numbers?|results?)\s+shows?)\b", re.I)

_OPINION_RE = re.compile(
    r"\b(?:overvalued|undervalued|attractive|compelling|cheap|expensive|"
    r"worrisome|alarming|impressive|disappointing|frothy|stretched)\b", re.I)

# SA house style: letter grades. Case-sensitive-ish: A-DF must stay uppercase
# ("grade of a stock" must not match), but allow capitalized sentence starts.
_GRADE_RE = re.compile(
    r"[Ss]core[sd]?\s+(?:poorly|well|an?\s+[\"']?[A-DF][-+]?\b)"
    r"|[Gg]rades? of\s+[\"']?[A-DF]")

# modal speculation — SA's genre signal (7 hits vs 0 on WSJ reported news).
# `may` is lowercase-only: capital "May" is the month ("since May" FP).
_SPECULATION_RE = re.compile(r"\b(?:might|would|could)\b", re.I)
_SPEC_MAY_RE = re.compile(r"\bmay\b")

_MISS_RE = re.compile(
    r"\b(?:missed|fell short|underperformed?|disappointed|"
    r"below (?:expectations?|forecasts?|estimates?)|despite)\b", re.I)

_LINK_RE = re.compile(
    r"\b(?:led to|caused|prompted|sparked|triggered|pushing|driving|fueling|"
    r"fuelling|which in turn|as a result|stoking|sending|sent\s+\w+\s+to|"
    r"reverberated)\b", re.I)

# SA author position / rating / disclosure
_POSITION_RE = re.compile(
    r"\b(?:i|we)\s+(?:rate|are rating|am rating|initiate[sd]?|"
    r"upgrade[sd]?|downgrade[sd]?)\b"
    r"|\b(?:i|we)\s+(?:am|are)\s+(?:long|short|neutral|bullish|bearish)\b"
    r"|\b(?:a )?(?:strong buy|strong sell|buy|sell|hold) rating\b"
    r"|\bmy (?:price )?target (?:is|of)\b"
    r"|\b(?:i|we) (?:have|hold|own|initiated) (?:a )?(?:long |short )?position"
    r"|\bno position\b", re.I)

_ECON_TAIL_RES = [
    ("concession", re.compile(
        r"^(of course|no doubt|doubtless|admittedly|it is true|certainly|"
        r"to be sure)", re.I)),
    ("contrast", re.compile(
        r"^(but|however|yet\b|nevertheless|nonetheless|still\b|"
        r"on the other hand|whereas|while\b(?!\s+it\s+is\s+true))", re.I)),
]


def _has_source(s):
    return bool(_SOURCE_RE.search(s) or _NAME_REPORT_RE.search(s)
                or _INST_REPORT_RE.search(s))


def _is_named_source(s):
    return bool(_NAME_PROPER_RE.search(s) or _NAME_INST_RE.search(s)
                or _NAME_REPORT_RE.search(s) or _INST_REPORT_RE.search(s))


def _is_opinion(s):
    return bool(_INFER_RE.search(s) or _OPINION_RE.search(s)
                or _GRADE_RE.search(s) or _SPECULATION_RE.search(s)
                or _SPEC_MAY_RE.search(s))


def econ_tag_sentence(sent):
    """Finance-function tag for one sentence, or None. First hit wins."""
    s = strip_opener(sent)
    if _MOVE_RE.search(s) and _MAG_RE.search(s):
        return "price-move"
    if _has_source(s):
        if _UNNAMED_RE.search(s):
            return "source-unnamed"
        return "source-named" if _is_named_source(s) else "source-unnamed"
    if _CAUSE_RE.search(s):
        return "cause"
    if _EXPECT_RE.search(s):
        return "expectation"
    if _DISCONFIRM_RE.search(s):
        return "disconfirmer"
    if _DATA_RE.search(s):
        return "data"
    if _INFER_RE.search(s) or _OPINION_RE.search(s) or _GRADE_RE.search(s):
        return "inference"
    for tag, rx in _ECON_TAIL_RES:
        if rx.match(s):
            return tag
    if _SPECULATION_RE.search(s) or _SPEC_MAY_RE.search(s):
        return "speculation"
    return None


def econ_structure(sents, mode="economy"):
    """Fill the WSJ/SA reading template from a flat sentence list. Every
    entry is a verbatim sentence; empty sections are flagged, never filled."""
    n_attr = sum(1 for s in sents if _has_source(s))
    n_op = sum(1 for s in sents if _is_opinion(s))
    if n_attr and n_op:
        ptype = "mixed"
    elif n_attr:
        ptype = "reported news"
    else:
        ptype = "analysis-opinion"
    if mode == "seeking-alpha" and n_op > 2 * n_attr:
        ptype = "analysis-opinion"  # opinion-dominant piece: say so

    moved = [s for s in sents if _MOVE_RE.search(s) and _MAG_RE.search(s)]

    claims = []
    for i, s in enumerate(sents):
        if not _CAUSE_RE.search(s):
            continue
        if _UNNAMED_RE.search(s):
            attr = "unnamed source"
        elif _has_source(s) and _is_named_source(s):
            attr = "named source"
        elif _INFER_RE.search(s):
            attr = "author inference"
        else:
            # honest default (Opus v3 correction): only straight reporting
            # earns "reported fact"; mixed/opinion pieces get author inference
            attr = ("reported fact (asserted flatly)" if ptype == "reported news"
                    else "author inference")
        ctx = " ".join(x for x in (sents[i - 1] if i else "", s,
                                   sents[i + 1] if i + 1 < len(sents) else "")
                       if x)
        if _DATA_RE.search(ctx):
            backing = "hard data"
        elif _has_source(ctx):
            backing = "third-party opinion"
        else:
            backing = "none"
        claims.append({"text": s, "attr": attr, "backing": backing})

    chains = []
    for s in sents:
        if len(_LINK_RE.findall(s)) >= 2:  # single sentence only (Opus Q9)
            parts = [p.strip(" ,.;:") for p in _LINK_RE.split(s)]
            parts = [p for p in parts if p]
            if len(parts) >= 3:
                chains.append(" → ".join(parts))

    forward = [s for s in sents if _EXPECT_RE.search(s)]
    disconfirmers = [s for s in sents if _DISCONFIRM_RE.search(s)]
    inf_fact = [s for s in sents
                if (_INFER_RE.search(s) or _OPINION_RE.search(s)
                    or _GRADE_RE.search(s)) and not _has_source(s)]
    position = [s for s in sents if _POSITION_RE.search(s)]
    miss = [s for s in sents if _MISS_RE.search(s)]
    n_spec = sum(1 for s in sents
                 if _SPECULATION_RE.search(s) or _SPEC_MAY_RE.search(s))
    return {"ptype": ptype, "n_attr": n_attr, "n_opinion": n_op,
            "n_speculation": n_spec, "moved": moved, "claims": claims,
            "chains": chains, "forward": forward, "disconfirmers": disconfirmers,
            "inf_fact": inf_fact, "position": position,
            "exp_vs_out": {"applicable": bool(miss), "outcome": miss}}


# ---------------------------------------------------------------------------
# outliner (shared; tagger plugged in per mode)
# ---------------------------------------------------------------------------

def outline_chapter(paragraphs, tag_fn):
    """Build the bullet tree. Untagged sentences attach only when
    corroborated (colon / means-definition / anaphora / shared content
    words); otherwise they stay in the flow as plain unmarked top-level
    bullets (provisional — nothing hidden). Means-definitions go at the
    END of the claim's children."""
    roots = []
    for para in paragraphs:
        sents = split_sentences(para)
        if not sents:
            continue
        claim = Node(sents[0])
        roots.append(claim)
        prev, prev_depth = claim, 1
        deferred_defs = []
        quote_heavy = sum(1 for s in sents if s[:1] in "\"“") >= max(2, len(sents) // 2)
        for s in sents[1:]:
            stripped = strip_opener(s)
            tag = tag_fn(s)
            if quote_heavy and tag is None:
                tag = "example"
            if tag:
                node = Node(s, tag)
                claim.children.append(node)
                prev, prev_depth = node, 2
                continue
            ow = content_words(s)
            if prev.text.rstrip()[-1:] == ":":
                node = Node(s, "example")
                parent = prev if prev_depth < 4 else claim
                parent.children.append(node)
                prev, prev_depth = node, min(prev_depth + 1, 4)
            elif is_definition(stripped):
                node = Node(s, "definition")
                deferred_defs.append(node)
                prev, prev_depth = node, 2
            elif ANAPHORA_RE.match(stripped) or \
                    (ow & content_words(prev.text)) or \
                    (ow & content_words(claim.text)):
                node = Node(s, "restatement")
                parent = prev if prev is not claim and prev_depth < 4 else claim
                parent.children.append(node)
                prev, prev_depth = node, min((prev_depth if parent is prev else 1) + 1, 4)
            else:
                roots.append(Node(s, provisional=True))
                prev, prev_depth = claim, 1
        claim.children.extend(deferred_defs)
    return roots


# ---------------------------------------------------------------------------
# markdown render + verify (token-multiset coverage; combined tag set)
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
TAG_STRIP_RE = re.compile(
    r"\[(?:evidence|definition|qualification|example|analogy|concession|"
    r"consequence|contrast|restatement|price-move|cause|source-named|"
    r"source-unnamed|expectation|disconfirmer|data|inference|speculation)\]")


def render_markdown(title, roots):
    lines = [f"# {title}", ""]
    def emit(node, depth):
        prefix = "  " * depth + "- "
        tag = f" [{node.tag}]" if node.tag else ""
        lines.append(prefix + node.text + tag)
        for c in node.children:
            emit(c, depth + 1)
    for r in roots:
        emit(r, 0)
    lines.append("")
    return "\n".join(lines)


def tokens(text):
    return collections.Counter(TOKEN_RE.findall(text.lower().replace("’", "'")))


def verify_chapter(md_text, source_text):
    body = []
    for line in md_text.splitlines():
        if line.startswith("#"):
            continue
        line = line.strip()
        if line.startswith("- "):
            line = line[2:]
        line = TAG_STRIP_RE.sub("", line)
        body.append(line)
    out_toks = tokens(" ".join(body))
    src_toks = tokens(source_text)
    dropped = src_toks - out_toks
    inserted = out_toks - src_toks
    total = sum(src_toks.values()) or 1
    coverage = 1.0 - sum(dropped.values()) / total
    return coverage, inserted, dropped


def chapter_stats(roots):
    n_nodes, n_provisional, tags = 0, 0, collections.Counter()
    def walk(n, depth):
        nonlocal n_nodes, n_provisional
        n_nodes += 1
        if n.provisional:
            n_provisional += 1
        if n.tag:
            tags[n.tag] += 1
        for c in n.children:
            walk(c, depth + 1)
    maxd = 0
    for r in roots:
        walk(r, 1)
        maxd = max(maxd, node_depth(r))
    return n_nodes, maxd, dict(tags), n_provisional


# ---------------------------------------------------------------------------
# input prep: plain paste, or hard-line-break cleanup (PDF / Gutenberg)
# ---------------------------------------------------------------------------

def load_wordlist(path="/usr/share/dict/words"):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return {w.strip().lower() for w in f if w.strip()}
    except OSError:
        return set()


def should_join(w1, w2, words):
    hyph = f"{w1}-{w2}".lower()
    joined = f"{w1}{w2}".lower()
    if hyph in words:
        return False
    if joined in words:
        return True
    if w1.lower() in words and w2.lower() in words:
        return False
    return True


def stitch_paragraphs(lines, words):
    """Join hard-wrapped lines: de-hyphenate at line ends; a new paragraph
    starts at a blank-line boundary only when the previous text closed a
    sentence."""
    paras, cur = [], ""
    for line, is_block_start in lines:
        if not cur:
            cur = line
            continue
        m = re.search(r"(\w+)-$", cur)
        first = re.match(r"(\w+)", line)
        if m and first:
            if should_join(m.group(1), first.group(1), words):
                cur = cur[: m.start(1)] + m.group(1) + line
            else:
                cur = cur + line
            continue
        if is_block_start and re.search(r"[.?!][\"”’)\]]?\s*$", cur):
            paras.append(cur)
            cur = line
        else:
            cur = cur + " " + line
    if cur:
        paras.append(cur)
    return paras


GUT_START_RE = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*", re.I)
GUT_END_RE = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*", re.I)

# Match a line that contains only a timestamp — used by strip_transcript_timestamps
_TS_LINE_RE = re.compile(r"^[ \t]*\[(?:\d{1,2}:)?\d{1,2}:\d{2}\][ \t]*$", re.M)
# Match any remaining inline timestamp (after line-only ones are gone)
_TS_INLINE_RE = re.compile(r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}\]")


def strip_transcript_timestamps(text):
    """Strip [MM:SS] / [HH:MM:SS] YouTube-style timestamps.

    Removes the *content* of timestamp-only lines while keeping their
    surrounding newlines, so existing blank-line paragraph boundaries are
    preserved and the Kindle/Medium line-per-paragraph mode is not
    incorrectly triggered.  Inline timestamps are also stripped.
    The resulting triple-newlines (blank + now-empty timestamp line) are
    collapsed back to a double-newline.
    """
    text = _TS_LINE_RE.sub("", text)           # blank out timestamp lines
    text = _TS_INLINE_RE.sub("", text)         # remove any inline timestamps
    text = re.sub(r"[ \t]{2,}", " ", text)     # tidy double spaces
    text = re.sub(r"\n{3,}", "\n\n", text)     # collapse triple+ newlines
    return text


def strip_gutenberg(text):
    """Drop everything outside the *** START/END OF PROJECT GUTENBERG ***
    markers when a whole ebook text is pasted."""
    m = GUT_START_RE.search(text)
    if m:
        text = text[m.end():]
    m = GUT_END_RE.search(text)
    if m:
        text = text[:m.start()]
    return text.strip()


# ---------------------------------------------------------------------------
# ALL-CAPS transcript normalization (YouTube/podcast paste)
# ---------------------------------------------------------------------------

def is_mostly_caps(text):
    letters = re.findall(r"[a-zA-Z]", text)
    if len(letters) < 50:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.8


def normalize_transcript(text):
    """De-capitalize an ALL-CAPS transcript: strip [7:07] timestamps, turn
    >> speaker markers into paragraph breaks, join hard line breaks, then
    re-capitalize sentence starts and standalone 'I'. Proper nouns can't be
    recovered — they stay lowercase."""
    t = re.sub(r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}\]", " ", text)  # [7:07] [1:23:45]
    t = t.replace(">>", "\x02")                                # speaker-turn sentinel
    t = re.sub(r"\s*\n\s*", " ", t)                            # join hard line breaks
    t = t.replace("\x02", "\n\n")                              # speaker turns → paragraphs
    t = re.sub(r" {2,}", " ", t).strip().lower()
    t = re.sub(r"\bi\b", "I", t)
    t = re.sub(r"(^|[.?!][\"'“”’)\]]*\s+)([a-z\"“'‘(])",
               lambda m: m.group(1) + m.group(2).upper(), t)
    t = re.sub(r"(\n\n\s*)([a-z\"“'‘(])",
               lambda m: m.group(1) + m.group(2).upper(), t)
    return t


def paragraphs_from_text(text, cleanup):
    text = strip_gutenberg(text.replace("\r\n", "\n").replace("\r", "\n"))
    if cleanup:
        words = load_wordlist()
        lines, block_start = [], True
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                block_start = True
                continue
            lines.append((line, block_start))
            block_start = False
        # keep heading lines (CHAPTER I. / QUESTION 3 ...) as standalone
        # paragraphs so the stitcher can't glue them onto following prose;
        # a short caps/title-case line after a heading is its subtitle
        paras, buf = [], []
        i = 0
        while i < len(lines):
            line, bs = lines[i]
            if len(line) <= 80 and HEADING_RE.match(line):
                if buf:
                    paras.extend(stitch_paragraphs(buf, words))
                    buf = []
                paras.append(line)
                if i + 1 < len(lines):
                    nxt = lines[i + 1][0]
                    if len(nxt) <= 80 and not HEADING_RE.match(nxt) \
                            and (nxt.isupper() or nxt.istitle()):
                        paras.append(nxt)
                        i += 1
            else:
                buf.append((line, bs))
            i += 1
        if buf:
            paras.extend(stitch_paragraphs(buf, words))
        return paras
    chunks = re.split(r"\n\s*\n", text)
    if len(chunks) == 1 and text.count("\n") >= 3:
        # Kindle / Medium style paste: no blank lines — each line a paragraph
        chunks = text.split("\n")
    paras = []
    for chunk in chunks:
        joined = " ".join(l.strip() for l in chunk.splitlines() if l.strip())
        if joined:
            paras.append(joined)
    return paras


# Gutenberg-style chapter headings: a short paragraph starting with a
# structural keyword (covers Aquinas's QUESTION/ARTICLE too)
HEADING_RE = re.compile(
    r"^(?:chapter|book|part|section|question|article|treatise|letter|volume|"
    r"canto)\b\.?\s*(?:[0-9]+|[ivxlcdm]+|[a-z]+)?\s*[.):\-–—]?", re.I)


def split_chapters(paras):
    """Split a long paste at heading paragraphs (short line starting with
    CHAPTER/PART/QUESTION/...). A bare heading (<=4 words) absorbs the next
    short paragraph as its subtitle. Returns [(title or None, [paras])];
    a single section when no headings are found."""
    chunks = []
    title, cur = None, []
    i = 0
    while i < len(paras):
        p = paras[i]
        if len(p) <= 80 and HEADING_RE.match(p):
            if cur:
                chunks.append((title, cur))
            title, cur = p, [p]  # heading line stays in the content (verbatim)
            if len(p.split()) <= 4 and i + 1 < len(paras) \
                    and len(paras[i + 1]) <= 80 and not HEADING_RE.match(paras[i + 1]) \
                    and (paras[i + 1].isupper() or paras[i + 1].istitle()):
                title = p + " — " + paras[i + 1]
                cur.append(paras[i + 1])  # subtitle stays in the content too
                i += 1
        else:
            cur.append(p)
        i += 1
    if cur:
        chunks.append((title, cur))
    if len(chunks) < 2:
        return [(None, paras)]
    return chunks


# ---------------------------------------------------------------------------
# reddit mode — comment-thread parser
# ---------------------------------------------------------------------------
# Paste format: optional post text, optional "---COMMENTS---" line, then
# comments as "u/name: text" with replies indented under their parent.
# Lines without a u/ prefix continue the current comment. Usernames are
# dropped; indentation becomes tree depth.

_REDDIT_COMMENT_RE = re.compile(r"^(\s*)u/[\w-]+:\s*(.*)$")
_REDDIT_SEP_RE = re.compile(r"^---COMMENTS---\s*$", re.M)


def build_reddit_tree(text):
    post, comments = "", text
    m = _REDDIT_SEP_RE.search(text)
    if m:
        post, comments = text[:m.start()].strip(), text[m.end():]
    roots, stack = [], []
    post_node = None
    if post:
        post_text = " ".join(l.strip() for l in post.splitlines() if l.strip())
        if post_text:
            post_node = Node(post_text)
            roots.append(post_node)
    for raw in comments.splitlines():
        if not raw.strip():
            continue
        cm = _REDDIT_COMMENT_RE.match(raw)
        if cm:
            indent = len(cm.group(1))
            node = Node(cm.group(2).strip())
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else post_node
            if parent is not None:
                parent.children.append(node)
            else:
                roots.append(node)
            stack.append((indent, node))
        else:
            cont = raw.strip()
            target = stack[-1][1] if stack else post_node
            if target is not None:
                target.text = (target.text + " " + cont).strip()
            else:
                roots.append(Node(cont))
    return roots


# ---------------------------------------------------------------------------
# routes — single paste → outline flow; nothing stored
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/outline", methods=["POST"])
def outline():
    text = (request.form.get("text") or "").strip()
    if not text:
        return render_template("index.html", error="Paste some text first.")
    mode = request.form.get("mode", "theology")
    if mode not in ("theology", "general", "economy", "seeking-alpha", "reddit"):
        mode = "theology"
    cleanup = bool(request.form.get("cleanup"))
    decaps = bool(request.form.get("decaps"))
    orig_text = text
    # timestamp/tidy subs would destroy reddit indentation — skip them there
    if mode != "reddit":
        text = strip_transcript_timestamps(text)
    # de-caps joins all lines, which would destroy reddit indentation — skip it there
    if decaps and mode != "reddit" and is_mostly_caps(text):
        text = normalize_transcript(text)
    paras = paragraphs_from_text(text, cleanup)
    if not paras:
        return render_template("index.html", error="No paragraphs found.")
    title = (request.form.get("title") or "").strip()
    if not title:
        head = re.findall(r"\S+", paras[0])[:8]
        title = " ".join(head) + ("…" if len(head) == 8 else "")
    if mode == "reddit":
        roots = build_reddit_tree(text)
        md = render_markdown(title, roots)
        n_nodes, maxd, tags, n_unplaced = chapter_stats(roots)
        return render_template("outline.html", title=title, mode=mode,
                               sections=[{"title": None, "roots": roots}],
                               panel=None, md=md, coverage=None,
                               n_inserted=None, n_nodes=n_nodes, maxd=maxd,
                               tags=tags, n_unplaced=n_unplaced,
                               orig_text=orig_text, cleanup=cleanup,
                               form_title=request.form.get("title", ""))
    tag_fn = tag_sentence if mode in ("theology", "general") else econ_tag_sentence
    chunks = split_chapters(paras) if mode == "general" else [(None, paras)]
    sections, md_all = [], []
    n_nodes, maxd, n_unplaced = 0, 0, 0
    tags = collections.Counter()
    for ctitle, cparas in chunks:
        croots = outline_chapter(cparas, tag_fn)
        md_all.append(render_markdown(ctitle or title, croots))
        n, d, tg, u = chapter_stats(croots)
        n_nodes += n
        maxd = max(maxd, d)
        n_unplaced += u
        tags.update(tg)
        sections.append({"title": ctitle, "roots": croots})
    source = "\n\n".join(paras)
    md = "\n".join(md_all)
    coverage, inserted, _dropped = verify_chapter(md, source)
    panel = None
    if mode in ("economy", "seeking-alpha"):
        sents = [s for p in paras for s in split_sentences(p)]
        panel = econ_structure(sents, mode)
    return render_template("outline.html", title=title, mode=mode,
                           sections=sections, panel=panel, md=md,
                           coverage=round(coverage * 100, 2),
                           n_inserted=sum(inserted.values()), n_nodes=n_nodes,
                           maxd=maxd, tags=dict(tags), n_unplaced=n_unplaced,
                           orig_text=orig_text, cleanup=cleanup,
                           form_title=request.form.get("title", ""))


if __name__ == "__main__":
    app.run(port=5004, debug=True)
