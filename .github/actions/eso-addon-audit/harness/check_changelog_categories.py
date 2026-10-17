import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ROOT = audit_env.projects_root()
DOCS = audit_env.docs_root()
DOC_NAMES = {"PermMemento": "PermanentMemento"}
DEFAULT_LIBRARIES = "LibAPH,LibAddonMenu,LibHarvensAddonSettings"
ENTRY_START = '[b][COLOR="Orange"]Version '
FIRST_RELEASE = {"Initial public release.", "Initial public release"}


def docs_dir(project):
    for path in (os.path.join(DOCS, DOC_NAMES.get(project, project)), os.path.join(DOCS, project), os.path.join(ROOT, project)):
        if os.path.isfile(os.path.join(path, "CHANGELOG_BBCODE.txt")):
            return path
    return None


def load_generator(docs):
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (os.path.join(audit_env.workspace_root(), "..", "Github-Actions", "markdown-check"),
                   os.path.join(docs, ".github", "actions", "markdown-check"),
                   os.path.join(here, "..", "..", "markdown-check")):
        if os.path.isfile(os.path.join(folder, "generate_changelog.py")):
            sys.path.insert(0, os.path.abspath(folder))
            import generate_changelog
            sys.path.pop(0)
            return generate_changelog
    return None


def libraries_for(docs):
    path = os.path.join(docs, ".github", "workflows", "markdown-check.yml")
    if os.path.isfile(path):
        m = re.search(r"^\s*libraries:\s*'([^']*)'", open(path, encoding="utf-8").read(), re.M)
        if m:
            return [x.strip() for x in m.group(1).split(",") if x.strip()]
    return DEFAULT_LIBRARIES.split(",")


def top_bbcode(text):
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(ENTRY_START)]
    if not starts:
        return ""
    end = starts[1] if len(starts) > 1 else len(lines)
    return "".join(lines[starts[0]:end]).rstrip("\n") + "\n"


bad, checked, generator = [], 0, None
for project in audit_env.targets():
    md_path = os.path.join(ROOT, project, "CHANGELOG.md")
    docs = docs_dir(project)
    if not os.path.isfile(md_path) or not docs:
        continue
    md = open(md_path, encoding="utf-8").read()
    head = re.search(r"^Version:\s*(\S+)", md, re.M)
    if not head:
        continue
    version = head.group(1)
    checked += 1
    generator = generator or load_generator(docs)
    if generator is None:
        print("CHANGELOG CATEGORIES CHECK OK: generate_changelog.py is not in this checkout, nothing to compare")
        sys.exit(0)
    parsed = generator.parse_changelog_md(md, version)
    if parsed is None:
        bad.append("%s: CHANGELOG.md's newest entry %s could not be read" % (project, version))
        continue
    date, sections = parsed
    bullets = [b for _, bs in sections for b in bs]
    first_release = len(bullets) == 1 and bullets[0] in FIRST_RELEASE
    if not first_release:
        for name, bs in sections:
            if not name and bs:
                bad.append("%s: CHANGELOG.md %s has %d bullet(s) outside a category; put every bullet under a category line such as Technical Style & Logic, Settings Menu or Slash Commands" % (project, version, len(bs)))
    libraries = libraries_for(docs)
    terms = generator.load_terms([], os.path.join(docs, ".github", "changelog-highlight-terms.txt"))
    wanted = {
        "CHANGELOG_BBCODE.txt": generator.esoui_ascii(generator.format_bbcode(version, date, sections, libraries, terms)),
        "CHANGELOG_GFM.txt": generator.esoui_ascii(generator.format_github(version, date, sections, libraries, terms)),
        "CHANGELOG_COMMONMARK.txt": generator.esoui_ascii(generator.format_bethesda(version, date, sections)),
    }
    for name, entry in wanted.items():
        path = os.path.join(docs, name)
        if not os.path.isfile(path):
            bad.append("%s: %s is missing" % (project, name))
            continue
        have = open(path, encoding="utf-8").read()
        if name == "CHANGELOG_BBCODE.txt":
            have = top_bbcode(have)
        if have.rstrip("\n") != entry.rstrip("\n"):
            bad.append("%s: the newest entry in %s is not what generate_changelog.py makes from CHANGELOG.md %s (hand-edited, missing colors or categories, or stale); regenerate it" % (project, name, version))

if bad:
    print("CHANGELOG CATEGORIES CHECK FAILED: every changelog entry groups its bullets under categories, and the BBCode, GitHub and Bethesda files carry exactly the generator's output (colors in BBCode only)")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("CHANGELOG CATEGORIES CHECK OK: %d projects group their newest changelog entry under categories, and all three generated files match the generator (colors in BBCode only)" % checked)
