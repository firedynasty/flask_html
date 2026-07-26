"""
Verbatim logical-structure outliner — the heuristic Phase 3/4 engine from
17-CS_Lewis/app.py, extracted so any paragraphs-in source can be outlined.

  outline_chapter(paragraphs) -> [Node]      tagged bullet tree
  render_markdown(title, roots) -> str       one bullet per line, [tag] suffix
  verify_chapter(md, source)   -> coverage   token-multiset diff outline vs src
  chapter_stats(roots)         -> counts     nodes / depth / tags / unplaced
  parse_outline_md(path)       -> [dict]     read a .md back into a tree

Difference from 17: split_sentences collapses internal newlines — EPUB-derived
paragraphs contain single \n breaks, and the md format is one bullet per line.
"""

import collections
import re

# ordered: first match wins. Checked against the sentence with leading
# quotes/brackets stripped, case-insensitive.
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
TAG_RES = [(tag, re.compile(rx, re.I)) for tag, rx in TAG_RULES]

STOPWORDS = {"their", "there", "which", "would", "could", "should", "about",
             "these", "those", "thing", "things", "people", "every", "being",
             "because", "before", "after", "other", "another", "between",
             "that", "this", "with", "from", "have", "been", "were", "what",
             "when", "where", "they", "them", "then", "than", "some", "into"}

# Anaphoric openers: a sentence starting this way refers back to the previous
# one, which corroborates the attachment without needing shared content words.
ANAPHORA_RE = re.compile(
    r"^(?:sometimes|often|usually|always|now|here|there|also|still|even|yes|no)?\s*"
    r"(this|that|these|those|it|its|he|she|they|and|indeed|nor|neither|either|"
    r"the same|such|so much|at any rate|in fact|anyway|none of us|we all|"
    r"all of us|you and i)\b", re.I)

# Definition-sense test for `means`. A definition is a construction —
# [term mentioned] (hedges) means [a meaning] — so the whole prefix must
# parse as a term-being-mentioned, then the complement is vetoed.
_QL = "\"'‘“"          # opening quotes
_QR = "\"'’”"          # closing quotes

_HEDGE = (
    r"(?:\s+(?:now|then|here|also|again|really|simply|just|merely|usually|"
    r"normally|generally|originally|properly|strictly|literally|roughly|"
    r"nowadays|today|[a-z]+ly)){0,3}"
)

_DEF_MEANS_RE = re.compile(
    r"^\s*(?P<subj>"
    r"[" + _QL + r"][^" + _QR + r"]{1,40}[" + _QR + r"]"          # 'Charity'
    r"|the\s+(?:word|term|name|phrase|expression)\s+"
    r"[" + _QL + r"]?[\w-]{1,30}[" + _QR + r"]?"                   # the word 'gentleman'
    r"|[A-Za-z][\w-]{1,30}[" + _QR + r"]"                          # Charity'  (leading quote stripped)
    r"|[A-Za-z][A-Za-z-]{1,30}"                                    # Dualism | Temperance | It
    r")"
    + _HEDGE +
    r"\s+mean(?:s|t)\b\s*(?P<obj>.*)$",
    re.I,
)

# Bare (unquoted, single-word) subjects that are never a term being defined.
_BAD_SUBJ = {
    "i", "he", "she", "we", "they", "you", "who", "one", "someone", "somebody",
    "anyone", "everyone", "everybody", "nobody", "that", "this", "these",
    "those", "there", "what", "which", "god", "christ", "jesus", "man",
    "people", "no",
}

# Complements that are propositions, prepositional phrases or adverbials
# rather than a meaning.
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


# footnote refs ([47]) following terminal punctuation are captured so they
# stay attached to the sentence they cite instead of vanishing into the
# sentence boundary
SENT_SPLIT_RE = re.compile(
    r"(?P<punct>[.?!]+[\"”’)\]]*)(?P<ref>\[\d+\])?\s+")

ABBR_MARK = "\x01"


def protect_abbrevs(text):
    t = re.sub(r"\b(Mr|Mrs|Dr|St|etc|vs|No|Jr|Sr|Messrs)\.",
               lambda m: m.group(1) + ABBR_MARK, text)
    t = re.sub(r"\b([ie])\. ?([ge])\.",
               lambda m: m.group(1) + ABBR_MARK + m.group(2) + ABBR_MARK, t)
    t = re.sub(r"\b([A-Z])\.", lambda m: m.group(1) + ABBR_MARK, text)
    # leading enumerator stays with its sentence: "1. It belongs…" (numbered
    # objections), not a bare "1" bullet
    t = re.sub(r"^(\d+)\.", lambda m: m.group(1) + ABBR_MARK, t)
    return t


