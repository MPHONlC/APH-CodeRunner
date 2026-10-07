import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

CALVER = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}\.\d{2}$")

ROOT = audit_env.projects_root()
data = os.path.join(ROOT, "APH-OnManager", "DATA")
versions_path = os.path.join(data, "KnownAddonVersions.lua")
categories_path = os.path.join(data, "SuggestedCategories.lua")
if not (os.path.isfile(versions_path) and os.path.isfile(categories_path)):
    print("AOM KNOWN ROWS CHECK OK: APH-OnManager's DATA tables are not in this checkout, nothing to compare")
    sys.exit(0)

versions = {}
for path in (versions_path, os.path.join(data, "KnownLibraries.lua")):
    if not os.path.isfile(path):
        continue
    for line in open(path, encoding="utf-8"):
        cols = line.rstrip("\n").split("\t")
        if len(cols) >= 3:
            versions[cols[0]] = cols
categories = set(re.findall(r'^\t\["([^"]+)"\]\s*=', open(categories_path, encoding="utf-8").read(), re.M))

bad, checked = [], 0
for project in sorted(os.listdir(ROOT)):
    folder = os.path.join(ROOT, project)
    manifest = next((os.path.join(folder, project + ext) for ext in (".addon", ".txt") if os.path.isfile(os.path.join(folder, project + ext))), None)
    if not manifest:
        continue
    checked += 1
    text = open(manifest, encoding="utf-8", errors="replace").read()
    is_calver = bool(re.search(r"^## Version: \d{4}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\s*$", text, re.M))
    row = versions.get(project)
    if not row:
        bad.append("%s: no row in APH-OnManager/DATA/KnownAddonVersions.lua or KnownLibraries.lua (the Version and AddOnVersion lines in the Add-Ons list come from it)" % project)
    elif not row[1].strip() or not row[2].strip():
        bad.append("%s: its KnownAddonVersions row has an empty AddOnVersion or Version" % project)
    elif is_calver and not (len(row) > 3 and row[3].strip()) and not CALVER.match(row[2].strip()):
        bad.append("%s: its KnownAddonVersions row shows %r, not a CalVer like its manifest" % (project, row[2]))
    if project not in categories:
        bad.append("%s: no entry in APH-OnManager/DATA/SuggestedCategories.lua, so the Add-Ons list files it under Uncategorized" % project)

if bad:
    print("AOM KNOWN ROWS CHECK FAILED: every add-on project needs a KnownAddonVersions row (CalVer Version + AddOnVersion) and a SuggestedCategories entry")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("AOM KNOWN ROWS CHECK OK: all %d add-on projects have a version row and a category" % checked)
