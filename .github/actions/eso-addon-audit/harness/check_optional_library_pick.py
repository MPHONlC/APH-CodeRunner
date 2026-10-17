import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ROOT = audit_env.projects_root()
GLOBAL_NAMES = {"LibAddonMenu-2.0": "LibAddonMenu2"}
OPTIONAL = re.compile(r"^## OptionalDependsOn:(.*)$", re.M)

bad, checked = [], 0
for project in audit_env.targets():
    folder = os.path.join(ROOT, project)
    manifest = next((os.path.join(folder, project + ext) for ext in (".addon", ".txt") if os.path.isfile(os.path.join(folder, project + ext))), None)
    if not manifest:
        continue
    text = open(manifest, encoding="utf-8", errors="replace").read()
    libraries = []
    for line in OPTIONAL.findall(text):
        libraries += [item.split(">=")[0] for item in line.split()]
    if not libraries:
        continue
    names = sorted({GLOBAL_NAMES.get(name, name) for name in libraries}, key=len, reverse=True)
    middle = "|".join(re.escape(name) for name in names)
    trap = re.compile(r"\band\s+(?:_G\[[\"'](?:%s)[\"']\]|(?:%s))(?:\.\w+)*\s+or\b" % (middle, middle))
    for path in sorted(glob.glob(os.path.join(folder, "**", "*.lua"), recursive=True)):
        checked += 1
        rel = os.path.relpath(path, ROOT)
        for number, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            if trap.search(line):
                bad.append("%s:%d  %s" % (rel, number, line.strip()[:140]))

if bad:
    print("OPTIONAL LIBRARY PICK CHECK FAILED: 'x and OptionalLibrary or y' falls through to y when that library is off (One APH a Time built its console panel with LibAddonMenu this way); pick with an if")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("OPTIONAL LIBRARY PICK CHECK OK: no 'and <optional library> or' picks in %d Lua files" % checked)
