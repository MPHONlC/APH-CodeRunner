import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
ROOT = re.compile(r"^permissions:", re.M)

bad = []
for path in sorted(glob.glob(os.path.join(DOCS, "**", ".github", "workflows", "*.yml"), recursive=True)):
    text = open(path, encoding="utf-8", errors="replace").read()
    if not ROOT.search(text):
        bad.append(path)

if bad:
    print("WORKFLOW PERMISSIONS CHECK FAILED: every workflow needs a top-level permissions block (contents: read, with write granted only on the jobs that push, release or edit issues), or CodeQL flags it")
    for path in bad:
        print("  " + path)
    sys.exit(1)
print("WORKFLOW PERMISSIONS CHECK OK: every workflow limits its token with a top-level permissions block")
