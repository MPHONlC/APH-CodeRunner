import re
import sys
import glob
import argparse
import os

KEY_LINE_RE = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.+?)\s*,?\s*(?:--.*)?$')
PLACEHOLDER_RE = re.compile(r'%[sdg%]')


def extract_keys(text):
    keys = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue
        m = KEY_LINE_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2)
            keys[key] = len(PLACEHOLDER_RE.findall(value))
    return keys


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lang-glob', default='lang/*.lua')
    parser.add_argument('--reference', default='default.lua')
    args = parser.parse_args()

    paths = sorted(glob.glob(args.lang_glob))
    out = ["## Localization completeness check", ""]

    if not paths:
        out.append(f"No files matched `{args.lang_glob}` - nothing to check.")
        print('\n'.join(out))
        return

    ref_path = next((p for p in paths if os.path.basename(p) == args.reference), None)
    if ref_path is None:
        print(f"::error::Reference file '{args.reference}' not found among {paths}")
        sys.exit(1)

    ref_keys = extract_keys(read(ref_path))
    out.append(f"Reference: `{ref_path}` ({len(ref_keys)} keys)")
    out.append("")

    any_problem = False
    for path in paths:
        if path == ref_path:
            continue
        keys = extract_keys(read(path))
        missing = sorted(set(ref_keys) - set(keys))
        extra = sorted(set(keys) - set(ref_keys))
        placeholder_mismatches = sorted(
            k for k in (set(ref_keys) & set(keys))
            if ref_keys[k] != keys[k]
        )

        problems = []
        if missing:
            problems.append(f"missing {len(missing)} key(s): {', '.join(missing)}")
        if extra:
            problems.append(f"{len(extra)} stale/unknown key(s) not in reference: {', '.join(extra)}")
        if placeholder_mismatches:
            problems.append(f"{len(placeholder_mismatches)} key(s) with a different placeholder (%s/%d/%g) count than the reference: {', '.join(placeholder_mismatches)}")

        if problems:
            any_problem = True
            out.append(f"**`{path}`**: {'; '.join(problems)}")
            for p in problems:
                print(f"::error::{path}: {p}")
        else:
            out.append(f"`{path}`: OK ({len(keys)} keys, matches reference)")

    print('\n'.join(out))
    if any_problem:
        sys.exit(1)


if __name__ == '__main__':
    main()
