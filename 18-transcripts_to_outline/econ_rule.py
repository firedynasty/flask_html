"""Case-set harness for the economy/SA tagger — same style as tag_rule.py.
Cases come from the worked example in OPUS_ECON_REVIEW.md plus the misfires
Opus found on the real WSJ and Seeking Alpha stress-test articles.
Run: python econ_rule.py
"""

from app import econ_tag_sentence

CASES = [
    # --- worked example (Opus: unchanged across v2/v3) ---
    ("Stocks fell on Tuesday as investors weighed fresh inflation data.", "data"),
    ("The Dow Jones Industrial Average dropped 1.2%, while the S&P 500 slid 0.8%.", "price-move"),
    ("The decline came after the Labor Department reported that consumer prices rose 3.4% in April from a year earlier.", "price-move"),
    ("\"The Fed has less room to cut rates this year,\" said Jane Smith, chief economist at Northern Trust.", "source-named"),
    ("Some analysts said the selloff was overdone.", "source-unnamed"),
    ("The report suggests that price pressures remain sticky.", "inference"),
    ("Nvidia shares rose 2.5% after the company forecast quarterly revenue above estimates.", "price-move"),
    ("The chip maker expects sales to reach $28 billion in the current quarter.", "expectation"),
    ("The rally could reverse if inflation fails to cool.", "disconfirmer"),
    ("Despite the broader decline, Treasury yields climbed.", None),
    ("Higher yields led to heavier borrowing costs, which in turn caused companies to pull back.", "cause"),

    # --- temporal `since` killed (3 FPs on the WSJ oil piece) ---
    ("Oil prices are at their highest since May.", None),
    ("The contract has risen since January 2025.", None),
    ("Prices have climbed since fighting began.", None),

    # --- disconfirmer tightened (thesis words, not disconfirmers) ---
    ("A threshold that threatens to bedevil the economy.", None),

    # --- source attribution (v3: pronoun-guarded reporting verbs) ---
    ("Prices at the pump averaged $3.90 a gallon, according to AAA.", "source-named"),
    ("BLS reported that payrolls rose last month.", "source-named"),
    ("The company reported quarterly revenue above estimates.", "source-named"),
    ("It reported $724.8M in net debt last quarter.", None),
    ("The U.S. announced new tariffs on imports.", None),

    # --- tense-flexible inference ---
    ("The tool indicated a recession is coming.", "inference"),
    ("The moves show investors are concerned.", "inference"),

    # --- SA house style: letter grades ---
    ("The stock scores poorly on valuation, with a grade of D-.", "inference"),

    # --- modal speculation (SA genre signal; month "May" must not fire) ---
    ("The Fed might comment on rates next week.", "speculation"),
    ("An interest rate hold might send the stock lower.", "speculation"),
    ("These firms would need to raise capital.", "speculation"),

    # --- move-verb additions (magnitude still required) ---
    ("Yields shot up 25 basis points after the report.", "price-move"),
    ("Shares were up 3.1% in premarket trading.", "price-move"),
    ("Crude topped $80 a barrel on Tuesday.", "price-move"),
]


def main():
    fails = 0
    for sent, want in CASES:
        got = econ_tag_sentence(sent)
        ok = got == want
        fails += not ok
        print(f"{'ok ' if ok else 'FAIL'} want={want!s:16} got={got!s:16} {sent[:72]}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} pass")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
