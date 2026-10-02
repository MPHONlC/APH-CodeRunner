import os
import re
import sys
import glob
import argparse

PRIMARY_RE = re.compile(r'SLASH_COMMANDS\s*\[\s*"(/[A-Za-z0-9_]+)"\s*\]\s*=\s*(?!SLASH_COMMANDS\b|nil\b)(?:function|[A-Za-z_])')
ALIAS_RE = re.compile(r'SLASH_COMMANDS\s*\[\s*"(/[A-Za-z0-9_]+)"\s*\]\s*=\s*SLASH_COMMANDS\s*\[')
AUTHOR_GATE_RE = re.compile(r'GetDisplayName\s*\(\s*\)\s*[~=]=\s*"@|\bis_dev\b')
LEAD_GATE_RE = re.compile(r'\bif\s+(?:not\s+)?(?:is_dev\b|GetDisplayName\s*\(\s*\)\s*[~=]=\s*"@)')
LEAD_LINES = 4


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def find_primary_commands(source_glob):
    primary = set()
    aliased = set()
    author_only = set()
    for path in sorted(glob.glob(source_glob, recursive=True)):
        text = read(path)
        if text is None:
            continue
        starts = [m.start() for m in PRIMARY_RE.finditer(text)]
        for index, m in enumerate(PRIMARY_RE.finditer(text)):
            primary.add(m.group(1))
            next_start = starts[index + 1] if index + 1 < len(starts) else len(text)
            lead = '\n'.join(text[:m.start()].splitlines()[-LEAD_LINES:])
            if AUTHOR_GATE_RE.search(text[m.end():next_start]) or LEAD_GATE_RE.search(lead):
                author_only.add(m.group(1))
        for m in ALIAS_RE.finditer(text):
            aliased.add(m.group(1))
    return primary - aliased - author_only, author_only


def parse_doc_files(raw):
    files = []
    for chunk in raw.replace(',', '\n').splitlines():
        chunk = chunk.strip()
        if chunk:
            files.append(chunk)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-glob', default='**/*.lua')
    parser.add_argument('--doc-files', required=True)
    parser.add_argument('--ignore-commands', default='')
    args = parser.parse_args()

    ignored = set(parse_doc_files(args.ignore_commands))
    found, author_only = find_primary_commands(args.source_glob)
    commands = found - ignored
    doc_files = parse_doc_files(args.doc_files)
    out = ["## Slash command documentation check", ""]
    annotations = []

    if author_only:
        out.append(f"Skipped {len(author_only)} author-only command(s) (dev-only, gated on `GetDisplayName()` or `is_dev`, never documented): {', '.join(sorted(author_only))}")
        out.append("")

    if not commands:
        out.append(f"No primary SLASH_COMMANDS registrations found under `{args.source_glob}` - nothing to check.")
        emit(out, annotations)
        return

    out.append(f"Found {len(commands)} primary slash command(s) registered in code: {', '.join(sorted(commands))}")
    if ignored:
        out.append(f"Ignored (author-only or debug, not expected in docs): {', '.join(sorted(ignored))}")
    out.append("")

    any_missing = False
    for path in doc_files:
        text = read(path)
        if text is None:
            out.append(f"**`{path}`**: file not found - skipping.")
            continue
        missing = sorted(c for c in commands if c not in text)
        if missing:
            any_missing = True
            out.append(f"**`{path}`**: missing {len(missing)} command(s): {', '.join(missing)}")
            for c in missing:
                annotations.append(f"::error::{path} does not document slash command {c}")
        else:
            out.append(f"**`{path}`**: all commands documented.")

    emit(out, annotations)
    if any_missing:
        sys.exit(1)


def emit(report_lines, annotations):
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a') as f:
            f.write('\n'.join(report_lines) + '\n')
    else:
        print('\n'.join(report_lines))
    for a in annotations:
        print(a)


if __name__ == '__main__':
    main()
