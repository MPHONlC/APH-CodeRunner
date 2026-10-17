import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HINT_CONTROL = re.compile(r"(CreateTopLevelWindow|CreateControl)\s*\(([^)]*(PadHints|HintBar|HintStrip)[^)]*)\)")
RELATIVE_LEVEL = re.compile(r"SetDrawLevel\s*\([^)]*GetDrawLevel\s*\(")
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
            code = "\n".join(line.split("--", 1)[0] for line in text.split("\n"))
            if project == LIBRARY and name == "KeyHints.lua":
                body = code[code.find("function LibAPH.CreatePadHintBar"):]
                library_ok = ("CreateTopLevelWindow(name)" in body and "DrawAbove(box" in body
                              and "SetDrawLevel(level + " in code)
                checked += 1
                continue
            for match in HINT_CONTROL.finditer(code):
                if "CT_LABEL" in match.group(2) or "CT_TEXTURE" in match.group(2):
                    continue
                checked += 1
                line = code[:match.start()].count("\n") + 1
                if match.group(1) == "CreateControl" and "GuiRoot" not in match.group(2):
                    bad.append("%s:%d  builds a controller hint strip as a child of a window, so that window's own text can draw over it; use LibAPH.CreatePadHintBar or a top-level window" % (path, line))
                elif not RELATIVE_LEVEL.search(code):
                    bad.append("%s:%d  builds a controller hint strip without drawing it above its window (SetDrawLevel(window:GetDrawLevel() + n) on the window's layer)" % (path, line))

if library_ok is False:
    bad.append("LibAPH/UI/KeyHints.lua: CreatePadHintBar no longer builds its own top-level window drawn just above the add-on's windows")

if bad:
    print("HINT DRAW ORDER CHECK FAILED: controller hint strips are their own top-level window, drawn just above the add-on's own windows "
          "on the same tier and layer, never as a child that the window's text can cover, and never higher than that")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("HINT DRAW ORDER CHECK OK: every controller hint strip draws just above its add-on's windows (%d checked)" % checked)
