# -*- coding: utf-8 -*-
"""
generate_schedule.py

Rerun this ANY TIME you add or change a puzzle's date, solution, or
difficulty in puzzle_bank.xlsx.

HOW SCHEDULING WORKS NOW:
The Puzzle_Date column is the single source of truth for which day a
puzzle runs on - just type the real date directly into that column for
any row. Assign_Puzzle_Difficulty still determines the tier (easy/
medium/hard), same thresholds as before, but no longer has any effect
on which day something lands on - it's purely a difficulty helper now.

A row is included in the live schedule if and only if it has ALL of:
  - a Puzzle_Date filled in
  - a Solution filled in
  - an Assign_Puzzle_Difficulty that falls into a valid tier (<=5)

This script reads every such row, groups them by (date, tier), and
writes:
  1. ../data/puzzles.js - the day-by-day schedule the LIVE GAME uses
                          (start/final words only - never includes
                          solutions, so today's and future puzzles are
                          never exposed).
  2. ../data/hints.js   - powers the in-game hint button AND the
                          "Yesterday's Solutions" / "Past Puzzles"
                          pages. Covers every dated puzzle regardless
                          of whether it's in the past, today, or the
                          future, so those pages can always correctly
                          find whatever date they're looking for on
                          their own, computed client-side, without
                          ever depending on exactly when this script
                          was last run.

HOW TO USE:
1. In puzzle_bank.xlsx, fill in a real date in the Puzzle_Date column
   for any puzzle you want live on that day (see the "Solution" column
   too - comma-separated words, e.g.
   "a,at,tan,rant,train,strain,retains,strainer,restraint").
2. Run:  python3 generate_schedule.py
3. This overwrites ../data/puzzles.js and ../data/hints.js, and bumps
   the cache-busting version numbers in index.html, solutions.html,
   and past-puzzles.html.
4. Commit + push the updated files to GitHub.

Requires: pip install pandas openpyxl
"""

import pandas as pd
from datetime import date
import json
import os
import re
import time

# ---------------- SETTINGS YOU CAN EDIT ----------------
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "puzzle_bank.xlsx")
PUZZLES_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "puzzles.js")
HINTS_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "hints.js")
INDEX_HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "index.html")
SOLUTIONS_HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "solutions.html")
PAST_PUZZLES_HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "past-puzzles.html")
# ---------------------------------------------------------


def compute_tier(apd):
    if apd is None or (isinstance(apd, float) and pd.isna(apd)):
        return None
    try:
        apd = float(apd)
    except (TypeError, ValueError):
        return None
    if apd < 1.25:
        return "easy"
    if apd <= 2.8:
        return "medium"
    if apd <= 5:
        return "hard"
    return None


def load_dated_puzzles():
    """Reads every row with a real Puzzle_Date, a Solution, and a valid
    tier. Returns {date_str: {tier: {"start", "final", "solution"}}},
    and separately warns about any (date, tier) collisions - two
    different puzzles accidentally assigned to the same day and tier -
    since that's the kind of mistake this format makes easy to catch
    early rather than silently picking one."""
    df = pd.read_excel(EXCEL_PATH, dtype=str)
    schedule = {}
    seen_slots = {}  # (date_str, tier) -> (start, final) already placed there

    for _, row in df.iterrows():
        raw_date = row.get("Puzzle_Date")
        solution_raw = row.get("Solution")
        if pd.isna(raw_date) or pd.isna(solution_raw) or not str(solution_raw).strip():
            continue

        try:
            date_str = pd.to_datetime(raw_date).date().isoformat()
        except (ValueError, TypeError):
            print(f"WARNING: could not parse Puzzle_Date '{raw_date}' - skipping this row.")
            continue

        apd = row.get("Assign_Puzzle_Difficulty")
        tier = compute_tier(apd)
        if tier is None:
            print(f"WARNING: row dated {date_str} has no valid difficulty "
                  f"(Assign_Puzzle_Difficulty='{apd}') - skipping, won't be scheduled.")
            continue

        solution = [w.strip().lower() for w in str(solution_raw).split(",") if w.strip()]
        start = solution[0]
        final = solution[-1]

        slot_key = (date_str, tier)
        if slot_key in seen_slots:
            prev_start, prev_final = seen_slots[slot_key]
            print(f"WARNING: {date_str} {tier} has MORE THAN ONE puzzle assigned - "
                  f"'{prev_start}->{prev_final}' AND '{start}->{final}'. "
                  f"Keeping the first one found; fix the duplicate date in the spreadsheet.")
            continue
        seen_slots[slot_key] = (start, final)

        schedule.setdefault(date_str, {})[tier] = {
            "start": start,
            "final": final,
            "solution": solution,
        }

    return schedule


