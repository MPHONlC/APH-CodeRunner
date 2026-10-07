import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ESOUI = os.path.join(audit_env.latest_esoui(audit_env.workspace_root()), "esoui")
if not os.path.isdir(ESOUI):
    ESOUI = audit_env.latest_esoui(audit_env.workspace_root())
DEFINED = set()
for folder, _, names in os.walk(ESOUI):
    for name in names:
        if name.endswith(".xml"):
            text = open(os.path.join(folder, name), encoding="utf-8", errors="replace").read()
            DEFINED.update(re.findall(r'<Font name="(ZoFont\w+)"', text))
if not DEFINED:
    print("FONT NAMES CHECK SKIPPED: no esoui source found to read the game's font list from")
    sys.exit(0)

USE = re.compile(r'"(ZoFont\w+)"(?!\s*\.\.)')
ROOT = audit_env.projects_root()
bad = []
for project in sorted(os.listdir(ROOT)):
    if audit_env.only_targets() and project not in audit_env.targets():
        continue
    for folder, dirs, names in os.walk(os.path.join(ROOT, project)):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in names:
            if not name.endswith((".lua", ".xml")):
                continue
            path = os.path.join(folder, name)
            for number, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
                for font in USE.findall(line):
                    if font not in DEFINED:
                        bad.append("%s:%d  %s" % (path, number, font))

if bad:
    print("FONT NAMES CHECK FAILED: these fonts do not exist in the game, so SetFont falls back to a default; use a real ZoFont name or a font string such as \"$(BOLD_FONT)|11|soft-shadow-thin\"")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("FONT NAMES CHECK OK: every ZoFont name used exists in the game (%d defined)" % len(DEFINED))
