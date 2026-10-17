import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
for candidate in (os.path.join(os.path.dirname(audit_env.workspace_root()), "Github-Actions", "esoui-safe-text"),
                  os.path.join(HERE, "..", "esoui-safe-text"), os.path.join(HERE, "..", "..", "esoui-safe-text")):
    if os.path.isfile(os.path.join(candidate, "esoui_safe_text.py")):
        sys.path.insert(0, candidate)
        break
import esoui_safe_text

BETHESDA_DESCRIPTION = 10000
DOCS = audit_env.docs_root()
bad, checked = [], 0
for path in sorted(glob.glob(os.path.join(DOCS, "*", "README_COMMONMARK.txt"))):
    project = os.path.basename(os.path.dirname(path))
    if audit_env.only_targets() and project not in audit_env.targets():
        continue
    checked += 1
    text = open(path, encoding="utf-8").read()
    size = len(esoui_safe_text.convert(text, "bethesda"))
    if size > BETHESDA_DESCRIPTION:
        bad.append("%s: %d characters as Bethesda gets it; the description box takes %d. Trim it (link the GitHub README for long parts)" % (path, size, BETHESDA_DESCRIPTION))

if bad:
    print("PLATFORM LIMITS CHECK FAILED: README_COMMONMARK.txt is the Bethesda description and must fit its limit")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("PLATFORM LIMITS CHECK OK: all %d Bethesda descriptions fit in %d characters" % (checked, BETHESDA_DESCRIPTION))
