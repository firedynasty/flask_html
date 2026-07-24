"""
Gutenberg EPUB -> per-chapter txt files + web reader.

Same shape as 17-pdf_outliner's pipeline, but the chapter map comes from the
EPUB's own table of contents — no page-offset arithmetic, no hardcoded
chapter list. EPUB parsing is done by the vendored @gxl/epub-parser library
(./epub-parser, compiled to lib/); dump_sections.js drives it and cuts each
section's text at toc anchor boundaries (several toc entries point inside
the same xhtml file). This app merges the slices into reading units, writes
clean/<slug>.txt + chapters.json, and serves index / prev / next navigation.

Requires: node; `npm install --ignore-scripts && npx tsc` inside epub-parser/
(has been run once already — lib/ is committed state on this machine).

Usage:
    python app.py            # builds clean/ + chapters.json on first run
    python app.py --rebuild  # force re-run
    open http://localhost:5005
"""

import collections
import json
import os
import re
import subprocess
import sys

from flask import Flask, Response, abort, redirect, render_template, url_for

BASE = os.path.dirname(os.path.abspath(__file__))
EPUB_PATH = os.path.join(BASE, "pg22295-images-3 (1).epub")
DUMP_JS = os.path.join(BASE, "dump_sections.js")
CLEAN_DIR = os.path.join(BASE, "clean")
CHAPTERS_JSON = os.path.join(BASE, "chapters.json")

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
    for i, (unit, s) in enumerate(units):
        slug = f"{i:02d}-{slugify(unit['title'])[:40]}".strip("-")
        unit["slug"] = slug
        body = "\n\n".join(t for _, t in s["blocks"])
        with open(os.path.join(CLEAN_DIR, slug + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write(unit["title"] + "\n\n" + body + "\n")
        out.append(unit)
    captured = sum(u["words"] for u in out)

    with open(CHAPTERS_JSON, "w", encoding="utf-8") as f:
        json.dump({"book_title": book_title, "book_author": book_author,
                   "units": out}, f, indent=1)
    return {"units": out, "captured": captured, "total": total_words,
            "dropped": dropped, "contents": contents_words}


# ---------------------------------------------------------------------------
# Flask UI
# ---------------------------------------------------------------------------

def load_units():
    if not os.path.exists(CHAPTERS_JSON):
        return None
    with open(CHAPTERS_JSON, encoding="utf-8") as f:
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
    if "--rebuild" in sys.argv or not os.path.exists(CHAPTERS_JSON):
        print("Parsing epub ...")
        rep = build()
        pct = 100.0 * rep["captured"] / max(1, rep["total"])
        print(f"  {len(rep['units'])} units; captured {rep['captured']}/"
              f"{rep['total']} words ({pct:.1f}%)")
        print(f"  dropped: {rep['dropped']} pre-toc words, "
              f"{rep['contents']} contents-page words")
        if pct < 95:
            print("  ! coverage below 95% — check the toc anchors")
    app.run(port=5005, debug=True)
