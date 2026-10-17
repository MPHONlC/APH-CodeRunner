import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

CALL = re.compile(r"CreateStatusLine\s*\(")
STACK = re.compile(r"stack\s*=\s*\"compass\"")
LIBRARY = "LibAPH"
CALL_SPAN = 800


def CallText(code, start):
    depth, at = 0, code.index("(", start)
    for index in range(at, min(len(code), at + CALL_SPAN)):
        if code[index] == "(":
            depth += 1
        elif code[index] == ")":
            depth -= 1
            if depth == 0:
                return code[at:index + 1]
    return code[at:at + CALL_SPAN]


ROOT = audit_env.projects_root()
bad = []
checked = 0
library_ok = None
for project in sorted(os.listdir(ROOT)):
    if audit_env.only_targets() and project not in audit_env.targets():
        continue
    folder_root = os.path.join(ROOT, project)
    if not os.path.isdir(folder_root):
        continue
    for folder, dirs, names in os.walk(folder_root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in names:
            if not name.endswith(".lua"):
                continue
            path = os.path.join(folder, name)
            text = open(path, encoding="utf-8", errors="replace").read()
            code = "\n".join(line.split("--", 1)[0] for line in text.split("\n"))
            if project == LIBRARY and name == "StatusLine.lua":
                library_ok = "opts.stack" in code and "Restack" in code
                continue
            for match in CALL.finditer(code):
                if "function" in code[max(0, match.start() - 20):match.start()]:
                    continue
                call = CallText(code, match.start())
                if "ZO_CompassFrame" not in call:
                    continue
                checked += 1
                if not STACK.search(call):
                    line = code[:match.start()].count("\n") + 1
                    bad.append("%s:%d  puts a status line under the compass without stack = \"compass\", so it overlaps other add-ons' lines there" % (path, line))

if library_ok is False:
    bad.append("LibAPH/UI/StatusLine.lua: CreateStatusLine no longer stacks lines that share opts.stack")

if bad:
    print("COMPASS STATUS CHECK FAILED: status lines under the compass join the \"compass\" stack (LibAPH.CreateStatusLine opts.stack, opts.order) so several add-ons' lines sit one under another")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("COMPASS STATUS CHECK OK: every status line under the compass stacks with the others (%d checked)" % checked)
