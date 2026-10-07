import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
DATA = os.path.join(audit_env.projects_root(), "APH-OnManager", "DATA")
ITEM = re.compile(r'^\[\*\] (?:\[url="([^"]*)"\])?\[COLOR="#FF69B4"\]([^\[]+)\[/COLOR\](\[/url\])?')
ESOUI = re.compile(r'^https://www\.esoui\.com/downloads/info(\d+)(?:-[^"/]*)?\.html$')

ids = {}
for table in ("KnownLibraries.lua", "KnownAddonVersions.lua"):
    path = os.path.join(DATA, table)
    if not os.path.isfile(path):
        continue
    for line in open(path, encoding="utf-8", errors="replace"):
        cols = line.rstrip("\n").split("\t")
        if len(cols) >= 4 and cols[3].isdigit():
            ids.setdefault(cols[0], cols[3])

bad, checked = [], 0
for path in sorted(glob.glob(os.path.join(DOCS, "*", "README_BBCODE.txt"))):
    rel = os.path.relpath(path, DOCS)
    inside = False
    for number, line in enumerate(open(path, encoding="utf-8", errors="replace").read().split("\n"), 1):
        if line.startswith("[SIZE"):
            inside = "Dependencies:" in line
            continue
        if not inside:
            continue
        m = ITEM.match(line)
        if not m:
            continue
        checked += 1
        url, name = m.group(1), m.group(2).strip()
        want = ids.get(name)
        link = ESOUI.match(url or "")
        if not url or not m.group(3):
            hint = " (info%s)" % want if want else ""
            bad.append("%s:%d  %s has no link; link it to its ESOUI page%s" % (rel, number, name, hint))
        elif not link:
            bad.append("%s:%d  %s links to %s, not an ESOUI download page" % (rel, number, name, url))
        elif want and link.group(1) != want:
            bad.append("%s:%d  %s links to ESOUI info%s, but %s is info%s" % (rel, number, name, link.group(1), name, want))

if bad:
    print("BBCODE DEPENDENCY LINKS CHECK FAILED: every dependency, optional and compatible add-on in README_BBCODE.txt links to its own ESOUI page")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("BBCODE DEPENDENCY LINKS CHECK OK: %d dependency entries link to their own ESOUI pages%s" % (checked, "" if ids else " (APH-OnManager's DATA tables are not in this checkout, so the ids were not compared)"))
