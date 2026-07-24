"""
PDF Outliner — verbatim logical-structure outline of a book-length PDF.

Implements the four phases from prompt.txt, fully local and offline:
  Phase 1  extract + clean (de-hyphenation, running heads, ligatures, reflow)
  Phase 2  chunk one chapter per unit (chapter map below)
  Phase 3  outline verbatim sentences as a tagged bullet tree (heuristic tagger)
  Phase 4  verify token-multiset coverage of outline vs. source

Usage:
    python app.py            # builds clean/ + outline/ on first run, then serves
    python app.py --rebuild  # force re-run of the pipeline
    open http://localhost:5003
"""

import collections
import json
import os
import re
import sys

import fitz
from flask import Flask, abort, redirect, render_template, url_for

BASE = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(BASE, "Mere-Christianity-C.-S.-Lewis.pdf")
CLEAN_DIR = os.path.join(BASE, "clean")
OUTLINE_DIR = os.path.join(BASE, "outline")
REPORT_JSON = os.path.join(OUTLINE_DIR, "_report.json")

# printed page -> pdf page offset, verified at 5 points across the book
OFFSET = 18
BACK_MATTER_PDF = 246  # "About the Author" starts here

# (printed start page, chapter title) — transcribed from the book's contents page
BOOKS = [
    ("Book 1", "Right and Wrong as a Clue to the Meaning of the Universe", [
        (3, "The Law of Human Nature"),
        (9, "Some Objections"),
        (16, "The Reality of the Law"),
        (21, "What Lies Behind the Law"),
        (28, "We Have Cause to Be Uneasy"),
    ]),
    ("Book 2", "What Christians Believe", [
        (35, "The Rival Conceptions of God"),
        (40, "The Invasion"),
        (47, "The Shocking Alternative"),
        (53, "The Perfect Penitent"),
        (60, "The Practical Conclusion"),
    ]),
    ("Book 3", "Christian Behaviour", [
        (69, "The Three Parts of Morality"),
        (76, "The 'Cardinal Virtues'"),
        (82, "Social Morality"),
        (88, "Morality and Psychoanalysis"),
        (94, "Sexual Morality"),
        (104, "Christian Marriage"),
        (115, "Forgiveness"),
        (121, "The Great Sin"),
        (129, "Charity"),
        (134, "Hope"),
        (138, "Faith"),
        (144, "Faith (continued)"),
    ]),
    ("Book 4", "Beyond Personality: or First Steps in the Doctrine of the Trinity", [
        (153, "Making and Begetting"),
        (160, "The Three-Personal God"),
        (166, "Time and Beyond Time"),
        (172, "Good Infection"),
        (178, "The Obstinate Toy Soldiers"),
        (183, "Two Notes"),
        (187, "Let's Pretend"),
        (195, "Is Christianity Hard or Easy?"),
        (201, "Counting the Cost"),
        (207, "Nice People or New Men"),
        (218, "The New Men"),
    ]),
]
# front matter: (slug, title, first pdf page, last pdf page)
FRONT_MATTER = [
    ("00-preface", "Preface", 5, 14),
    ("00-foreword", "Foreword", 15, 18),
]

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Phase 1 — extract and clean
# ---------------------------------------------------------------------------

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
             "\ufb03": "ffi", "\ufb04": "ffl"}

ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.I)


def load_wordlist(path="/usr/share/dict/words"):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return {w.strip().lower() for w in f if w.strip()}
    except OSError:
        return set()


