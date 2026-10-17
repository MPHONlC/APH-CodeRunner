import glob
import os
import re
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ROOT = audit_env.projects_root()
MIN_LENGTH = 12
SETGLOBAL = re.compile(r"SETGLOBAL\s.*; (\w+)$", re.M)
GETGLOBAL = re.compile(r"GETGLOBAL\s.*; (\w+)$", re.M)

game_names = set()
docs = audit_env.docs_file()
if os.path.isfile(docs):
    game_names = set(re.findall(r"^\* (\w+)\(", open(docs, encoding="utf-8", errors="replace").read(), re.M))


def token(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def listing(path):
    done = subprocess.run(["luac5.1", "-l", "-p", path], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


bad, checked = [], 0
for project in audit_env.targets():
    folder = os.path.join(ROOT, project)
    manifest = next((os.path.join(folder, project + ext) for ext in (".addon", ".txt") if os.path.isfile(os.path.join(folder, project + ext))), None)
    if not manifest:
        continue
    text = open(manifest, encoding="utf-8", errors="replace").read()
    is_library = bool(re.search(r"^## IsLibrary:\s*true", text, re.M | re.I))
    saved = []
    for line in re.findall(r"^## SavedVariables\w*:(.*)$", text, re.M):
        saved += line.split()
    own = token(project)
    sets, reads = {}, {}
    for path in glob.glob(os.path.join(folder, "**", "*.lua"), recursive=True):
        out = listing(path)
        rel = os.path.relpath(path, ROOT)
        for name in SETGLOBAL.findall(out):
            sets.setdefault(name, set()).add(rel)
        for name in GETGLOBAL.findall(out):
            reads.setdefault(name, set()).add(rel)
    xml = ""
    for path in glob.glob(os.path.join(folder, "**", "*.xml"), recursive=True):
        xml += open(path, encoding="utf-8", errors="replace").read()
    checked += 1
    for name in sorted(set(sets) | set(saved)):
        if name in game_names:
            continue
        where = ", ".join(sorted(sets.get(name, {os.path.basename(manifest)})))
        if own not in token(name) and len(name) < MIN_LENGTH:
            bad.append("%s: global %s (%s) is too short and not unique; name it after the add-on (e.g. %s) and keep a short local alias" % (project, name, where, project.replace("-", "")))
        if name in saved or is_library:
            continue
        others = (reads.get(name, set()) | sets.get(name, set())) - set(list(sets.get(name, set()))[:1])
        if len(sets.get(name, set())) <= 1 and not others and not re.search(r"\b%s\b" % re.escape(name), xml):
            bad.append("%s: global %s is only used inside %s (no XML, no other file, not a library); make it local" % (project, name, where))

if bad:
    print("GLOBAL NAMES CHECK FAILED: globals are named after the add-on (or at least %d characters) and only exist when another file, XML or other add-ons need them" % MIN_LENGTH)
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("GLOBAL NAMES CHECK OK: every global in %d add-ons is named after its add-on and needed outside its own file" % checked)
