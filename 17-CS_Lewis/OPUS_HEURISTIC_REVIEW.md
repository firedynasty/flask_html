# Review request: improve my outliner's `[definition]` heuristic

Please rewrite one heuristic rule in my outlining tool. Everything you need is
below — the current code, real failure examples, and the constraints.

## What the tool does

I have a local Python tool that turns a book chapter into a **verbatim bullet
outline**. Every sentence of the source appears once, verbatim, tagged with its
logical role and nested under the paragraph's claim:

```
- The claim (first sentence of a paragraph, untagged)
  - [evidence] Because ...
    - [example] For example ...
  - [contrast] But ...
  - [definition] 'Charity' now means ...
```

Sentences that can't be corroborated go to an honest "Unplaced" bucket — I
prefer orphans over forced placement. Tags come from **ordered regexes on the
sentence opener; first match wins**. No LLM at runtime; I want better
heuristics, not a model call.

## The current code

Tag rules (checked in order against the sentence, leading quotes/brackets
stripped, case-insensitive, first match wins):

```python
TAG_RULES = [
    ("concession", r"^(of course|no doubt|doubtless|admittedly|it is true|certainly|to be sure|"
                   r"i know|i admit|you may (say|think|ask|object|feel)|"
                   r"some (people|one|of you) (may |might |will )?(say|think|ask|object|feel)|"
                   r"it may be (said|thought|urged|objected)|we (may|might) be told|"
                   r"it is (often|sometimes) (said|thought))"),
    ("example", r"^(for example|for instance|take |think of |consider |suppose, for example)"),
    ("analogy", r"^(just as|it is as if|as if|imagine|suppose|like |similarly|in the same way)"),
    ("contrast", r"^(but|however|yet\b|nevertheless|none the less|nonetheless|still\b|"
                 r"on the other hand|on the contrary|whereas|while\b|conversely|in contrast|"
                 r"at the same time)"),
    ("evidence", r"^(because|for\b|since\b|after all|the reason|in fact|as a matter of fact|"
                 r"the fact (is|remains)|we know|it is a fact|that is (the reason|why we know))"),
    ("consequence", r"^(therefore|thus|hence|consequently|accordingly|so\b|then\b|it follows|"
                    r"which means|that is why|the result is|and so|in that case)"),
    ("restatement", r"^(that is\b|in other words|i mean|or rather|namely|again\b|"
                    r"to put it (another way|differently)|put another way|"
                    r"(first|firstly|second|secondly|third|thirdly|fourth|fourthly|"
                    r"fifth|finally|lastly|next\b)[,.\)])"),
    ("qualification", r"^(?:now\s+)?(if\b|unless|provided|although|though\b|even if|"
                      r"even though|when\b|whenever|as long as|so long as|"
                      r"while it is true|only\b)"),
    ("definition", r"^(by .{1,40} i mean|what (do )?(we|i) mean|let me (define|explain)|"
                   r"i am using|we mean by|i mean by)"),
]
```

If no opener matches, untagged sentences get one more chance — this is the rule
I want improved:

```python
# A definition signal in the opening stretch of a sentence ("X means ...").
DEF_MID_RE = re.compile(r"^.{0,50}?\bmeans\b", re.I)
```

If `DEF_MID_RE` matches → tag `[definition]`, child of the claim. Otherwise an
anaphora/content-word-overlap check decides `[restatement]` vs. Unplaced.

## The problem: `means` is not always a definition

Real outputs from C. S. Lewis, *Mere Christianity*. For each: source, current
output, what I want instead.

### Example 1 — "means" as a NOUN (false positive)

Source (Preface):

> A talker ought to use variations of voice for emphasis because his medium
> naturally lends itself to that method: but a writer ought not to use italics
> for the same purpose. **He has his own, different, means of bringing out the
> key words and ought to use them.**

Current:

```
- [definition] He has his own, different, means of bringing out the key words and ought to use them
```

Wrong: "means of bringing out" — *means* is a noun ("a method"). The sentence
continues the talker/writer contrast. I'd expect `[contrast]`-ish or
`[restatement]`, never `[definition]`. Signal: `means of` (noun), and no term
being defined.

### Example 2 — "means" as IMPLICATION (false positive)

Source (The Great Sin):

> That raises a terrible question. How is it that people who are quite
> obviously eaten up with Pride can say they believe in God and appear to
> themselves very religious? **I am afraid it means they are worshipping an
> imaginary God.**

Current:

```
- That raises a terrible question
  - [definition] I am afraid it means they are worshipping an imaginary God
```

Wrong: this *answers* the question — it's an inference ("it turns out /
it follows that"), so `[consequence]` or untagged. Signal: what follows
"means" is a full proposition ("they are worshipping…"), not a meaning;
leading filler "I am afraid" precedes the pronoun.

### Example 3 — person as subject (false positive)

Source (Is Christianity Hard or Easy?):

> He says, 'Take up your Cross' … Next minute he says, 'My yoke is easy and
> my burden light'. **He means both.**

Current: `- [definition] He means both`

Wrong: a person *meaning* something isn't a term being defined. Signal:
human subject (he/she/I/they/name), and the object ("both") is not a meaning.

### Example 4 — TRUE positives that must keep working

- > 'Charity' now means simply what used to be called 'alms'—that is, giving
  > to the poor.
- > Dualism means the belief that there are two equal and independent powers…
- > Temperance is, unfortunately, one of those words that has changed its
  > meaning. **It now usually means teetotalism.**
- > What we mean by 'being good' is giving in to those claims.

Signal in true positives: the subject is a **quoted term**, a word-used-as-word
(*Dualism*, *Temperance*), or a pronoun whose antecedent is a term; the object
is a meaning/paraphrase (often followed by "that is…").

### Example 5 — borderline, your call

> God created things which had free will. **That means creatures which can go
> either wrong or right.**

Currently `[definition]`. It glosses "free will" rather than defining a term —
I lean `[restatement]`, but I can be talked out of it.

## What I'm asking for

1. A drop-in replacement for `DEF_MID_RE` (or a small function
   `is_definition(sentence) -> bool`) that separates examples 1–3 from
   example 4. Regex-only is fine; a few lines of Python with 2–3 regexes is
   also fine. Must stay deterministic and offline.
2. If the fix belongs in `TAG_RULES` order instead (e.g. an earlier rule
   catching "means of"), say so and show the revised list.
3. Please respect the constraints: ordered first-match-wins rules; false
   negatives are acceptable (they fall through to the restatement/Unplaced
   logic); false positives are the enemy. When unsure, prefer NOT tagging
   `[definition]`.
4. Bonus: I already see the same class of problem in `[consequence]`'s `so\b`.
   Because consequence is checked *before* qualification/contrast, these real
   outputs are mis-tagged `[consequence]`:
   - "So long as we write and talk about them we are much more likely to
     deter him…" — that's "provided that" → `[qualification]` (your own
     qualification rule lists `so long as`, but it never gets there).
   - "So far from killing the taste of the egg…, it actually brings it out" —
     that's "far from" → `[contrast]`.
   If you see others, flag them — but the definition rule is the priority.