def squash(text):
    """lowercase, letters/digits only — for title comparison."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_running_head(line):
    """Letter-spaced running head, e.g. 'm e r e  c h r i s t i a n i t y'."""
    toks = line.strip().split()
    if len(toks) < 3:
        return False
    single = sum(1 for t in toks if len(t) == 1)
    return single / len(toks) > 0.6


def is_page_number(line, is_edge):
    """Bare arabic or roman numeral; only trusted near a page edge."""
    if not is_edge:
        return False
    t = line.strip().replace(" ", "")
    return t.isdigit() or (len(t) <= 6 and bool(ROMAN_RE.match(t)))


def should_join(w1, w2, words):
    """Dictionary check for de-hyphenation (prompt Phase 1.1)."""
    hyph = f"{w1}-{w2}".lower()
    joined = f"{w1}{w2}".lower()
    if hyph in words:
        return False          # genuine compound, dictionary says so
    if joined in words:
        return True           # typesetting break of a real word
    if w1.lower() in words and w2.lower() in words:
        return False          # both halves are words: keep the hyphen
    return True               # fragment: join


def extract_chapter_lines(doc, first_page, last_page, chapter_title):
    """Yield (line, is_block_start) across the chapter's pages, with running
    heads, page numbers and the chapter number/title header removed."""
    out = []
    title_sq = squash(chapter_title)
    for pno in range(first_page, last_page + 1):
        page = doc[pno]
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        # drop near-empty pages (book title pages, blanks between books)
        lines_on_page = [l for b in blocks for l in b[4].splitlines() if l.strip()]
        if len(lines_on_page) < 8 and pno != first_page:
            continue
        dropped_title = False
        for bi, b in enumerate(blocks):
            blines = [l.strip() for l in b[4].splitlines() if l.strip()]
            for li, line in enumerate(blines):
                flat = line
                for lig, rep in LIGATURES.items():
                    flat = flat.replace(lig, rep)
                edge = (bi in (0, len(blocks) - 1))
                if is_running_head(flat):
                    continue
                if is_page_number(flat, edge):
                    continue
                # chapter header on its first page: bare number, then title line
                if pno == first_page and not dropped_title:
                    if flat.strip().isdigit():
                        continue
                    if squash(flat) == title_sq:
                        dropped_title = True
                        continue
                out.append((flat, li == 0))
    return out


def stitch_paragraphs(lines, words):
    """Join lines into paragraphs: de-hyphenate at line ends, start a new
    paragraph at a block boundary only when the previous text closed a sentence."""
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
                cur = cur + line  # keep hyphen, no space
            continue
        if is_block_start and re.search(r"[.?!][\"”’)\]]?\s*$", cur):
            paras.append(cur)
            cur = line
        else:
            cur = cur + " " + line
    if cur:
        paras.append(cur)
    return paras


# ---------------------------------------------------------------------------
# Phase 3 — outline
# ---------------------------------------------------------------------------

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

# Definition-sense test for `means` (replaces the old DEF_MID_RE keyword
# window). A definition is a construction — [term mentioned] (hedges) means
# [a meaning] — so the whole prefix must parse as a term-being-mentioned,
# then the complement is vetoed. Anchoring the subject kills the noun-`means`
# ("means of…") and inference-`means` ("it means they are…") false positives.
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

SENT_SPLIT_RE = re.compile(r"[.?!]+[\"”’)\]]*\s+")


ABBR_MARK = "\x01"


def protect_abbrevs(text):
    t = re.sub(r"\b(Mr|Mrs|Dr|St|etc|vs|No|Jr|Sr|Messrs)\.",
               lambda m: m.group(1) + ABBR_MARK, text)
    t = re.sub(r"\b([ie])\. ?([ge])\.",
               lambda m: m.group(1) + ABBR_MARK + m.group(2) + ABBR_MARK, t)
    t = re.sub(r"\b([A-Z])\.", lambda m: m.group(1) + ABBR_MARK, text)
    return t


def split_sentences(para):
    t = protect_abbrevs(para)
    out, pos = [], 0
    for m in SENT_SPLIT_RE.finditer(t):
        seg = t[pos:m.start()].strip()
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
    """Build the bullet tree for one chapter. Returns the roots.

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
# Phase 4 — verify
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
# build pipeline
# ---------------------------------------------------------------------------

def chapter_list():
    """Flat list of chapter descriptors in reading order."""
    items = []
    for slug, title, p0, p1 in FRONT_MATTER:
        items.append({"slug": slug, "title": title, "book": "Front Matter",
                      "num": "", "first": p0, "last": p1})
    starts = []
    for book, book_title, chs in BOOKS:
        for i, (printed, title) in enumerate(chs):
            starts.append({"book": book, "book_title": book_title,
                           "num": str(i + 1), "title": title,
                           "first": printed + OFFSET})
    for i, ch in enumerate(starts):
        nxt = starts[i + 1]["first"] if i + 1 < len(starts) else BACK_MATTER_PDF
        ch["last"] = nxt - 1
        ch["slug"] = f"b{ch['book'][-1]}-{int(ch['num']):02d}-{slugify(ch['title'])}"
        items.append(ch)
    return items


def slugify(title):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-")


