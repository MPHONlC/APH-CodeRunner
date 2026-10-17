import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

CHOICES = re.compile(r"([A-Za-z_][\w.\[\]\"']*)\s*:\s*UpdateChoices\s*\(")
CLEARED = re.compile(r"([A-Za-z_][\w.\[\]\"']*)\s*:\s*ClearItems\s*\(\s*\)")
RESELECT = "(SetSelectedItemText|SetSelectedItem|SetSelectedItemByEval|SelectItem|SelectItemByIndex|SelectFirstItem|RefreshSelectedItemText|UpdateValue)"
CHOICES_WINDOW = 4
CLEARED_WINDOW = 30

ROOT = audit_env.projects_root()
bad = []
checked = 0
for project in sorted(os.listdir(ROOT)):
    if audit_env.only_targets() and project not in audit_env.targets():
        continue
    for folder, dirs, names in os.walk(os.path.join(ROOT, project)):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in names:
            if not name.endswith(".lua"):
                continue
            path = os.path.join(folder, name)
            lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
            for index, line in enumerate(lines):
                code = line.split("--", 1)[0]
                for match in CHOICES.finditer(code):
                    checked += 1
                    owner = re.escape(match.group(1))
                    after = "\n".join(lines[index + 1:index + 1 + CHOICES_WINDOW])
                    if not re.search(owner + r"\s*:\s*UpdateValue\s*\(", after):
                        bad.append("%s:%d  %s:UpdateChoices(...) is not followed by %s:UpdateValue()" % (path, index + 1, match.group(1), match.group(1)))
                for match in CLEARED.finditer(code):
                    checked += 1
                    owner = re.escape(match.group(1))
                    after = "\n".join(lines[index + 1:index + 1 + CLEARED_WINDOW])
                    if not re.search(owner + r"\s*:\s*" + RESELECT + r"\s*\(", after):
                        bad.append("%s:%d  %s:ClearItems() never sets the shown item again" % (path, index + 1, match.group(1)))

if bad:
    print("DROPDOWN REFRESH CHECK FAILED: rebuilding a dropdown's choices clears the selected item, so the box shows empty text until something selects again. "
          "After control:UpdateChoices(...) call control:UpdateValue(); after combo:ClearItems() set the shown item (SetSelectedItemText, SelectItem, RefreshSelectedItemText, ...)")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("DROPDOWN REFRESH CHECK OK: every rebuilt dropdown selects its current value again (%d rebuilds checked)" % checked)
