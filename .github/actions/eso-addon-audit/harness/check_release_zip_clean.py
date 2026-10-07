import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
BUILD = re.compile(r"rsync\s[^\n]*--exclude-from=\.build-ignore[^\n]*")

bad = []
for ignore in sorted(glob.glob(os.path.join(DOCS, "*", ".build-ignore"))):
    lines = open(ignore, encoding="utf-8", errors="replace").read().splitlines()
    for pattern in (".*", "__*"):
        if pattern not in lines:
            bad.append("%s: missing the line %s" % (os.path.relpath(ignore, DOCS), pattern))
for path in sorted(glob.glob(os.path.join(DOCS, "*", ".github", "workflows", "*.yml"))):
    text = open(path, encoding="utf-8", errors="replace").read()
    for m in BUILD.finditer(text):
        if "--exclude='.*'" not in m.group(0) or "--exclude='__*'" not in m.group(0):
            bad.append("%s:%d: the zip build does not add --exclude='.*' --exclude='__*'" % (os.path.relpath(path, DOCS), text[:m.start()].count("\n") + 1))

if bad:
    print("RELEASE ZIP CLEAN CHECK FAILED: release zips never carry hidden files (.gitignore, .luacheckrc, ...) or __ folders (__pycache__, __MACOSX)")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("RELEASE ZIP CLEAN CHECK OK: every .build-ignore and zip build leaves out files starting with . or __")