def write_puzzles_js(schedule):
    """start/final only - solutions are never included here, so today's
    and future puzzles can never be spoiled by inspecting this file."""
    result = {}
    for date_str, tiers in schedule.items():
        result[date_str] = {
            tier: {"start": p["start"], "final": p["final"]}
            for tier, p in tiers.items()
        }
    with open(PUZZLES_OUTPUT_PATH, "w") as f:
        f.write("// AUTO-GENERATED by scripts/generate_schedule.py - do not hand-edit\n")
        f.write("const PUZZLE_SCHEDULE = ")
        f.write(json.dumps(dict(sorted(result.items())), indent=2))
        f.write(";\n")
    print(f"Wrote {len(result)} day(s) of puzzles to {PUZZLES_OUTPUT_PATH}")


def write_hints_js(schedule):
    """Full solutions, covering every dated puzzle (past, today, and
    future) - same file already used by the in-game hint button, the
    Yesterday's Solutions page, and the Past Puzzles page. Those pages
    compute which date they need client-side and look it up here
    directly, so they're never dependent on when this script last ran."""
    with open(HINTS_OUTPUT_PATH, "w") as f:
        f.write("// AUTO-GENERATED by scripts/generate_schedule.py - do not hand-edit\n")
        f.write("// Powers the in-game hint button, Yesterday's Solutions, and Past\n")
        f.write("// Puzzles. Covers every dated puzzle - not a bigger exposure than\n")
        f.write("// the live game already has.\n")
        f.write("const HINTS_SCHEDULE = ")
        f.write(json.dumps(dict(sorted(schedule.items())), indent=2))
        f.write(";\n")
    print(f"Wrote hint data for {len(schedule)} day(s) to {HINTS_OUTPUT_PATH}")


def bump_cache_version_in(path, script_filename):
    """Force browsers to fetch the freshly generated file instead of a
    cached copy, by rewriting the ?v= number in the given HTML file."""
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        html = f.read()
    new_version = int(time.time())
    pattern = rf'({re.escape(script_filename)}\?v=)\d+'
    html, count = re.subn(pattern, rf'\g<1>{new_version}', html)
    if count == 0:
        print(f"NOTE: no {script_filename}?v= tag found in {path} to bump "
              f"(fine if that file doesn't reference it).")
        return
    with open(path, "w") as f:
        f.write(html)
    print(f"Bumped cache-busting version for {script_filename} in {path} to {new_version}")


def main():
    schedule = load_dated_puzzles()
    print(f"Loaded {len(schedule)} dated day(s) from {EXCEL_PATH}")

    write_puzzles_js(schedule)
    write_hints_js(schedule)

    bump_cache_version_in(INDEX_HTML_PATH, "data/puzzles.js")
    bump_cache_version_in(INDEX_HTML_PATH, "data/hints.js")
    bump_cache_version_in(SOLUTIONS_HTML_PATH, "data/hints.js")
    bump_cache_version_in(PAST_PUZZLES_HTML_PATH, "data/hints.js")


if __name__ == "__main__":
    main()
