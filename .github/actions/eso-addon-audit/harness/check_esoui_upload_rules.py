import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ROOT = audit_env.projects_root()
JUNK = {"luac.out", "desktop.ini", ".DS_Store", "Thumbs.db", "__MACOSX", ".idea", ".vs", ".vscode"}
JUNK_SUFFIXES = (".orig", ".rej", ".bak", ".swp", "~")
FILTERED = {"EVENT_COMBAT_EVENT", "EVENT_EFFECT_CHANGED", "EVENT_INVENTORY_SINGLE_SLOT_UPDATE", "EVENT_POWER_UPDATE"}
REGISTER = re.compile(r"RegisterForEvent\(\s*([^,]+?)\s*,\s*(EVENT_\w+)")
FILTER = re.compile(r"AddFilterForEvent\(\s*([^,]+?)\s*,\s*(EVENT_\w+|\w+)")
SKIP_DIRS = {".git", "tests", "DATA"}

bad, checked = [], 0
for project in audit_env.targets():
    folder = os.path.join(ROOT, project)
    manifest = next((os.path.join(folder, project + ext) for ext in (".addon", ".txt") if os.path.isfile(os.path.join(folder, project + ext))), None)
    if not manifest:
        continue
    checked += 1
    text = open(manifest, encoding="utf-8", errors="replace").read()
    for line in re.findall(r"^## APIVersion:(.*)$", text, re.M):
        if len(line.split()) > 2:
            bad.append("%s: ## APIVersion lists %d values; the game reads only the first two, so the add-on shows as out of date after the second" % (project, len(line.split())))
    for key, value in re.findall(r"^##\s*((?:PC|Console)?(?:Optional)?DependsOn)\s*:(.*)$", text, re.M):
        if re.search(r"[,;]", value):
            bad.append("%s: ## %s separates entries with a comma or semicolon; ESOUI asks for spaces only" % (project, key))
        for entry in value.split():
            optional = "Optional" in key
            if not optional and ">=" not in entry:
                bad.append("%s: ## %s %s has no >= version, so a very old copy of it can load" % (project, key, entry))
    if re.search(r"^##\s+\w+\s+:", text, re.M):
        bad.append("%s: a manifest key has a space before its colon; put the colon right after the key" % project)
    for root, dirs, names in os.walk(folder):
        for name in list(dirs):
            if name in JUNK:
                bad.append("%s: %s is a system or editor folder; remove it before uploading" % (project, os.path.relpath(os.path.join(root, name), ROOT)))
        dirs[:] = [d for d in dirs if d not in JUNK and d != ".git"]
        for name in names:
            if name in JUNK or name.endswith(JUNK_SUFFIXES):
                bad.append("%s: %s is a leftover or system file; remove it before uploading" % (project, os.path.relpath(os.path.join(root, name), ROOT)))
    for path in glob.glob(os.path.join(folder, "**", "*.lua"), recursive=True):
        rel = os.path.relpath(path, ROOT)
        if set(os.path.relpath(path, folder).split(os.sep)[:-1]) & SKIP_DIRS:
            continue
        source = open(path, encoding="utf-8", errors="replace").read()
        if re.search(r"\bLibStub\s*[(:.]", source):
            bad.append("%s: %s calls LibStub, which ESOUI says must not be used since Summerset; use the library's global" % (project, rel))
        if re.search(r"ZO_SavedVars\s*:\s*New\s*\(|NewCharacterNameSettings", source):
            bad.append("%s: %s uses character-name saved variables; use NewCharacterIdSettings (renames keep their data) or NewAccountWide with GetWorldName()" % (project, rel))
        filters = {(ns.strip(), ev) for ns, ev in FILTER.findall(source)}
        wrapped = "AddFilterForEvent(namespace, event" in source
        for namespace, event in REGISTER.findall(source):
            if event in FILTERED and (namespace.strip(), event) not in filters and not wrapped:
                bad.append("%s: %s registers %s without AddFilterForEvent, so it runs Lua for every player and unit; filter it" % (project, rel, event))

if bad:
    print("ESOUI UPLOAD RULES CHECK FAILED: the ESOUI add-on rules (forums t=10790) are not all followed")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("ESOUI UPLOAD RULES CHECK OK: %d add-ons read two API versions at most, list dependencies with spaces and >= versions, ship no system or leftover files, never call LibStub, save by character ID or per server, and filter high-traffic events" % checked)
