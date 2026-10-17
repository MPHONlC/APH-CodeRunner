import glob
import os
import re
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
KNOWN = audit_env.targets()
SKIP = {"#Backups", "#Documentations", "#GITHUB-BACKUP", "#Sources", "OLD-SHIT", "OLD-LTTC"}


def discover():
    found = []
    for entry in sorted(os.listdir(PROJECTS)):
        folder = os.path.join(PROJECTS, entry)
        if entry in SKIP or not os.path.isdir(folder):
            continue
        if glob.glob(os.path.join(folder, "*.addon")) or (entry in KNOWN and glob.glob(os.path.join(folder, "*.txt"))):
            found.append(entry)
    if audit_env.only_targets():
        found = [name for name in found if name in KNOWN]
    missing = [name for name in KNOWN if name not in found]
    if missing:
        print("LOCAL ORDER CHECK FAILED: expected add-on folders are missing: " + ", ".join(missing))
        sys.exit(1)
    return found


TARGETS = discover()

DECLARE = re.compile(r"^local\s+(?:function\s+([A-Za-z_]\w*)\s*\(.*|([A-Za-z_][\w\s,]*?)\s*(?:=\s*(.*))?)$")
GLOBAL_OP = re.compile(r"\[(\d+)\]\s+(GETGLOBAL|SETGLOBAL)\s+.*;\s+([A-Za-z_]\w*)\s*$")


def file_locals(path):
    found = {}
    for number, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        match = DECLARE.match(line.rstrip())
        if not match:
            continue
        names = [match.group(1)] if match.group(1) else [n.strip() for n in match.group(2).split(",")]
        values = [v.strip() for v in (match.group(3) or "").split(",")]
        for index, name in enumerate(names):
            if not name or name in found:
                continue
            value = values[index] if index < len(values) else ""
            if value == name:
                continue
            found[name] = number
    return found


def global_uses(path):
    listing = subprocess.run(["luac5.1", "-p", "-l", path], capture_output=True, text=True)
    if listing.returncode != 0:
        return None, listing.stderr.strip()
    uses = []
    for line in listing.stdout.splitlines():
        match = GLOBAL_OP.search(line)
        if match:
            uses.append((int(match.group(1)), match.group(2), match.group(3)))
    return uses, None


bad = []
checked = 0
for project in TARGETS:
    for path in sorted(glob.glob(os.path.join(PROJECTS, project, "**", "*.lua"), recursive=True)):
        checked += 1
        declared = file_locals(path)
        uses, err = global_uses(path)
        if err:
            bad.append("%s: luac failed: %s" % (os.path.relpath(path, PROJECTS), err))
            continue
        for line, op, name in uses:
            at = declared.get(name)
            if at is not None and line < at:
                verb = "reads" if op == "GETGLOBAL" else "writes"
                bad.append("%s:%d %s global %s, but the file declares local %s later at line %d"
                           % (os.path.relpath(path, PROJECTS), line, verb, name, name, at))

if bad:
    print("LOCAL ORDER CHECK FAILED: a file-level local is used above its own declaration, so that code sees a global of the same name (usually nil)")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("LOCAL ORDER CHECK OK: no file-level local is used above the line that declares it (%d files in %s)" % (checked, ", ".join(TARGETS)))
