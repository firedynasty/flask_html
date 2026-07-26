"""
Gutenberg EPUB -> per-chapter txt files + verbatim outlines + web reader.

Same shape as 17-pdf_outliner's pipeline, but the chapter map comes from the
EPUB's own table of contents — no page-offset arithmetic, no hardcoded
chapter list. EPUB parsing is done by the vendored @gxl/epub-parser library
(./epub-parser, compiled to lib/); dump_sections.js drives it and cuts each
section's text at toc anchor boundaries (several toc entries point inside
the same xhtml file). This app merges the slices into reading units, writes
clean/<slug>.txt + chapters.json, outlines each unit into outline/<slug>.md
(see outliner.py — the same heuristic engine as 17-CS_Lewis) with a token
coverage report, and serves index / read / outline navigation.

Requires: node; `npm install --ignore-scripts && npx tsc` inside epub-parser/
(has been run once already — lib/ is committed state on this machine).

Usage:
    python app.py [bookdir]            # builds clean/ + outline/ on first run
    python app.py [bookdir] --rebuild  # force re-run
    open http://localhost:5005

bookdir defaults to this directory (the Aquinas epub); pass e.g. `quixote`
to convert/serve quixote/pg996-images-3.epub — outputs land in <bookdir>/
(clean/, outline/, chapters.json), so books don't clobber each other.
"""

import collections
import glob
import json
import os
import re
import subprocess
import sys

from flask import Flask, Response, abort, redirect, render_template, url_for

import outliner

BASE = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = BASE
for a in sys.argv[1:]:
    if not a.startswith("--"):
        BOOK_DIR = os.path.join(BASE, a)
_epubs = sorted(glob.glob(os.path.join(BOOK_DIR, "*.epub")))
EPUB_PATH = _epubs[0] if _epubs else os.path.join(BOOK_DIR, "book.epub")
DUMP_JS = os.path.join(BASE, "dump_sections.js")
CLEAN_DIR = os.path.join(BOOK_DIR, "clean")
OUTLINE_DIR = os.path.join(BOOK_DIR, "outline")
REPORT_JSON = os.path.join(OUTLINE_DIR, "_report.json")
CHAPTERS_JSON = os.path.join(BOOK_DIR, "chapters.json")

app = Flask(__name__)

HEADING_TAGS = frozenset(["h1", "h2", "h3", "h4", "h5", "h6"])


def parse_epub():
    """Run the Node driver; returns {info, dropped_words, slices}.
    slices: [{label, level, blocks:[[tag, text], ...]}] in reading order."""
    proc = subprocess.run(["node", DUMP_JS, EPUB_PATH],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("epub parse failed:\n" + proc.stderr[-3000:])
    return json.loads(proc.stdout)


def slugify(title):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-",
                                     title.lower())).strip("-")


