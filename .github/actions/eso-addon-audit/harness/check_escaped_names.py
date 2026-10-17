import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

PROJECTS = audit_env.projects_root()
NAME_USE = re.compile(r'GetUniqueNameForCharacter\s*\(|SI_UNIT_NAME|selectedCharacterEntry\.name|GetCharacterNameById\s*\(|\$LastCharacterName')
SAFE = re.compile(r'UnescapeName|unescape\(')

bad = []
for proj in audit_env.targets():
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "*.lua"), recursive=True):
        for number, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            if line.lstrip().startswith("--"):
                continue
            if NAME_USE.search(line) and not SAFE.search(line):
                bad.append((path, number, line.strip()))

if bad:
    print("ESCAPED NAME CHECK FAILED: since Update 51 a formatted character name can carry \\' for an apostrophe; pass it through LibAPH.UnescapeName before using it as a key or comparing it")
    for path, number, line in bad:
        print("  %s:%d  %s" % (path, number, line))
    sys.exit(1)
print("ESCAPED NAME CHECK OK: character names reach lookups without the Update 51 backslash")
