import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
DOCS = audit_env.docs_file()
GLOBALS_DIR = os.path.join(audit_env.esoui_dir(), "esoui")
TARGETS = audit_env.targets()

OPTIONAL_LIBRARY_CALLS = {}

CALL = re.compile(r"(?<![\w.:])((?:Get|Is|Has|Can|Request|Set|Do|Play|Reload|Select|Clear|Add|Show|Update|Anchor|Zo|zo)[A-Za-z0-9_]*)\s*\(")
LOCAL_DEF = re.compile(r"(?:local\s+function\s+|function\s+)([A-Za-z0-9_.:]+)")


def documented_names():
    names = set()
    with open(DOCS, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = re.match(r"\* ([A-Za-z0-9_]+)\(", line.strip())
            if match:
                names.add(match.group(1))
    return names


aliases = {}


def source_names():
    names = set()
    for root, _dirs, files in os.walk(GLOBALS_DIR):
        for name in files:
            if not name.endswith(".lua"):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            for match in re.finditer(r"^\s*function\s+([A-Za-z0-9_]+)\s*\(", text, re.MULTILINE):
                names.add(match.group(1))
            for match in re.finditer(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:function|[a-z]+\.[a-z]+)", text, re.MULTILINE):
                names.add(match.group(1))
            for match in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Z][A-Za-z0-9_]*)\s*$", text, re.MULTILINE):
                aliases[match.group(1)] = match.group(2)
    return names


def project_files():
    for target in TARGETS:
        base = os.path.join(PROJECTS, target)
        for root, _dirs, files in os.walk(base):
            for name in files:
                skip = (os.sep + "lang" + os.sep in root + os.sep
                        or os.sep + "DATA" + os.sep in root + os.sep
                        or name.endswith("_Strings.lua"))
                if name.endswith(".lua") and not skip:
                    yield os.path.join(root, name)


def main():
    documented = documented_names()
    known = documented | source_names()
    known |= set(aliases)
    for names in OPTIONAL_LIBRARY_CALLS.values():
        known |= names
    unknown = {}
    for path in project_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        defined = set(LOCAL_DEF.findall(text))
        defined |= {name.split(".")[-1].split(":")[-1] for name in defined}
        for match in CALL.finditer(text):
            name = match.group(1)
            if name in known or name in defined:
                continue
            if re.search(r"(?:local\s+%s\b|%s\s*=)" % (re.escape(name), re.escape(name)), text):
                continue
            unknown.setdefault(name, set()).add(os.path.relpath(path, PROJECTS))

    if not unknown:
        print("API CALL CHECK OK: every ESO function called by the add-ons exists in the %s documentation or the live UI source" % audit_env.docs_api_version(DOCS))
        return 0

    print("API CALL CHECK FAILED: these calls are in neither the documentation nor the live UI source")
    for name in sorted(unknown):
        print("  %s  <- %s" % (name, ", ".join(sorted(unknown[name]))))
    return 1


if __name__ == "__main__":
    sys.exit(main())
