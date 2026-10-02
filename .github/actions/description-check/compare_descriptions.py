import os
import re
import sys
import argparse


PLATFORM_ALIASES = {
    'bbcode': ['BBCODE', 'ESOUI'],
    'commonmark': ['COMMONMARK', 'PLAINMARKDOWN', 'BETHESDA'],
}


def resolve_platform_file(explicit, prefix, kind):
    if explicit:
        return explicit
    aliases = PLATFORM_ALIASES[kind]
    try:
        entries = os.listdir('.')
    except OSError:
        entries = []
    for alias in aliases:
        pattern = re.compile(r'^' + re.escape(prefix) + r'_' + re.escape(alias) + r'\.txt$', re.IGNORECASE)
        for entry in entries:
            if pattern.match(entry):
                return entry
    return f'{prefix}_{aliases[0]}.txt'


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def load_ignore_patterns(path):
    text = read(path)
    if text is None:
        return []
    patterns = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        patterns.append(line)
    return patterns


def strip_ignored_lines(text, patterns):
    if not patterns:
        return text
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    kept = [line for line in text.splitlines() if not any(p.search(line) for p in compiled)]
    return '\n'.join(kept)


def terminate_headings(text):
    out = []
    for line in text.splitlines():
        m = re.match(r'^(#{1,6}\s+)(.*)$', line)
        if m and not re.search(r'[.!?:]\s*$', m.group(2)):
            out.append(m.group(1) + m.group(2) + '.')
        else:
            out.append(line)
    return '\n'.join(out)


