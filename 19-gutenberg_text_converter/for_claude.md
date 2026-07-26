# for_claude.md — converting a new EPUB to `html_js_ported/`

Playbook for a future Claude Code session: turn a Gutenberg (or similar) EPUB
into a self-contained, no-server HTML reader with per-sentence tagged
outlines. Proven on two books (2026-07-25): Aquinas *On prayer and the
contemplative life* (top level, 76 units) and Cervantes *Don Quixote*
(`quixote/`, 145 units, 426k words).

## What the pipeline is

```
<book>/<book>.epub
  → app.py build        (node dump_sections.js → slices; python merges,
                         outlines, verifies → clean/<slug>.txt,
                         outline/<slug>.md, outline/_report.{json,md},
                         chapters.json)
  → make_portable.py    (chapters.json + clean/*.txt + outliner.py
                         → <book>/html_js_ported/index.html)
```

A "book" = **one directory containing exactly one .epub**. All outputs are
written inside that directory, so books never clobber each other.

## Prerequisites (already satisfied on this machine)

- `node` — used by `dump_sections.js`.
- `epub-parser/lib/` is **compiled, patched state — do not re-clone or
  reinstall it**. The upstream `sectionId` bug fix (assign `_manifest` before
  `_genStructure` in `src/parseEpub.ts`) only exists in the compiled `lib/`.
  If a reinstall is ever forced: `npm install --ignore-scripts && npx tsc`
  inside `epub-parser/`, then re-apply that patch.
- `python3` + `flask` (flask is only imported by `app.py`; `make_portable.py`
  itself is stdlib-only).

## Steps for a new book

```bash
cd 19-gutenberg_text_converter
mkdir <book>                          # e.g. "quixote"
mv /path/to/pgXXXX.epub <book>/       # exactly one .epub per directory

python app.py <book>                  # auto-builds (no chapters.json yet),
                                      # then serves at http://localhost:5005
# Ctrl-C the server if you only wanted the build.
# Later rebuilds of the same book: python app.py <book> --rebuild

python make_portable.py <book>        # writes <book>/html_js_ported/index.html
```

Serve the portable with any static server (`cd <book>/html_js_ported &&
python3 -m http.server 8020`) or just open the file — it is fully
self-contained (index / read / outline views, prev-next arrows, x-collapse,
A−/A+ font control, mobile CSS; no fetch calls).

## Verify before declaring done

`app.py` prints build stats; healthy numbers look like DQ's:
`145 units; captured 423828/426379 words (99.4%); 0 units flagged`.

1. **Word capture ≥ 95%** of total. Deliberate drops: pre-toc words and the
   CONTENTS page(s).
2. **0 flagged units** — a unit is flagged when outline token coverage < 98%
   or any inserted tokens. Details in `<book>/outline/_report.md`.
3. **No collapsed slices** — if one unit holds ~the whole book, the toc
   anchors didn't match. Inspect with:

   ```bash
   node dump_sections.js <book>/<book>.epub | python3 -c "
   import json,sys; d=json.load(sys.stdin)
   for s in d['slices']:
       w=sum(len(t.split()) for _,t in s['blocks'])
       print(s['level'], s['label'][:60], w)"
   ```

## Gotchas (both hit with real epubs)

- **Anchors on wrapper divs.** Some epubs (DQ) put navpoint anchors on
  `<div class="chapter" id=...>` around the whole chapter, not on block
  elements. `dump_sections.js sectionBlocks` collects ids from the block, its
  `<a id>` descendants, AND all ancestor elements — all three are needed. If
  the driver is ever rewritten, keep the ancestor walk or the whole book
  lands in one slice.
- **`build()` wipes** `*.txt` in `<book>/clean/` and `*.md` in
  `<book>/outline/` before writing — never keep two epubs in one bookdir.
- **File size is mostly images.** A 40+ MB epub parses in seconds; the xhtml
  is small. Portable HTML ends up ~11 KB per 1k words (DQ: 426k → 4.7 MB).
- **Flat tocs** (no part/volume nesting, e.g. DQ) produce one big group on
  the index page. Cosmetic; prev/next and titles still navigate fine.
- **Outline coverage regressions** usually come from sentence splitting in
  `outliner.py`: footnote refs `[47]` must stay attached to their sentence
  (see `SENT_SPLIT_RE` named groups), and abbreviations/leading enumerators
  are protected via `ABBR_MARK`. If many units suddenly drop below 98%,
  diff the dropped-token samples in `_report.md` — they'll name the culprit.

## File map

| file | role |
|---|---|
| `app.py` | paths per bookdir, build pipeline, Flask UI (:5005) |
| `dump_sections.js` | node driver: epub → anchor-cut slices JSON |
| `epub-parser/` | vendored @gxl/epub-parser, patched, compiled |
| `outliner.py` | 17-CS_Lewis Phase 3 engine: tag rules, tree builder, coverage verifier |
| `make_portable.py` | chapters.json + clean/ → self-contained HTML |
| `templates/` | Flask pages (index / unit / outline) |