def split_sentences(para):
    # collapse single newlines: EPUB paragraphs carry \n breaks, and the
    # outline md format is one bullet per line
    t = protect_abbrevs(re.sub(r"\s+", " ", para))
    out, pos = [], 0
    for m in SENT_SPLIT_RE.finditer(t):
        seg = t[pos:m.start()].strip()
        if m.group("ref"):
            seg = (seg + m.group("punct") + m.group("ref")).strip()
        nxt = t[m.end():m.end() + 1]
        # only split where the next sentence begins with capital/quote/digit
        if seg and (not nxt or nxt.isupper() or nxt in "\"“‘'(0123456789"):
            out.append(seg)
            pos = m.end()
    last = t[pos:].strip()
    if last:
        out.append(last)
    return [s.replace(ABBR_MARK, ".") for s in (x.strip() for x in out) if s]


def tag_sentence(sent):
    s = re.sub(r"^[\"“‘'(\[\]… ]+", "", sent)
    for tag, rx in TAG_RES:
        if rx.match(s):
            return tag
    return None


def content_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", text.lower())} - STOPWORDS


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


def outline_chapter(paragraphs):
    """Build the bullet tree for one unit. Returns the roots.

    Untagged sentences are attached only when corroborated: a colon before
    them (illustration), an anaphoric opener, a 'means' definition, or shared
    content words with the previous sentence / paragraph claim. Otherwise the
    sentence stays in the flow as a plain untagged top-level bullet
    (provisional=True — no relation asserted, but nothing hidden).

    'Means' definitions are collected and appended at the END of the claim's
    children (a definition glosses the whole paragraph, so it reads better
    after the reasons, not in front of them).
    """
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
            stripped = re.sub(r"^[\"“‘'(\[\]… ]+", "", s)
            tag = tag_sentence(s)
            if quote_heavy and tag is None:
                tag = "example"  # quoted speech inside an illustrative stretch
            if tag:
                node = Node(s, tag)
                claim.children.append(node)
                prev, prev_depth = node, 2
                continue
            # untagged: corroborate, or bucket
            ow = content_words(s)
            if prev.text.rstrip()[-1:] == ":":
                # follows a colon: it illustrates what precedes
                node = Node(s, "example")
                parent = prev if prev_depth < 4 else claim
                parent.children.append(node)
                prev, prev_depth = node, min(prev_depth + 1, 4)
            elif is_definition(stripped):
                node = Node(s, "definition")
                deferred_defs.append(node)  # placed at the end, not in front
                prev, prev_depth = node, 2
            elif ANAPHORA_RE.match(stripped) or \
                    (ow & content_words(prev.text)) or \
                    (ow & content_words(claim.text)):
                node = Node(s, "restatement")
                parent = prev if prev is not claim and prev_depth < 4 else claim
                parent.children.append(node)
                prev, prev_depth = node, min((prev_depth if parent is prev else 1) + 1, 4)
            else:
                # no corroboration: keep the sentence in the flow, unmarked
                roots.append(Node(s, provisional=True))
                prev, prev_depth = claim, 1  # do not chain under it
        claim.children.extend(deferred_defs)
    return roots


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


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
TAG_STRIP_RE = re.compile(r"\[(evidence|definition|qualification|example|analogy|"
                          r"concession|consequence|contrast|restatement)\]")


def tokens(text):
    return collections.Counter(TOKEN_RE.findall(text.lower().replace("’", "'")))


def verify_chapter(md_text, source_text):
    body = []
    for line in md_text.splitlines():
        if line.startswith("#") or line.lstrip().startswith("> why:"):
            continue
        line = line.strip()
        if line.startswith("- "):
            line = line[2:]
        line = TAG_STRIP_RE.sub("", line).replace("[…]", "").replace("…", "")
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
# md -> tree (for the Flask UI)
# ---------------------------------------------------------------------------

MD_LINE_RE = re.compile(
    r"^( *)- (.*?)(?: \[(evidence|definition|qualification|example|analogy|"
    r"concession|consequence|contrast|restatement)\])?$")


def parse_outline_md(path):
    """Parse an outline .md back into a node tree for rendering."""
    roots, stack = [], []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("#") or not line.strip():
                continue
            m = MD_LINE_RE.match(line)
            if not m:
                continue
            depth = len(m.group(1)) // 2
            node = {"tag": m.group(3), "text": m.group(2), "children": []}
            stack = stack[:depth]
            if stack:
                stack[-1]["children"].append(node)
            else:
                roots.append(node)
            stack.append(node)
    return roots
