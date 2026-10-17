import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ROOT = audit_env.projects_root()
TYPE_TABLE = re.compile(r'type\((\w+)\)\s*[~=]=\s*"table"')
CONTROL_METHODS = ("SetHandler", "GetHandler", "IsHidden", "SetHidden", "IsControlHidden", "GetOwningWindow", "GetParent",
                   "GetDrawLevel", "GetDrawTier", "GetDrawLayer", "SetAnchor", "ClearAnchors", "GetNamedChild", "SetMouseEnabled")
NEAR = 8

bad, checked = [], 0
for project in audit_env.targets():
    for path in sorted(glob.glob(os.path.join(ROOT, project, "**", "*.lua"), recursive=True)):
        if "/tests/" in path.replace(os.sep, "/"):
            continue
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        checked += 1
        for index, line in enumerate(lines):
            if "userdata" in line:
                continue
            for name in TYPE_TABLE.findall(line):
                use = re.compile(r'\b%s\s*[:.]\s*(%s)\b' % (re.escape(name), "|".join(CONTROL_METHODS)))
                window = "\n".join(lines[max(0, index - NEAR):index + NEAR + 1])
                if use.search(window):
                    bad.append("%s:%d: type(%s) is checked against \"table\", but %s is used as a control nearby; game controls are userdata, so this skips every one of them in game (accept \"userdata\" too)"
                               % (os.path.relpath(path, ROOT), index + 1, name, name))

if bad:
    print("CONTROL USERDATA CHECK FAILED: a control is expected to be a Lua table, which only the test harness gives")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("CONTROL USERDATA CHECK OK: no control in %d Lua files is required to be a Lua table" % checked)
