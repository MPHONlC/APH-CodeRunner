import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
DOCS = audit_env.docs_root()
SKIP = {"#Backups", "#Documentations", "#GITHUB-BACKUP", "#Sources", "OLD-SHIT", "OLD-LTTC"}

LUA_HEADER = re.compile(
    r"\A--\[\[\n"
    r"    Copyright © \d{4}(?:-\d{4})? @APHONlC\. All rights reserved\.\n"
    r"\n"
    r"    No copying, modification, distribution, or sale without prior written permission\.\n"
    r"    AI/ML ingestion and training are strictly prohibited \(TDM opt-out\)\.\n"
    r"\n"
    r"    See LICENSE\.md for full terms and maintenance exceptions\.\n"
    r"\]\]\n")
MANIFEST_LICENSE = "; License: All Rights Reserved. See LICENSE.md for maintenance exceptions & AI opt-out."
COPY_SIGNS = ("\u00a9", "&" + "#169;")
OLD_MARKERS = ("See LICENSE.md and NOTICE.md", "; LICENSE") + tuple("Copyright %s @APHONlC" % sign for sign in COPY_SIGNS)
OLD_ORDER = tuple("Copyright %s %s" % (sign, tail) for sign in COPY_SIGNS for tail in ("@APHONlC", "[COLOR"))
KNOWN_DIRECTIVES = {"Title", "Author", "Version", "AddOnVersion", "APIVersion", "Description", "DependsOn", "OptionalDependsOn", "SavedVariables", "SavedVariablesPerCharacter", "IsLibrary"}
MAX_DIRECTIVE_BYTES = 301
MAX_DESCRIPTION_BYTES = 255
MAX_COMMENT_CHARS = 1024


def projects():
    for entry in sorted(os.listdir(PROJECTS)):
        folder = os.path.join(PROJECTS, entry)
        if entry in SKIP or not os.path.isdir(folder):
            continue
        if audit_env.only_targets() and entry not in audit_env.targets():
            continue
        manifests = glob.glob(os.path.join(folder, "*.addon")) + glob.glob(os.path.join(folder, entry + ".txt"))
        if manifests:
            yield entry, folder, manifests


bad = []
checked = 0
for name, folder, manifests in projects():
    for gone in ("NOTICE.md", "AGENTS.md"):
        if os.path.exists(os.path.join(folder, gone)):
            bad.append("%s/%s still exists; LICENSE.md is the only license file" % (name, gone))
    license_path = os.path.join(folder, "LICENSE.md")
    if not os.path.exists(license_path):
        bad.append("%s has no LICENSE.md" % name)
    elif not open(license_path, encoding="utf-8").read().startswith("# License & Notice\n\nCopyright © "):
        bad.append("%s/LICENSE.md is not the License & Notice text" % name)

    for path in sorted(glob.glob(os.path.join(folder, "**", "*.lua"), recursive=True)):
        checked += 1
        text = open(path, encoding="utf-8").read()
        if not LUA_HEADER.match(text):
            bad.append("%s does not start with the --[[ ]] license block" % os.path.relpath(path, PROJECTS))

    for manifest in manifests:
        rel = os.path.relpath(manifest, PROJECTS)
        raw = open(manifest, "rb").read()
        if raw.startswith(b"\xef\xbb\xbf"):
            bad.append("%s starts with a BOM; manifests must be UTF-8 without BOM" % rel)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append("%s is not UTF-8" % rel)
            continue
        for number, line in enumerate(text.split("\n"), 1):
            if line.startswith("##") and line.split(":", 1)[0][2:].strip() not in KNOWN_DIRECTIVES:
                bad.append("%s:%d unknown directive %s; ESO refuses to load the add-on, use a ; comment" % (rel, number, line.split(":", 1)[0]))
        if MANIFEST_LICENSE not in text.split("\n"):
            bad.append("%s is missing the line: %s" % (rel, MANIFEST_LICENSE))
        else:
            kept = text.rstrip("\n").split("\n")
            if kept[-1] != MANIFEST_LICENSE or len(kept) < 2 or kept[-2] != "":
                bad.append("%s: the ; License line goes last, after the ZeniMax block and one blank line" % rel)
        for number, line in enumerate(text.split("\n"), 1):
            is_comment = line.startswith(";") or (line.startswith("#") and not line.startswith("##"))
            if is_comment and len(line) > MAX_COMMENT_CHARS:
                bad.append("%s:%d comment is %d characters; ESO stops at %d" % (rel, number, len(line), MAX_COMMENT_CHARS))
            if line.startswith("## Description:"):
                value = line[len("## Description:"):].strip().encode("utf-8")
                if len(value) > MAX_DESCRIPTION_BYTES:
                    bad.append("%s:%d Description is %d bytes with its color codes; the game cuts it at %d" % (rel, number, len(value), MAX_DESCRIPTION_BYTES))
            if not is_comment and len(line.encode("utf-8")) > MAX_DIRECTIVE_BYTES:
                bad.append("%s:%d is %d bytes; ESO ignores anything past %d" % (rel, number, len(line.encode("utf-8")), MAX_DIRECTIVE_BYTES))

    for path in glob.glob(os.path.join(folder, "**", "*"), recursive=True):
        if os.path.isfile(path) and path.endswith((".lua", ".addon", ".txt", ".md", ".sh", ".ps1", ".awk", ".xml")):
            text = open(path, encoding="utf-8", errors="replace").read()
            for marker in OLD_MARKERS:
                if marker in text:
                    bad.append("%s still has the old license wording: %s" % (os.path.relpath(path, PROJECTS), marker))

for path in glob.glob(os.path.join(DOCS, "**", "*"), recursive=True):
    if os.path.isfile(path) and path.endswith((".md", ".txt", ".py", ".yml")) and "/.git/" not in path:
        text = open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, PROJECTS)
        if os.path.basename(path) in ("NOTICE.md", "AGENTS.md"):
            bad.append("%s still exists" % rel)
        if "NOTICE.md" in text or any(marker in text for marker in OLD_ORDER):
            bad.append("%s still points at NOTICE.md or uses the old copyright order" % rel)

if bad:
    print("LICENSE FORMAT CHECK FAILED:")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("LICENSE FORMAT CHECK OK: LICENSE.md only, --[[ ]] Lua headers, ; License manifest line, manifest byte limits, Description at most 255 bytes (%d Lua files)" % checked)
