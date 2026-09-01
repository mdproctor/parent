"""CI wrapper for doc freshness detection — posts PR comments for candidate-stale sections.

Vendors the core detection logic from soredium/doc-freshness/doc_freshness_check.py.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from doc_freshness_core import parse_anchors, find_anchored_docs, detect_stale


def main():
    import argparse
    parser = argparse.ArgumentParser(description='CI doc freshness check')
    parser.add_argument('--diff', required=True, help='File containing changed file paths')
    parser.add_argument('--docs', required=True, help='Path to docs directory')
    parser.add_argument('--repo', help='Current repo name for cross-repo filtering')
    args = parser.parse_args()

    if not os.path.isfile(args.diff):
        print("No diff file found — skipping.")
        return 0

    with open(args.diff) as f:
        diff_files = [line.strip() for line in f if line.strip()]

    if not diff_files:
        print("No changed files — skipping.")
        return 0

    if not os.path.isdir(args.docs):
        print(f"Docs directory not found: {args.docs} — skipping.")
        return 0

    anchored = find_anchored_docs(args.docs)
    candidates = detect_stale(diff_files, anchored)

    if not candidates:
        print(f"Doc freshness: clean ({len(anchored)} anchored docs checked)")
        return 0

    print(f"Doc freshness: {len(candidates)} candidate-stale section(s) found:\n")
    for c in candidates:
        print(f"  - {c.doc_path}: {c.anchor_type} anchor '{c.anchor_value}'")
        print(f"    changed file: {c.changed_file}")
        print()

    return 1


if __name__ == '__main__':
    sys.exit(main())