def build():
    os.makedirs(CLEAN_DIR, exist_ok=True)
    os.makedirs(OUTLINE_DIR, exist_ok=True)
    words = load_wordlist()
    doc = fitz.open(PDF_PATH)
    report = []
    for ch in chapter_list():
        lines = extract_chapter_lines(doc, ch["first"], ch["last"], ch["title"])
        paras = stitch_paragraphs(lines, words)
        source = "\n\n".join(paras) + "\n"
        with open(os.path.join(CLEAN_DIR, ch["slug"] + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write(source)
        roots = outline_chapter(paras)
        md = render_markdown(ch["title"], roots)
        with open(os.path.join(OUTLINE_DIR, ch["slug"] + ".md"), "w",
                  encoding="utf-8") as f:
            f.write(md)
        coverage, inserted, dropped = verify_chapter(md, source)
        n_nodes, maxd, tags, n_unplaced = chapter_stats(roots)
        report.append({
            **{k: ch[k] for k in ("slug", "title", "book", "num")},
            "book_title": ch.get("book_title", ""),
            "coverage": round(coverage * 100, 2),
            "inserted": dict(inserted.most_common(20)),
            "n_inserted": sum(inserted.values()),
            "n_dropped": sum(dropped.values()),
            "dropped_sample": dict(dropped.most_common(15)),
            "nodes": n_nodes, "max_depth": maxd, "tags": tags,
            "unplaced": n_unplaced, "paragraphs": len(paras),
            "flagged": coverage < 0.98 or sum(inserted.values()) > 0,
        })
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    write_report_md(report)
    return report


def write_report_md(report):
    lines = ["# Verification report", "",
             "| chapter | coverage % | inserted | dropped | nodes | depth | unplaced | tags |",
             "|---|---|---|---|---|---|---|---|"]
    for r in report:
        flag = " **!**" if r["flagged"] else ""
        tags = ", ".join(f"{k}:{v}" for k, v in sorted(r["tags"].items()))
        lines.append(f"| {r['slug']} | {r['coverage']}{flag} | {r['n_inserted']} | "
                     f"{r['n_dropped']} | {r['nodes']} | {r['max_depth']} | "
                     f"{r['unplaced']} | {tags} |")
    lines.append("")
    ins = [r for r in report if r["n_inserted"]]
    if ins:
        lines += ["## Insertions (tokens in outline, absent from source)", ""]
        for r in ins:
            lines.append(f"- **{r['slug']}**: {r['inserted']}")
        lines.append("")
    with open(os.path.join(OUTLINE_DIR, "_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Flask UI
# ---------------------------------------------------------------------------

def load_report():
    if not os.path.exists(REPORT_JSON):
        return None
    with open(REPORT_JSON, encoding="utf-8") as f:
        return json.load(f)


MD_LINE_RE = re.compile(
    r"^( *)- (.*?)(?: \[(evidence|definition|qualification|example|analogy|"
    r"concession|consequence|contrast|restatement)\])?$")


def parse_outline_md(slug):
    """Parse an outline .md back into a node tree for rendering."""
    path = os.path.join(OUTLINE_DIR, slug + ".md")
    if not os.path.exists(path):
        return None
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


@app.route("/")
def index():
    report = load_report()
    if report is None:
        return redirect(url_for("rebuild"))
    groups = collections.OrderedDict()
    for r in report:
        key = (r["book"], r["book_title"])
        groups.setdefault(key, []).append(r)
    flagged = [r for r in report if r["flagged"]]
    return render_template("index.html", groups=groups, flagged=flagged,
                           report=report)


@app.route("/chapter/<slug>")
def chapter(slug):
    report = load_report() or []
    meta = next((r for r in report if r["slug"] == slug), None)
    parsed = parse_outline_md(slug)
    if meta is None or parsed is None:
        abort(404)
    roots = parsed
    idx = [r["slug"] for r in report].index(slug)
    prev_slug = report[idx - 1]["slug"] if idx > 0 else None
    next_slug = report[idx + 1]["slug"] if idx + 1 < len(report) else None
    return render_template("chapter.html", meta=meta, roots=roots,
                           prev_slug=prev_slug, next_slug=next_slug)


@app.route("/source/<slug>")
def source(slug):
    path = os.path.join(CLEAN_DIR, slug + ".txt")
    if not os.path.exists(path):
        abort(404)
    report = load_report() or []
    meta = next((r for r in report if r["slug"] == slug), None)
    with open(path, encoding="utf-8") as f:
        paras = [p for p in f.read().split("\n\n") if p.strip()]
    return render_template("source.html", meta=meta, slug=slug, paras=paras)


@app.route("/rebuild")
def rebuild():
    build()
    return redirect(url_for("index"))


if __name__ == "__main__":
    if "--rebuild" in sys.argv or not os.path.exists(REPORT_JSON):
        print("Building clean/ and outline/ ...")
        rep = build()
        bad = [r for r in rep if r["flagged"]]
        print(f"  {len(rep)} units; {len(bad)} flagged for review "
              f"(coverage < 98% or insertions)")
        for r in bad:
            print(f"   ! {r['slug']}: coverage={r['coverage']} "
                  f"inserted={r['n_inserted']}")
    app.run(port=5003, debug=False)