def flatten_bbcode(text, ignore_patterns):
    t = strip_ignored_lines(text, ignore_patterns)
    t = re.sub(r'\[url="[^"]*"\]', '', t)
    t = re.sub(r'\[/url\]', '', t)
    t = re.sub(r'\[\*\]', '', t)
    t = re.sub(r'\[/?[A-Za-z]+(=[^\]]*)?\]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def flatten_plain_md(text, ignore_patterns):
    t = strip_ignored_lines(text, ignore_patterns)
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = terminate_headings(t)
    t = re.sub(r'^#{1,6}\s*', '', t, flags=re.M)
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    t = re.sub(r'^\s*[-*]\s+', '', t, flags=re.M)
    t = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def flatten_github_md(text, ignore_patterns):
    t = strip_ignored_lines(text, ignore_patterns)
    t = re.sub(r'<div[^>]*>.*?</div>', '', t, flags=re.S)
    t = re.sub(r'</?details>', '', t)
    t = re.sub(r'<summary>.*?</summary>', '', t, flags=re.S)
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', t)
    lines = []
    for line in t.splitlines():
        if re.match(r'^\s*>\s*\[!(NOTE|WARNING|IMPORTANT|TIP|CAUTION)\]\s*$', line, re.IGNORECASE):
            continue
        m = re.match(r'^\s*>\s?(.*)$', line)
        lines.append(m.group(1) if m else line)
    t = '\n'.join(lines)
    out_lines = []
    for line in t.splitlines():
        stripped = line.strip()
        if re.match(r'^\|[\s:|-]+\|$', stripped):
            continue
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            out_lines.append(': '.join(c for c in cells if c))
        else:
            out_lines.append(line)
    t = '\n'.join(out_lines)
    t = re.sub(r'</?kbd>', '', t)
    t = re.sub(r'</?sub>', '', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = terminate_headings(t)
    t = re.sub(r'^#{1,6}\s*', '', t, flags=re.M)
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    t = re.sub(r'^\s*[-*]\s+', '', t, flags=re.M)
    t = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def extract_bbcode_headings(text, ignore_patterns):
    t = strip_ignored_lines(text, ignore_patterns)
    out = []
    for line in t.splitlines():
        s = line.strip()
        if s.startswith('[*]'):
            continue
        if not (re.match(r'^\[SIZE="\d"\]', s) or s.startswith('[b][COLOR') or s.startswith('[b][color=')):
            continue
        flat = re.sub(r'\[url="[^"]*"\]', '', s)
        flat = re.sub(r'\[/url\]', '', flat)
        flat = re.sub(r'\[/?[A-Za-z]+(=[^\]]*)?\]', '', flat)
        flat = flat.strip()
        if flat:
            out.append(flat)
    return out


def extract_md_headings(text, ignore_patterns):
    t = strip_ignored_lines(text, ignore_patterns)
    out = []
    for line in t.splitlines():
        m = re.match(r'^#{1,6}\s+(.*)$', line.strip())
        if not m:
            continue
        h = m.group(1)
        h = re.sub(r'</?sub>', '', h)
        h = re.sub(r'\*([^*]+)\*', r'\1', h)
        h = h.strip()
        if h:
            out.append(h)
    return out


def normalize_heading(h):
    h = re.sub(r'\([^)]*\)', '', h)
    h = h.strip().rstrip(':?.').strip()
    return h.lower()


def check_section_order(name_a, headings_a, name_b, headings_b):
    norm_a = [normalize_heading(h) for h in headings_a]
    norm_b = [normalize_heading(h) for h in headings_b]
    shared = [h for h in norm_a if h in norm_b]
    shared_b_order = [h for h in norm_b if h in norm_a]
    if shared == shared_b_order:
        return None
    return (
        f"**{name_a} vs {name_b}**: shared sections appear in a different order.\n"
        f"  - {name_a} order: {' -> '.join(shared)}\n"
        f"  - {name_b} order: {' -> '.join(shared_b_order)}"
    )


def split_sentences(text):
    if not text:
        return []
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', text)
    return [s.strip() for s in raw if s.strip()]


def extract_manifest_addon_version(text):
    m = re.search(r'^##\s*AddOnVersion:\s*(\d+)', text, re.M)
    return m.group(1) if m else None


def find_addon_version_mentions(text):
    mentions = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if 'addonversion' not in line.lower():
            continue
        for m in re.finditer(r'\d{5,}', line):
            mentions.append((lineno, m.group(0)))
    return mentions


def compare_sentences(name_a, sentences_a, name_b, sentences_b):
    set_b = set(sentences_b)
    set_a = set(sentences_a)
    only_a = [s for s in sentences_a if s not in set_b]
    only_b = [s for s in sentences_b if s not in set_a]
    matched_a = len(sentences_a) - len(only_a)
    out = [f"**{name_a} vs {name_b}**: {matched_a}/{len(sentences_a)} sentences in {name_a} also appear in {name_b}."]
    if only_a or only_b:
        out.append("")
        out.append(f"<details><summary>Sentences that differ ({name_a} vs {name_b})</summary>")
        out.append("")
        if only_a:
            out.append(f"Only in {name_a}:")
            for s in only_a:
                out.append(f"- {s}")
        if only_b:
            out.append(f"Only in {name_b}:")
            for s in only_b:
                out.append(f"- {s}")
        out.append("")
        out.append("</details>")
    out.append("")
    return out, bool(only_a or only_b)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bbcode-file', default='')
    parser.add_argument('--github-file', default='README.md')
    parser.add_argument('--bethesda-file', default='')
    parser.add_argument('--ignore-file', default='.github/description-ignore.txt')
    parser.add_argument('--manifest-file', default='')
    args = parser.parse_args()

    bbcode_path = resolve_platform_file(args.bbcode_file, 'README', 'bbcode')
    github_path = args.github_file
    bethesda_path = resolve_platform_file(args.bethesda_file, 'README', 'commonmark')
    ignore_file = args.ignore_file

    ignore_patterns = load_ignore_patterns(ignore_file)

    bbcode_raw = read(bbcode_path)
    github_raw = read(github_path)
    bethesda_raw = read(bethesda_path)

    out = ["## Description content comparison", ""]
    annotations = []

    addon_version_problems = []
    if args.manifest_file:
        manifest_text = read(args.manifest_file)
        if manifest_text is None:
            addon_version_problems.append(f"manifest ({args.manifest_file}): file not found")
        else:
            real_version = extract_manifest_addon_version(manifest_text)
            if real_version is None:
                addon_version_problems.append(f"manifest ({args.manifest_file}): no '## AddOnVersion:' field found")
            else:
                for label, path, raw in [("BBCode", bbcode_path, bbcode_raw), ("GitHub", github_path, github_raw), ("Bethesda", bethesda_path, bethesda_raw)]:
                    if raw is None:
                        continue
                    for lineno, mentioned in find_addon_version_mentions(raw):
                        if mentioned != real_version:
                            addon_version_problems.append(f"{label} ({path}:{lineno}): mentions AddOnVersion {mentioned}, manifest's real AddOnVersion is {real_version}")

        out.append("## AddOnVersion staleness check")
        out.append("")
        if addon_version_problems:
            for p in addon_version_problems:
                out.append(f"- {p}")
                annotations.append(f"::error::{p}")
        else:
            out.append(f"No stale AddOnVersion mentions found (manifest: {args.manifest_file}).")
        out.append("")

    if ignore_patterns:
        out.append(f"Ignoring {len(ignore_patterns)} known platform-specific pattern(s) from `{ignore_file}` (e.g. donation links, legal boilerplate that isn't meant to appear on every platform).")
        out.append("")

    missing = [name for name, raw in [("BBCode", bbcode_raw), ("GitHub", github_raw), ("Bethesda", bethesda_raw)] if raw is None]
    if missing:
        out.append(f"Could not read: {', '.join(missing)} - skipping comparison.")
        emit(out, annotations)
        if addon_version_problems:
            sys.exit(1)
        return

    bbcode_headings = extract_bbcode_headings(bbcode_raw, ignore_patterns)
    github_headings = extract_md_headings(github_raw, ignore_patterns)
    bethesda_headings = extract_md_headings(bethesda_raw, ignore_patterns)

    out.append("## Section order check")
    out.append("")
    out.append("BBCode is the reference: every other platform's shared sections must appear in the same relative order (formatting/nesting can differ, order can't).")
    out.append("")
    order_problems = []
    for name_a, ha, name_b, hb in [("BBCode", bbcode_headings, "GitHub", github_headings), ("BBCode", bbcode_headings, "Bethesda", bethesda_headings)]:
        problem = check_section_order(name_a, ha, name_b, hb)
        if problem:
            order_problems.append(problem)
    if order_problems:
        for p in order_problems:
            out.append(p)
            annotations.append(f"::error::Section order mismatch - {p.splitlines()[0]}")
    else:
        out.append("No section-order mismatches found.")
    out.append("")

    bbcode = split_sentences(flatten_bbcode(bbcode_raw, ignore_patterns))
    github = split_sentences(flatten_github_md(github_raw, ignore_patterns))
    bethesda = split_sentences(flatten_plain_md(bethesda_raw, ignore_patterns))

    out.append("## Sentence content comparison")
    out.append("")
    out.append("Compared sentence-by-sentence, ignoring formatting - covered by the section-order check above, not by this one.")
    out.append("")

    pairs = [("BBCode", bbcode, "GitHub", github), ("GitHub", github, "Bethesda", bethesda), ("BBCode", bbcode, "Bethesda", bethesda)]
    for name_a, a, name_b, b in pairs:
        section, _ = compare_sentences(name_a, a, name_b, b)
        out.extend(section)

    emit(out, annotations)

    if order_problems:
        sys.exit(1)

    if addon_version_problems:
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
