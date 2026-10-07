import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
PASTED = re.compile(r"\$\{\{\s*(secrets\.[A-Za-z0-9_]+|inputs\.[A-Za-z0-9_]*(?:pass|token|secret|key|bnet)[A-Za-z0-9_]*)\s*\}\}", re.I)
RUN = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*)$")
OLD_UPLOAD = re.compile(r"uses:\s*m00nyONE/bnet-upload@")


def run_lines(text):
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = RUN.match(lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        if m.group(2).strip() not in ("", "|", ">", "|-", ">-", "|+", ">+"):
            yield i + 1, m.group(2)
            i += 1
            continue
        i += 1
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            yield i + 1, lines[i]
            i += 1


bad = []
files = glob.glob(os.path.join(DOCS, "**", ".github", "workflows", "*.yml"), recursive=True)
files += glob.glob(os.path.join(DOCS, "**", ".github", "actions", "*", "action.yml"), recursive=True)
for path in sorted(files):
    text = open(path, encoding="utf-8", errors="replace").read()
    rel = os.path.relpath(path, DOCS)
    for m in OLD_UPLOAD.finditer(text):
        bad.append("%s:%d  m00nyONE/bnet-upload puts the password into a bash line unquoted (a ';' in it breaks the login and prints part of it); use ./.github/actions/eso-bethesda-upload"
                   % (rel, text[:m.start()].count("\n") + 1))
    for number, line in run_lines(text):
        for m in PASTED.finditer(line):
            bad.append("%s:%d  %s is pasted into a shell script; pass it through env: and read it as a variable" % (rel, number, m.group(1)))

if bad:
    print("SECRETS IN SHELL CHECK FAILED: secrets and credentials reach scripts only through env:, never as ${{ }} text inside run:")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("SECRETS IN SHELL CHECK OK: no secret or credential is pasted into a run: script, and Bethesda uploads use eso-bethesda-upload")
