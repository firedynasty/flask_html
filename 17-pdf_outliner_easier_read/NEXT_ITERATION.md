# Next iteration: paste-an-article → outline

Goal: a page with a textarea where I paste an article (or chapter) and get the
same kind of verbatim outline as the PDF outliner in this directory.

Reuse `app.py` from this project — the core is input-agnostic. Everything below
is what worked and what bit me, so the next build skips the debugging.

## What to reuse (works, tested)

The pipeline splits into an input-dependent half and an input-independent half.

**Input-independent (reuse as-is):**
- `split_sentences` — regex splitter with abbreviation protection
  (`Mr.`, `e.g.`, initials `C. S.`). Protect with a placeholder char, restore
  after splitting.
- `TAG_RULES` / `tag_sentence` — ordered regexes on the sentence opener:
  concession → example → analogy → contrast → evidence → **qualification →
  consequence** → restatement (incl. enumeration markers `First,` `Secondly,`)
  → definition. First match wins; order matters — qualification must precede
  consequence or consequence's `so` eats "so long as". Guards that fixed real
  mis-tags: `so\b(?!\s+(?:long|far|much|many|great|be\b))`,
  `while\b(?!\s+it\s+is\s+true)` in contrast, `(so )?far from` in contrast,
  `as far as|so far as` in qualification.
- `outline_chapter` — corroboration at attach time:
  1. tagged → child of the paragraph's claim (depth 2)
  2. previous sentence ends with `:` → `[example]`, child of previous
  3. `is_definition()` → `[definition]`, collected and appended at the END of
     the claim's children (a definition glosses the whole paragraph; in front
     it buries the reasons). `is_definition` is a subject-anchored `means`
     test, NOT a keyword window: subject must parse from `^` (quoted term /
     "the word X" / bare word), ≤3 hedges, then `means|meant`, then a nominal
     complement. Person/demonstrative subjects (he/that/this/God…) and
     propositional complements ("that…", "they are…", "both") are rejected —
     false negatives are fine, false positives are the enemy. Test cases in
     `def_rule.py`; review doc that produced it: `OPUS_HEURISTIC_REVIEW.md`.
  4. anaphoric opener (`ANAPHORA_RE`: this/that/it/they/and…, optional leading
     adverb like "Sometimes") or shared content words (≥4 letters, minus
     stopwords) with previous sentence or claim → `[restatement]`
  5. otherwise → stays in the flow as a plain untagged top-level bullet
     (`provisional=True`, counted in the report as "unplaced"), and **reset
     prev to the claim** so the next sentence doesn't chain under it. No
     bucket section, no why-notes.
- `verify_chapter` — token-multiset comparison. Parse the written `.md` file
  (strip `#` headings and tags), not in-memory data — that tests the real
  artifact. Line format is `- sentence text [tag]` — the tag TRAILS the
  sentence (user preference: marker at the end of the line, not in front).
  This pipeline gets 100% coverage / 0 insertions on all 35 units of the book.
- Flask templates: `chapter.html` (collapsible tree, tag chips, stats bar,
  ←/→ navigation), `source.html`, `index.html`.

**Input-dependent (rewrite for paste):**
- Phases 1–2 (PyMuPDF extraction, running heads, chapter map) mostly drop away.
- BUT: text pasted *from a PDF* still has line-break hyphenation and hard line
  breaks. Keep `stitch_paragraphs` + `should_join` (4-rule dictionary check
  against `/usr/share/dict/words`) as an optional "pasted from PDF" cleanup
  mode; treat blank lines as paragraph boundaries instead of block metadata.
  Plain pasted text: split on blank lines and go straight to the outliner.

Suggested shape: single route, textarea POST → outline page, nothing stored.
Maybe a checkbox: "clean up PDF line breaks".

## Bugs I hit (don't repeat)

1. **Literal control chars in source.** Writing `r"\1"` as a `re.sub`
   replacement through the Write tool embedded a real `\x01` byte in the file —
   invisible in readers, broke the code. Use `lambda m: m.group(1) + MARK`
   replacements or a named constant; never backslash-digit replacements in
   tool-written strings.
2. **De-hyphenation ate the preceding space.** Joined with
   `cur[:m.start(1) - 1]` → `variousbiological`. Correct is
   `cur[:m.start(1)]` (keeps everything up to the word, drops only the `-`).
3. **Wrong depth test.** Used subtree depth (`node_depth(prev)`) where the
   node's depth *in the tree* was needed. Track `prev_depth` as a plain
   variable while building.
4. **Cascade displacement.** First design corroborated attachments in a
   post-pass; when a node failed, its children were displaced with it even
   when independently fine (29% → bucket). Corroborate at attach time instead.
5. **Unplaced flooded at 51%.** Strict word-overlap alone is too weak for
   elaborative prose. Fixed by adding, in order: anaphora rule, colon rule,
   `means`-definition rule, enumeration markers, 4-letter content words.
   Final rate ~26% for C. S. Lewis — acceptable; the spec prefers honest
   orphans over forced placement.
6. **macOS grep has no `-P`.** Use a small Python snippet to hunt control
   characters.
7. **TOC + page offset beats heading detection** for chunking books: read the
   contents page, verify `printed + offset` at ~5 spots across the book, then
   slice chapters by start pages. Skip near-empty pages (book title pages).

## Expectations to set

- Heuristic tagging ≠ understanding. Tags come from opener patterns; they are
  hints. Articles with plainer prose (journalism, essays) should bucket *less*
  than Lewis's sermonic style.
- Uncorroborated sentences stay inline as plain untagged bullets — no Unplaced
  bucket, no why-notes (user preference 2026-07-24: keep the flow, "don't tell
  why"). The honesty signal is the missing tag plus the report's count.
- Verification is cheap and catches every class of bug above; always wire it up.
