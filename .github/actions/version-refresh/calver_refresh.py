import argparse
import os
import re
import subprocess
import sys
import time


def stamp(offset_hours):
    t = time.gmtime(time.time() + offset_hours * 3600)
    version = '%04d.%02d.%02d.%02d.%02d' % (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min)
    addon = '%02d%02d%02d%02d' % (t.tm_year % 100, t.tm_mon, t.tm_mday, t.tm_hour)
    return version, addon


def short_date_hour(version):
    p = version.split('.')
    return '%s%s%s%s' % (p[0][2:], p[1], p[2], p[3])


def read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def manifest_field(text, name):
    m = re.search(r'^## ' + re.escape(name) + r':[ \t]*(\S+)', text, re.M)
    return m.group(1) if m else None


def set_manifest(text, version, addon):
    text = re.sub(r'^(## Version:[ \t]*)\S+', lambda m: m.group(1) + version, text, count=1, flags=re.M)
    text = re.sub(r'^(## AddOnVersion:[ \t]*)\S+', lambda m: m.group(1) + addon, text, count=1, flags=re.M)
    return text


def is_released(tag):
    try:
        out = subprocess.run(['git', 'ls-remote', '--tags', 'origin', tag],
                             capture_output=True, text=True, timeout=60)
        return bool(out.stdout.strip())
    except Exception:
        return False


def top_changelog_version(text):
    m = re.search(r'^Version:[ \t]*(\S+)', text, re.M)
    return m.group(1) if m else None


def restamp_changelog_md(text, old, new, addon):
    header = re.compile(r'^Version:[ \t]*\S+.*$', re.M)
    m = header.search(text)
    if not m:
        return text
    return text[:m.start()] + 'Version: %s (%s)' % (new, addon) + text[m.end():]


def mdy(version):
    p = version.split('.')
    return '%s/%s/%s' % (p[1], p[2], p[0])


def iso(version):
    p = version.split('.')
    return '%s-%s-%s' % (p[0], p[1], p[2])


def restamp_generated(text, old, new):
    changed = text
    patterns = [
        (r'^(\[b\]\[COLOR="Orange"\]Version )([^\s\[]+)(.*?\()(\d{2}/\d{2}/\d{4})(\))',
         lambda m: m.group(1) + new + m.group(3) + mdy(new) + m.group(5)),
        (r'^(### Version )(\S+)( <sub>\*\()(\d{2}/\d{2}/\d{4})(\)\*</sub>)',
         lambda m: m.group(1) + new + m.group(3) + mdy(new) + m.group(5)),
        (r'^(# VERSION )(\S+)( \()(\d{4}-\d{2}-\d{2})(\))',
         lambda m: m.group(1) + new + m.group(3) + iso(new) + m.group(5)),
    ]
    for pat, repl in patterns:
        m = re.search(pat, changed, re.M)
        if m and m.group(2) == old:
            changed = changed[:m.start()] + repl(m) + changed[m.end():]
            break
    return changed


def sync_file(spec, new):
    path, _, pattern = spec.partition('::')
    path = path.strip()
    if not path or not pattern or not os.path.exists(path):
        return False, path
    text = read(path)
    rx = re.compile(pattern, re.M)
    m = rx.search(text)
    if not m or m.lastindex is None or m.lastindex < 3:
        return False, path
    if m.group(2) == new:
        return False, path
    text = text[:m.start(2)] + new + text[m.end(2):]
    write(path, text)
    return True, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest-file', required=True)
    ap.add_argument('--utc-offset', type=float, default=8.0)
    ap.add_argument('--changelog-md', default='')
    ap.add_argument('--generated-changelog', action='append', default=[])
    ap.add_argument('--readme', default='')
    ap.add_argument('--sync', action='append', default=[])
    ap.add_argument('--tag-prefix', default='Version-')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    manifest = read(args.manifest_file)
    old_version = manifest_field(manifest, 'Version')
    old_addon = manifest_field(manifest, 'AddOnVersion')
    if not old_version or not old_addon:
        print("::error::manifest needs both '## Version:' and '## AddOnVersion:' fields")
        sys.exit(1)

    changelog = read(args.changelog_md) if args.changelog_md and os.path.exists(args.changelog_md) else None
    top = top_changelog_version(changelog) if changelog else None

    released = is_released(args.tag_prefix + old_version) and not args.force
    if released and (top is None or top == old_version):
        print('Version %s is already released; add a new CHANGELOG.md entry to start the next one.' % old_version)
        emit(False, old_version, old_version, old_addon, old_addon, 'released')
        return

    new_version, new_addon = stamp(args.utc_offset)
    if re.fullmatch(r'\d{4}(\.\d{2}){4}', old_version) and new_version < old_version:
        print('Clock is behind the declared version; leaving it alone.')
        emit(False, old_version, old_version, old_addon, old_addon, 'behind')
        return

    touched = []
    new_manifest = set_manifest(manifest, new_version, new_addon)
    if new_manifest != manifest:
        write(args.manifest_file, new_manifest)
        touched.append(args.manifest_file)

    if changelog is not None:
        out = restamp_changelog_md(changelog, old_version, new_version, short_date_hour(new_version))
        if out != changelog:
            write(args.changelog_md, out)
            touched.append(args.changelog_md)
    for path in args.generated_changelog:
        if os.path.exists(path):
            text = read(path)
            out = restamp_generated(text, top or old_version, new_version)
            if out == text and top != old_version:
                out = restamp_generated(text, old_version, new_version)
            if out != text:
                write(path, out)
                touched.append(path)

    if args.readme and os.path.exists(args.readme):
        text = read(args.readme)
        out = re.sub(r'(!\[[^\]]*\]\(https://img\.shields\.io/badge/version-)([^-]+)(-[^)]*\))',
                     lambda m: m.group(1) + new_version + m.group(3), text, count=1)
        if out != text:
            write(args.readme, out)
            touched.append(args.readme)

    for spec in args.sync:
        did, path = sync_file(spec, new_version)
        if did:
            touched.append(path)

    changed = bool(touched)
    print('Version:      %s -> %s' % (old_version, new_version))
    print('AddOnVersion: %s -> %s' % (old_addon, new_addon))
    print('Files: %s' % ', '.join(touched))
    emit(changed, old_version, new_version, old_addon, new_addon, 'updated' if changed else 'up_to_date', touched)


def emit(changed, ov, nv, oa, na, result, files=()):
    print('changed=%s' % ('true' if changed else 'false'))
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write('changed=%s\nold=%s\nnew=%s\nold_addon=%s\nnew_addon=%s\nresult=%s\nfiles=%s\n'
                    % ('true' if changed else 'false', ov, nv, oa, na, result, ' '.join(files)))


if __name__ == '__main__':
    main()
