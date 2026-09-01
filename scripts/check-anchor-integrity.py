"""Verify structural anchors resolve in the codebase.

Walks documentation files with YAML frontmatter, extracts anchor class/SPI names,
and verifies each resolves via file path matching. Cross-repo anchors (repo field
doesn't match current repo) are skipped — caught by adversarial check instead.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from doc_freshness_core import find_anchored_docs


def check_class_exists(class_name: str, source_root: str) -> bool:
    """Check if a fully qualified class name resolves to a file in the source tree."""
    simple_name = class_name.rsplit('.', 1)[-1]
    expected_package = class_name.rsplit('.', 1)[0] if '.' in class_name else ''

    for root, _, files in os.walk(source_root):
        if '.git' in root:
            continue
        for fname in files:
            if fname == f'{simple_name}.java' or fname == f'{simple_name}.kt':
                fpath = os.path.join(root, fname)
                with open(fpath, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('package '):
                            pkg = line.replace('package ', '').rstrip(';').strip()
                            if pkg == expected_package:
                                return True
                        if not line or line.startswith('import') or line.startswith('/*') or line.startswith('*') or line.startswith('//'):
                            continue
                        if line.startswith('public') or line.startswith('class') or line.startswith('@'):
                            break
    return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Check anchor integrity')
    parser.add_argument('--docs', required=True, help='Path to docs directory')
    parser.add_argument('--repo', required=True, help='Current repo name')
    parser.add_argument('--source-root', required=True, help='Source tree root')
    args = parser.parse_args()

    if not os.path.isdir(args.docs):
        print(f"Docs directory not found: {args.docs} — skipping.")
        return 0

    anchored = find_anchored_docs(args.docs)
    broken = []

    for doc in anchored:
        repo_name = f'casehub-{args.repo}' if not args.repo.startswith('casehub-') else args.repo
        if doc.repo and doc.repo != repo_name:
            continue

        for anchor_type in ('classes', 'spis'):
            for anchor in doc.anchors.get(anchor_type, []):
                if not check_class_exists(anchor, args.source_root):
                    broken.append({
                        'doc': doc.path,
                        'type': anchor_type,
                        'anchor': anchor,
                    })

    if not broken:
        print(f"Anchor integrity: all anchors resolve ({len(anchored)} docs checked)")
        return 0

    print(f"Anchor integrity: {len(broken)} broken anchor(s):\n")
    for b in broken:
        print(f"  - {b['doc']}: {b['type']} '{b['anchor']}' not found in codebase")
    return 1


if __name__ == '__main__':
    sys.exit(main())
