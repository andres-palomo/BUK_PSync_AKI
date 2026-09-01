r"""
Diagnostic: finds CSV rows that don't have the expected number of columns.
This almost always means a cell contains an unescaped newline or an unmatched
quote character, which breaks the CSV structure and shifts every column
after it for that logical row.

Usage:
    python find_ragged_rows.py C:\path\to\clean_data.csv
"""
import csv
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "clean_data.csv"

with open(path, encoding="utf-8-sig", newline="") as fh:
    r = csv.reader(fh)
    header = next(r)
    print(f"header has {len(header)} columns")
    problems = 0
    for i, row in enumerate(r, start=2):
        if len(row) != len(header):
            problems += 1
            print(f"\nline ~{i}: {len(row)} columns (expected {len(header)})")
            print(f"  col A (Umfrage): {row[0]!r}")
            col_b = repr(row[1]) if len(row) > 1 else "MISSING"
            print(f"  col B (id):      {col_b}")
            print(f"  last 3 cells:    {row[-3:]}")
    if not problems:
        print("No ragged rows found - column counts are consistent throughout.")
    else:
        print(f"\n{problems} ragged row(s) found. These are almost certainly caused by an "
              f"unescaped newline or quote inside a free-text answer (like A0, A1a, or a "
              f"'_comment' field) that split one logical row into pieces.")