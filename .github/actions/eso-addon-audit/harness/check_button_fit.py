import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

PROJECTS = audit_env.projects_root()
TEXT_BUTTON = re.compile(r'CreateControlFromVirtual\([^)]*"ZO_DefaultButton"\)|CreateKeybindLabelButton\(')
FITTED = re.compile(r'LibAPH\.FitButtonText\(|LibAPH\.FitButtonRow\(|:FitButtons\(\)')
DEFINES = re.compile(r'function LibAPH\.(CreateKeybindLabelButton|FitButtonText|FitButtonRow)\b')

bad = []
for proj in audit_env.targets():
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "*.lua"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        hits = [m for m in TEXT_BUTTON.finditer(text) if not DEFINES.search(text[max(0, m.start() - 40):m.end()])]
        if hits and not FITTED.search(text):
            bad.append((path, text[:hits[0].start()].count("\n") + 1))

if bad:
    print("BUTTON FIT CHECK FAILED: buttons with text must fit their window on small screens; call LibAPH.FitButtonText, LibAPH.FitButtonRow or the window's :FitButtons() in the same file")
    for path, line in bad:
        print("  %s:%d" % (path, line))
    sys.exit(1)
print("BUTTON FIT CHECK OK: every file that makes text buttons fits them to their window")