def build():
    if not os.path.exists(EPUB_PATH):
        raise SystemExit(f"epub not found: {EPUB_PATH}")
    os.makedirs(CLEAN_DIR, exist_ok=True)
    os.makedirs(OUTLINE_DIR, exist_ok=True)
    # stale outputs from a previous epub in the same bookdir would linger
    for stale in glob.glob(os.path.join(CLEAN_DIR, "*.txt")) + \
            glob.glob(os.path.join(OUTLINE_DIR, "*.md")):
        os.remove(stale)
    data = parse_epub()
    info = data.get("info") or {}
    book_title, book_author = info.get("title"), info.get("author")
    slices = [{"label": s["label"], "level": s["level"],
               "blocks": [(tag, text) for tag, text in s["blocks"]]}
              for s in data["slices"]]
    dropped = data["dropped_words"]
    total_words = dropped + sum(len(t.split())
                                for s in slices for _, t in s["blocks"])

    # drop anchor-less/empty slices, then the html CONTENTS page
    # (this app's own index replaces it)
    slices = [s for s in slices if s["blocks"]]
    contents_words = sum(len(t.split())
                         for s in slices if s["label"].upper().startswith("CONTENTS")
                         for _, t in s["blocks"])
    slices = [s for s in slices if not s["label"].upper().startswith("CONTENTS")]

    # fold heading-only slices (QUESTION LXXXI, bare article numerals) into
    # the slice that follows, keeping the outermost nesting level
    merged = []
    for s in slices:
        if merged and all(t in HEADING_TAGS for t, _ in merged[-1]["blocks"]):
            prev = merged.pop()
            s = {"label": prev["label"] + " — " + s["label"],
                 "level": min(prev["level"], s["level"]),
                 "blocks": prev["blocks"] + s["blocks"]}
        merged.append(s)

    # groups: a level-0 slice opens a new group; deeper slices join it
    groups = []
    units = []  # flat reading order, for slugs + prev/next
    for s in merged:
        label = "Footnotes" if s["label"].upper() == "FOOTNOTES:" else s["label"]
        unit = {"title": label,
                "n_blocks": len(s["blocks"]),
                "words": sum(len(t.split()) for _, t in s["blocks"])}
        if s["level"] == 0 or not groups:
            groups.append(label)
        unit["group"] = groups[-1]
        units.append((unit, s))

    out = []
    report = []
    for i, (unit, s) in enumerate(units):
        slug = f"{i:02d}-{slugify(unit['title'])[:40]}".strip("-")
        unit["slug"] = slug
        body = "\n\n".join(t for _, t in s["blocks"])
        with open(os.path.join(CLEAN_DIR, slug + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write(unit["title"] + "\n\n" + body + "\n")
        out.append(unit)

        paras = [p for p in body.split("\n\n") if p.strip()]
        roots = outliner.outline_chapter(paras)
        md = outliner.render_markdown(unit["title"], roots)
        with open(os.path.join(OUTLINE_DIR, slug + ".md"), "w",
                  encoding="utf-8") as f:
            f.write(md)
        coverage, inserted, dropped_ct = outliner.verify_chapter(md, body)
        n_nodes, maxd, tags, n_unplaced = outliner.chapter_stats(roots)
        report.append({
            "slug": slug, "title": unit["title"], "group": unit["group"],
            "coverage": round(coverage * 100, 2),
            "inserted": dict(inserted.most_common(20)),
            "n_inserted": sum(inserted.values()),
            "n_dropped": sum(dropped_ct.values()),
            "dropped_sample": dict(dropped_ct.most_common(15)),
            "nodes": n_nodes, "max_depth": maxd, "tags": tags,
            "unplaced": n_unplaced, "paragraphs": len(paras),
            "flagged": coverage < 0.98 or sum(inserted.values()) > 0,
        })
    captured = sum(u["words"] for u in out)

    with open(CHAPTERS_JSON, "w", encoding="utf-8") as f:
        json.dump({"book_title": book_title, "book_author": book_author,
                   "units": out}, f, indent=1)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    write_report_md(report)
    return {"units": out, "captured": captured, "total": total_words,
            "dropped": dropped, "contents": contents_words}


def write_report_md(report):
    lines = ["# Verification report", "",
             "| unit | coverage % | inserted | dropped | nodes | depth | unplaced | tags |",
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

def load_units():
    if not os.path.exists(CHAPTERS_JSON):
        return None
    with open(CHAPTERS_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_report():
    if not os.path.exists(REPORT_JSON):
        return None
    with open(REPORT_JSON, encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    data = load_units()
    if data is None:
        return redirect(url_for("rebuild"))
    groups = collections.OrderedDict()
    for u in data["units"]:
        groups.setdefault(u["group"], []).append(u)
    return render_template("index.html", groups=groups,
                           book_title=data["book_title"],
                           book_author=data["book_author"],
                           n_units=len(data["units"]),
                           total_words=sum(u["words"] for u in data["units"]))


def find_unit(data, slug):
    for i, u in enumerate(data["units"]):
        if u["slug"] == slug:
            return i
    return None


@app.route("/unit/<slug>")
def unit(slug):
    data = load_units() or {"units": []}
    i = find_unit(data, slug)
    path = os.path.join(CLEAN_DIR, slug + ".txt")
    if i is None or not os.path.exists(path):
        abort(404)
    with open(path, encoding="utf-8") as f:
        paras = [p for p in f.read().split("\n\n") if p.strip()]
    title, paras = paras[0], paras[1:]
    units = data["units"]
    return render_template(
        "unit.html", meta=units[i], title=title, paras=paras,
        idx=i + 1, n=len(units),
        book_title=data.get("book_title"),
        prev_slug=units[i - 1]["slug"] if i > 0 else None,
        next_slug=units[i + 1]["slug"] if i + 1 < len(units) else None)


@app.route("/outline/<slug>")
def outline_view(slug):
    report = load_report() or []
    meta = next((r for r in report if r["slug"] == slug), None)
    md_path = os.path.join(OUTLINE_DIR, slug + ".md")
    if meta is None or not os.path.exists(md_path):
        abort(404)
    roots = outliner.parse_outline_md(md_path)
    idx = [r["slug"] for r in report].index(slug)
    prev_slug = report[idx - 1]["slug"] if idx > 0 else None
    next_slug = report[idx + 1]["slug"] if idx + 1 < len(report) else None
    return render_template("outline.html", meta=meta, roots=roots,
                           prev_slug=prev_slug, next_slug=next_slug)


@app.route("/txt/<slug>")
def txt(slug):
    path = os.path.join(CLEAN_DIR, slug + ".txt")
    if not os.path.exists(path):
        abort(404)
    with open(path, encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/plain; charset=utf-8")


@app.route("/rebuild")
def rebuild():
    build()
    return redirect(url_for("index"))


if __name__ == "__main__":
    if "--rebuild" in sys.argv or not os.path.exists(CHAPTERS_JSON) \
            or not os.path.exists(REPORT_JSON):
        print("Parsing epub ...")
        rep = build()
        pct = 100.0 * rep["captured"] / max(1, rep["total"])
        print(f"  {len(rep['units'])} units; captured {rep['captured']}/"
              f"{rep['total']} words ({pct:.1f}%)")
        print(f"  dropped: {rep['dropped']} pre-toc words, "
              f"{rep['contents']} contents-page words")
        if pct < 95:
            print("  ! coverage below 95% — check the toc anchors")
        report = load_report() or []
        bad = [r for r in report if r["flagged"]]
        print(f"  outlined; {len(bad)} units flagged for review "
              f"(coverage < 98% or insertions)")
        for r in bad:
            print(f"   ! {r['slug']}: coverage={r['coverage']} "
                  f"inserted={r['n_inserted']}")
    app.run(port=5005, debug=True)
