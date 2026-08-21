# -*- coding: utf-8 -*-
"""
Scores every puzzle in the bank on two objective, computable signals:

1. TRAPS: how many real words exist that look like a valid first move from
   the starting word (contain all its letters, one longer) but are DEAD
   ENDS - i.e. they don't fit inside the final word's letters at all, so
   anyone who guesses them gets stuck immediately. More traps = trickier.
   (This is exactly the "aunt"/"tuna" phenomenon you described.)

2. BOTTLENECK: at each intermediate length, how many real words exist that
   both (a) contain all the starting word's letters and (b) fit within the
   final word's letters - i.e. how many "could plausibly belong somewhere
   in a valid chain" at that length. The SMALLEST such count across all
   lengths is the puzzle's tightest bottleneck - the step where a solver
   has the fewest real options to stumble onto, whether or not they know
   the game's intended path. Lower = harder.

Neither of these knows anything about how COMMON/obscure a word is to an
average person - that part genuinely still needs your judgment. But traps
and bottlenecks are exactly the two things separating a puzzle that merely
has weird words from one that's actually mentally slippery.
"""
import pandas as pd
from collections import Counter

with open('/home/claude/site/data/words.js') as f:
    content = f.read()
import json, re
raw = re.search(r'"(.*)"', content, re.S).group(1)
raw = raw.encode().decode('unicode_escape')
WORDS = set(w for w in raw.split('\n') if w)

def counter(s):
    return Counter(s)

def is_superset(word, sub_multiset):
    wc = counter(word)
    return all(wc.get(ch,0) >= n for ch, n in sub_multiset.items())

def is_subset_of(word, super_multiset):
    wc = counter(word)
    return all(wc.get(ch,0) <= super_multiset.get(ch,0) for ch in wc)

def score_puzzle(start, final):
    start = start.lower()
    final = final.lower()
    start_counts = counter(start)
    final_counts = counter(final)

    # TRAP count: real words one letter longer than start, containing all
    # of start's letters, that do NOT fit inside final's letters.
    traps = []
    trap_len = len(start) + 1
    for w in WORDS:
        if len(w) != trap_len:
            continue
        if is_superset(w, start_counts) and not is_subset_of(w, final_counts):
            traps.append(w)

    # BOTTLENECK: for each intermediate length, count real words that
    # contain all of start's letters AND fit inside final's letters.
    bottleneck_by_length = {}
    for L in range(len(start)+1, len(final)):
        count = 0
        for w in WORDS:
            if len(w) != L:
                continue
            if is_superset(w, start_counts) and is_subset_of(w, final_counts):
                count += 1
        bottleneck_by_length[L] = count

    min_bottleneck = min(bottleneck_by_length.values()) if bottleneck_by_length else None
    num_steps = len(bottleneck_by_length)

    return {
        'traps': len(traps),
        'trap_words': traps[:8],
        'bottleneck_by_length': bottleneck_by_length,
        'min_bottleneck': min_bottleneck,
        'num_steps': num_steps,
    }

if __name__ == '__main__':
    import sys
    start, final = sys.argv[1], sys.argv[2]
    result = score_puzzle(start, final)
    print(json.dumps(result, indent=2))
