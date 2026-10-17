import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

SKIP_DIRS = {".git", "__pycache__", "node_modules", "out", "backups", "#Secrets", "esoui-upload-text"}
BINARY = (".xlsx", ".dds", ".png", ".ico", ".zip", ".db", ".jpg", ".jpeg", ".npy", ".gz", ".exe", ".dll",
          ".ttf", ".otf", ".pdf", ".gif", ".webp", ".mp4", ".wav", ".ogg")


def roots():
    workspace = audit_env.workspace_root()
    projects = audit_env.projects_root()
    if audit_env.only_targets():
        found = [os.path.join(projects, name) for name in audit_env.targets()]
    else:
        found = [projects]
    found.append(audit_env.docs_root())
    for extra in ("#Scripts", os.path.join("#Backups", "Harness")):
        found.append(os.path.join(workspace, extra))
    outer = os.path.dirname(workspace)
    for extra in ("Github-Actions", "APH-Search-Guide-Assets"):
        found.append(os.path.join(outer, extra))
    return [r for r in found if os.path.isdir(r)]


def files():
    seen = set()
    for root in roots():
        for folder, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                path = os.path.realpath(os.path.join(folder, name))
                if path in seen or name.lower().endswith(BINARY):
                    continue
                seen.add(path)
                yield os.path.join(folder, name)
    repo_scripts = os.path.join(os.path.dirname(audit_env.workspace_root()), "Github-Repo")
    if os.path.isdir(repo_scripts):
        for name in os.listdir(repo_scripts):
            path = os.path.join(repo_scripts, name)
            if os.path.isfile(path) and not name.lower().endswith(BINARY):
                yield path


ENTITY = re.compile("&" + r"(#[0-9]+|#x[0-9a-fA-F]+|copy|reg|mdash|ndash|trade);")
DOCS = re.compile(r"^(README|CHANGELOG)[^/]*\.(md|txt)$", re.I)


def is_manifest(path):
    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    return ext == ".addon" or (ext == ".txt" and stem == os.path.basename(folder) and os.path.isfile(path)
                                and open(path, "rb").read(200).find(b"## Title:") >= 0)


bad = []
for path in files():
    try:
        data = open(path, "rb").read()
    except OSError:
        continue
    if b"\0" in data:
        continue
    if data.startswith(b"\xef\xbb\xbf"):
        bad.append("%s:1  starts with a byte-order mark; save it as UTF-8 without a BOM" % path)
        continue
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as err:
        bad.append("%s  is not UTF-8 (%s); save it as UTF-8" % (path, err))
        continue
    manifest = is_manifest(path)
    doc = bool(DOCS.match(os.path.basename(path)))
    for number, line in enumerate(text.split("\n"), 1):
        m = ENTITY.search(line)
        if m:
            bad.append("%s:%d  HTML entity %s; write the real character (or a plain - for a dash)" % (path, number, m.group(0)))
            break
        if manifest and any(ord(c) > 127 and not (line.startswith(";") and c in "\u00a9\u00ae") for c in line):
            bad.append("%s:%d  manifests are plain ASCII apart from \u00a9 and \u00ae in ; comment lines (the ZeniMax notice)" % (path, number))
            break
        if doc and "\u2014" in line:
            bad.append("%s:%d  em dash; use a plain - or a colon" % (path, number))
            break

if bad:
    print("TEXT ENCODING CHECK FAILED: local files are UTF-8 without a BOM and hold real characters (\u00a9 \u00ae), never HTML entities; manifests ASCII apart from \u00a9 \u00ae in comment lines; docs use - instead of em dashes")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("TEXT ENCODING CHECK OK: no HTML entities anywhere, manifests ASCII (\u00a9 \u00ae allowed in comments), docs without em dashes, all UTF-8 without a BOM")
