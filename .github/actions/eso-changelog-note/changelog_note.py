import argparse
import os
import re
import subprocess
import sys
import time

ENTRY_START = '[b][COLOR="Orange"]Version '
VERSION_LINE = re.compile(r'^Version:\s*(\S+)')
FIRST_RELEASE = {'Initial public release.', 'Initial public release'}


def git(*args):
    r = subprocess.run(['git', *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def stamp(offset_hours):
    t = time.gmtime(time.time() + offset_hours * 3600)
    version = '%04d.%02d.%02d.%02d.%02d' % (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min)
    addon = '%02d%02d%02d%02d' % (t.tm_year % 100, t.tm_mon, t.tm_mday, t.tm_hour)
    return version, addon


def latest_tag(prefix):
    out = git('tag', '--list', prefix + '*', '--sort=-creatordate')
    return out.splitlines()[0] if out else None


def is_released(tag):
    out = git('ls-remote', '--tags', 'origin', 'refs/tags/' + tag)
    if out is None:
        out = git('tag', '--list', tag)
    return bool(out)


def api_line(text):
    m = re.search(r'^## APIVersion:[ \t]*(.*?)\s*$', text or '', re.M)
    return m.group(1) if m else None


def wanted(args, last):
    if args.when == 'always':
        return True, 'always added'
    if not last:
        return False, 'no %s* tag yet, so there is no earlier release to compare against' % args.tag_prefix
    if args.when == 'api':
        before = api_line(git('show', '%s:%s' % (last, args.manifest_file)))
        now = api_line(read(args.manifest_file))
        if before == now:
            return False, 'APIVersion %s is the same as in %s' % (now, last)
        return True, 'APIVersion %s in %s, %s now' % (before, last, now)
    r = subprocess.run(['git', 'diff', '--quiet', last, '--', args.data_path])
    if r.returncode == 0:
        return False, '%s is the same as in %s' % (args.data_path, last)
    return True, '%s changed since %s' % (args.data_path, last)


def bounds(lines):
    starts = [i for i, line in enumerate(lines) if VERSION_LINE.match(line)]
    if not starts:
        return None, None
    return starts[0], (starts[1] if len(starts) > 1 else len(lines))


def is_bullet(line):
    return re.match(r'^\s*-\s+', line) is not None


def add_to_pending(lines, start, end, category, bullet):
    body = lines[start:end]
    if any(re.match(r'^\s*-\s+' + re.escape(bullet) + r'\s*$', line) for line in body):
        return False, 'the top entry already has "%s"' % bullet
    bullets = [line for line in body if is_bullet(line)]
    if len(bullets) == 1 and re.sub(r'^\s*-\s+', '', bullets[0]).strip() in FIRST_RELEASE:
        return False, 'the top entry is the first release'
    for i in range(start, end):
        if lines[i].strip() == category and not is_bullet(lines[i]):
            j = i + 1
            while j < end and is_bullet(lines[j]):
                j += 1
            lines.insert(j, '  - ' + bullet)
            return True, 'added under %s in the pending entry' % category
    k = end - 1
    while k > start and not lines[k].strip():
        k -= 1
    lines[k + 1:k + 1] = ['', category, '  - ' + bullet]
    return True, 'added as %s in the pending entry' % category


def bbcode_version(line):
    m = re.match(r'^\[b\]\[COLOR="Orange"\]Version ([^\s\[]+)', line)
    return m.group(1) if m else None


def put_bbcode(path, entry, version):
    existing = read(path) if os.path.exists(path) else ''
    lines = existing.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(ENTRY_START)]
    if not starts:
        write(path, (existing.rstrip('\n') + '\n\n' if existing.strip() else '') + entry)
        return
    first = starts[0]
    head = ''.join(lines[:first])
    if bbcode_version(lines[first]) == version:
        rest = ''.join(lines[starts[1]:]) if len(starts) > 1 else ''
    else:
        rest = ''.join(lines[first:])
    write(path, head + entry + ('\n' + rest if rest else ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bullet', required=True)
    ap.add_argument('--category', required=True)
    ap.add_argument('--when', choices=['api', 'data', 'always'], default='always')
    ap.add_argument('--manifest-file', default='')
    ap.add_argument('--data-path', default='DATA')
    ap.add_argument('--changelog-md', default='CHANGELOG.md')
    ap.add_argument('--bbcode', default='CHANGELOG_BBCODE.txt')
    ap.add_argument('--gfm', default='CHANGELOG_GFM.txt')
    ap.add_argument('--commonmark', default='CHANGELOG_COMMONMARK.txt')
    ap.add_argument('--generator-dir', required=True)
    ap.add_argument('--libraries', default='')
    ap.add_argument('--terms-file', default='')
    ap.add_argument('--tag-prefix', default='Version-')
    ap.add_argument('--utc-offset', type=float, default=8.0)
    args = ap.parse_args()

    if args.when == 'api' and not args.manifest_file:
        print('::error::when: api needs manifest_file')
        sys.exit(1)

    sys.path.insert(0, os.path.abspath(args.generator_dir))
    import generate_changelog as gen

    ok, why = wanted(args, latest_tag(args.tag_prefix))
    if not ok:
        print('Skipped "%s": %s.' % (args.bullet, why))
        emit(False, '')
        return
    print('"%s": %s.' % (args.bullet, why))

    text = read(args.changelog_md)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.replace('\r\n', '\n').split('\n')
    start, end = bounds(lines)
    top = VERSION_LINE.match(lines[start]).group(1) if start is not None else None

    if top and not is_released(args.tag_prefix + top):
        version = top
        changed, how = add_to_pending(lines, start, end, args.category, args.bullet)
    else:
        version, addon = stamp(args.utc_offset)
        block = ['Version: %s (%s)' % (version, addon), '-' * 27, '', args.category, '  - ' + args.bullet, '']
        at = start if start is not None else len(lines)
        lines[at:at] = block
        changed, how = True, 'new entry %s' % version
    print(how)
    if not changed:
        emit(False, version)
        return
    write(args.changelog_md, newline.join(lines))

    parsed = gen.parse_changelog_md(newline.join(lines).replace('\r\n', '\n'), version)
    if parsed is None:
        print('::error::Could not read the %s entry back from %s' % (version, args.changelog_md))
        sys.exit(1)
    date, sections = parsed
    libraries = [x.strip() for x in args.libraries.split(',') if x.strip()]
    terms = gen.load_terms([], args.terms_file or None)
    put_bbcode(args.bbcode, gen.esoui_ascii(gen.format_bbcode(version, date, sections, libraries, terms)), version)
    write(args.gfm, gen.esoui_ascii(gen.format_github(version, date, sections, libraries, terms)))
    write(args.commonmark, gen.esoui_ascii(gen.format_bethesda(version, date, sections)))
    emit(True, version)


def emit(changed, version):
    print('changed=%s' % ('true' if changed else 'false'))
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write('changed=%s\nversion=%s\n' % ('true' if changed else 'false', version))


if __name__ == '__main__':
    main()
