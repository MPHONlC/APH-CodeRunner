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

CALL = re.compile(r"(?<![\w.:])((?:Get|Is|Has|Can|Request|Set|Do|Play|Reload|Select|Clear|Add|Show|Update|Anchor|Zo|zo|ZO_)[A-Za-z0-9_]*)\s*\(")
ANY_CALL = re.compile(r"(?<![\w.:])([A-Za-z_]\w*)\s*\(")
METHOD_CALL = re.compile(r":([A-Za-z_]\w*)\s*\(")
RESTRICTED = re.compile(r"^\* ([A-Za-z0-9_]+) \*(private|protected)\*")
LOCAL_DEF = re.compile(r"(?:local\s+function\s+|function\s+)([A-Za-z0-9_.:]+)")
NAME_LIST = r"((?:[A-Za-z_]\w*\s*,\s*)*[A-Za-z_]\w*)"
LOCAL_LIST = re.compile(r"\blocal\s+" + NAME_LIST)
FOR_LIST = re.compile(r"\bfor\s+" + NAME_LIST + r"\s*(?:=|\bin\b)")
PARAMS = re.compile(r"\bfunction\b[^(\n]*\(([^)]*)\)")
LONG_BRACKET = re.compile(r"\[(=*)\[.*?\]\1\]", re.S)


def code_only(text):
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("--", i):
            m = LONG_BRACKET.match(text, i + 2)
            end = m.end() if m else (text.find("\n", i) if text.find("\n", i) >= 0 else n)
            out.append("\n" * text.count("\n", i, end))
            i = end
            continue
        c = text[i]
        if c == "[":
            m = LONG_BRACKET.match(text, i)
            if m:
                out.append('""' + "\n" * text.count("\n", i, m.end()))
                i = m.end()
                continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append('""')
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def declared_names(code):
    names = set()
    for pattern in (LOCAL_LIST, FOR_LIST):
        for match in pattern.finditer(code):
            names |= {part.strip() for part in match.group(1).split(",")}
    for match in PARAMS.finditer(code):
        names |= {part.strip() for part in match.group(1).split(",") if part.strip() and part.strip() != "..."}
    return names


restricted_globals = {}
method_status = {}


def documented_names():
    names = set()
    section, current = "", None
    with open(DOCS, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("h2. "):
                section = stripped[4:]
            elif stripped.startswith("h3. "):
                current = stripped[4:]
            match = re.match(r"\* ([A-Za-z0-9_]+)\(", stripped)
            if match:
                names.add(match.group(1))
            if section == "Object API":
                method = re.match(r"\* ([A-Za-z0-9_]+)(?: \*([a-z-]+)\*)? \(", stripped)
                if method:
                    method_status.setdefault(method.group(1), set()).add(method.group(2) or "public")
            else:
                restricted = RESTRICTED.match(stripped)
                if restricted:
                    restricted_globals[restricted.group(1)] = restricted.group(2)
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
    blocked = {}
    for path in project_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = code_only(handle.read())
        defined = set(LOCAL_DEF.findall(text))
        defined |= {name.split(".")[-1].split(":")[-1] for name in defined}
        defined |= declared_names(text)
        for match in CALL.finditer(text):
            name = match.group(1)
            if name in known or name in defined:
                continue
            if re.search(r"(?:local\s+%s\b|%s\s*=)" % (re.escape(name), re.escape(name)), text):
                continue
            unknown.setdefault(name, set()).add(os.path.relpath(path, PROJECTS))
        for match in ANY_CALL.finditer(text):
            name = match.group(1)
            kind = restricted_globals.get(name)
            if kind and name not in defined:
                blocked.setdefault("%s (%s)" % (name, kind), set()).add(os.path.relpath(path, PROJECTS))
        for match in METHOD_CALL.finditer(text):
            name = match.group(1)
            status = method_status.get(name)
            if status and "public" not in status and "protected-attributes" not in status:
                blocked.setdefault(":%s (%s)" % (name, "/".join(sorted(status))), set()).add(os.path.relpath(path, PROJECTS))

    if blocked:
        print("API CALL CHECK FAILED: these calls are private or protected in the %s documentation; add-on code cannot make them (protected functions only through CallSecureProtected)" % audit_env.docs_api_version(DOCS))
        for name in sorted(blocked):
            print("  %s  <- %s" % (name, ", ".join(sorted(blocked[name]))))
        if unknown:
            print("Also in neither the documentation nor the live UI source:")
            for name in sorted(unknown):
                print("  %s  <- %s" % (name, ", ".join(sorted(unknown[name]))))
        return 1
    if not unknown:
        print("API CALL CHECK OK: every ESO function called by the add-ons exists in the %s documentation or the live UI source" % audit_env.docs_api_version(DOCS))
        return 0

    print("API CALL CHECK FAILED: these calls are in neither the documentation nor the live UI source")
    for name in sorted(unknown):
        print("  %s  <- %s" % (name, ", ".join(sorted(unknown[name]))))
    return 1


if __name__ == "__main__":
    sys.exit(main())
