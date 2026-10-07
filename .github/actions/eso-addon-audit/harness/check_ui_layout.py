import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
SKIP = {"#Backups", "#Documentations", "#GITHUB-BACKUP", "#Sources", "OLD-SHIT", "OLD-LTTC"}

SCROLL_LIST = re.compile(r'(?:local\s+)?([A-Za-z_][\w\.]*)\s*=\s*WINDOW_MANAGER:CreateControlFromVirtual\([^)]*"ZO_ScrollList"\)')
COMMIT_ON_HEIGHT = "ZO_ScrollList_AddCommitOnHeightChange(%s)"
STRING_WIDTH = re.compile(r":GetStringWidth\(")
LOOKAHEAD = 5


def projects():
    for entry in sorted(os.listdir(PROJECTS)):
        folder = os.path.join(PROJECTS, entry)
        if entry in SKIP or not os.path.isdir(folder):
            continue
        if audit_env.only_targets() and entry not in audit_env.targets():
            continue
        if glob.glob(os.path.join(folder, "*.addon")) or glob.glob(os.path.join(folder, "*.txt")):
            yield entry


bad = []
checked = 0
for project in projects():
    for path in sorted(glob.glob(os.path.join(PROJECTS, project, "**", "*.lua"), recursive=True)):
        if os.sep + "DATA" + os.sep in path:
            continue
        checked += 1
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
        rel = os.path.relpath(path, PROJECTS)
        for number, line in enumerate(lines, 1):
            match = SCROLL_LIST.search(line)
            if match:
                wanted = COMMIT_ON_HEIGHT % match.group(1)
                if not any(wanted in later for later in lines[number:number + LOOKAHEAD]):
                    bad.append("%s:%d ZO_ScrollList %s has no %s right after it, so a list sized or resized while hidden draws only the rows its old height held"
                               % (rel, number, match.group(1), wanted))
            if STRING_WIDTH.search(line):
                window = "\n".join(lines[number - 1:number - 1 + 3])
                if "GetUIGlobalScale()" not in window:
                    bad.append("%s:%d GetStringWidth is in screen pixels; divide by GetUIGlobalScale() (or use GetTextWidth, which is already UI units)" % (rel, number))

if bad:
    print("UI LAYOUT CHECK FAILED:")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("UI LAYOUT CHECK OK: every ZO_ScrollList re-commits on height change and every GetStringWidth is scaled (%d files)" % checked)
