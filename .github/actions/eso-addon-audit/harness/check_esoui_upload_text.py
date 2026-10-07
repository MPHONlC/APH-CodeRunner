import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
UPLOAD = re.compile(r'uses:\s*m00nyONE/esoui-upload@')
FILE_INPUT = re.compile(r"(description_file|changelog_file):\s*'([^']*)'")

bad = []
for path in glob.glob(os.path.join(DOCS, "**", ".github", "workflows", "*.yml"), recursive=True):
    text = open(path, encoding="utf-8", errors="replace").read()
    if not UPLOAD.search(text):
        continue
    for m in FILE_INPUT.finditer(text):
        value = m.group(2)
        if value and not value.startswith("esoui-upload-text/"):
            bad.append((path, text[:m.start()].count("\n") + 1, "%s: '%s'" % (m.group(1), value)))
    if any(m.group(2) for m in FILE_INPUT.finditer(text)) and "esoui-safe-text" not in text:
        bad.append((path, 1, "uploads to ESOUI without the esoui-safe-text step"))

BNET = re.compile(r'uses:\s*(m00nyONE/bnet-upload@|\./\.github/actions/eso-bethesda-upload)')
NOTES = re.compile(r"release_notes_file:\s*'([^']*)'")
for path in glob.glob(os.path.join(DOCS, "**", ".github", "workflows", "*.yml"), recursive=True):
    text = open(path, encoding="utf-8", errors="replace").read()
    if not BNET.search(text):
        continue
    for m in NOTES.finditer(text):
        value = m.group(1)
        if value.startswith("latest_changes") or value.startswith("CHANGELOG"):
            bad.append((path, text[:m.start()].count("\n") + 1, "Bethesda notes '%s' must be the esoui-safe-text target: bethesda copy (bethesda-upload-text/...)" % value))

if bad:
    print("UPLOAD TEXT CHECK FAILED: ESOUI reads uploads as ISO-8859-1 and Bethesda wants plain ASCII, so uploads send the esoui-safe-text copies (esoui-upload-text/... and bethesda-upload-text/...), never the UTF-8 source files")
    for path, line, why in bad:
        print("  %s:%d  %s" % (path, line, why))
    sys.exit(1)
print("UPLOAD TEXT CHECK OK: ESOUI uploads send the Latin-1 copies and Bethesda uploads the ASCII release notes")
