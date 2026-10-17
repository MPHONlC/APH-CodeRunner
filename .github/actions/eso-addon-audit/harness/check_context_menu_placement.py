import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

MENU_CONTROL = re.compile(r"LibAPH_ContextMenu\d")
PLACE_CALL = re.compile(r"LibAPH\.PlaceContextMenuBeside\s*\(")
PLACE_GUARD = re.compile(r"LibAPH\.PlaceContextMenuBeside(?!\s*\()")
GUARD_WINDOW = 3
LIBRARY = "LibAPH"

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
            if project == LIBRARY:
                if name == "ContextMenu.lua" and os.path.basename(folder) == "UI":
                    library_ok = ("function LibAPH.PlaceContextMenuBeside" in text
                                  and re.search(r"function LibAPH\.ShowContextMenu\b[\s\S]*?PlaceBeside\(menu, opts\.window or control", text) is not None)
                continue
            lines = text.split("\n")
            for index, line in enumerate(lines):
                code = line.split("--", 1)[0]
                if MENU_CONTROL.search(code):
                    checked += 1
                    bad.append("%s:%d  places LibAPH's menu control itself (%s); call LibAPH.PlaceContextMenuBeside(window, opts) instead"
                               % (path, index + 1, MENU_CONTROL.search(code).group(0)))
                if PLACE_CALL.search(code):
                    checked += 1
                    before = "\n".join(l.split("--", 1)[0] for l in lines[max(index - GUARD_WINDOW, 0):index + 1])
                    if not PLACE_GUARD.search(before):
                        bad.append("%s:%d  LibAPH.PlaceContextMenuBeside is called without checking it exists, so an older LibAPH breaks the menu" % (path, index + 1))

if library_ok is False:
    bad.append("LibAPH/UI/ContextMenu.lua: LibAPH.PlaceContextMenuBeside is missing, or ShowContextMenu no longer places the menu beside its window by default")

if bad:
    print("CONTEXT MENU PLACEMENT CHECK FAILED: every context menu is placed by LibAPH (below the window, else left, above, right, then inside), "
          "never by an add-on's own anchors. Open it with LibAPH.ShowScrollableMenu(window, entries) and, to sit it beside a different window, "
          "call LibAPH.PlaceContextMenuBeside(window, { gap, belowGap, aboveGap }) after checking the function exists")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("CONTEXT MENU PLACEMENT CHECK OK: menus are placed by LibAPH only (%d menu calls checked)" % checked)
