import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
GITHUB_REF = re.compile(r"https://github\.com/MPHONlC/[A-Za-z0-9_.-]+(?![A-Za-z0-9_.-]*/(issues|releases|wiki|actions|blob/[^)\]\s]*\.(png|jpg|gif)))")
bad = []
for path in sorted(glob.glob(os.path.join(DOCS, "*", "README_BBCODE.txt"))):
    text = open(path, encoding="utf-8").read()
    for m in re.finditer(r"\[LIST\]", text, re.I):
        before = text[:m.start()].upper()
        if before.rfind("[CENTER]") > before.rfind("[/CENTER]"):
            bad.append("%s:%d  [LIST] inside [CENTER]; ESOUI indents list items, so centred lines drift right. Write the items as plain centred lines" % (path, before.count("\n") + 1))
for path in sorted(glob.glob(os.path.join(DOCS, "*", "README*")) + glob.glob(os.path.join(DOCS, "*", "CHANGELOG*"))):
    for number, line in enumerate(open(path, encoding="utf-8"), 1):
        if "shields.io" in line:
            continue
        m = GITHUB_REF.search(line)
        if m:
            bad.append("%s:%d  links %s; reference my projects by their ESOUI page" % (path, number, m.group(0)))

if bad:
    print("DOC LAYOUT CHECK FAILED")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("DOC LAYOUT CHECK OK: no lists inside centred BBCode, project references go to ESOUI")
