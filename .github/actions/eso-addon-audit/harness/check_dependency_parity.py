import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
TARGETS = audit_env.targets()
TABLE = os.path.join(PROJECTS, "APH-OnManager", "DATA", "KnownAddonDependencies.lua")
REGISTER = re.compile(r"LibAPH\.RegisterAddonDependencies\(\s*[\w.]+\s*,\s*\{([^}]*)\}\s*,\s*\{([^}]*)\}", re.S)


def names(field):
    out = set()
    for token in (field or "").split():
        name = re.split(r"[<>=]", token, maxsplit=1)[0]
        if name:
            out.add(name)
    return out


def manifest_path(project):
    path = os.path.join(PROJECTS, project, project + ".addon")
    if os.path.exists(path):
        return path
    return os.path.join(PROJECTS, project, project + ".txt")


def manifest(project):
    path = manifest_path(project)
    fields = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^##\s*(\w+)\s*:\s*(.*?)\s*$", line)
        if m:
            fields[m.group(1)] = fields.get(m.group(1), "") + " " + m.group(2)
    optional_raw = " ".join(fields.get(key, "") for key in fields if key.endswith("OptionalDependsOn"))
    return names(fields.get("DependsOn")), names(fields.get("OptionalDependsOn")), re.findall(r"\S*[<>=]\S*", optional_raw)


def registration(project):
    for root, _dirs, files in os.walk(os.path.join(PROJECTS, project)):
        for name in files:
            if not name.endswith(".lua"):
                continue
            text = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
            m = REGISTER.search(text)
            if m:
                return set(re.findall(r'"([^"]+)"', m.group(1))), set(re.findall(r'"([^"]+)"', m.group(2)))
    return None


def table_entries():
    if not os.path.exists(TABLE):
        return None
    text = open(TABLE, encoding="utf-8").read()
    return {m.group(1): set(re.findall(r'"([^"]+)"', m.group(2)))
            for m in re.finditer(r'\[\s*"([^"]+)"\s*\]\s*=\s*\{([^}]*)\}', text)}


def main():
    problems = []
    table = table_entries()
    for project in TARGETS:
        required, optional, versioned = manifest(project)
        for token in versioned:
            problems.append("%s: OptionalDependsOn carries a version (%s), versions belong on DependsOn only" % (project, token))
        reg = registration(project)
        if (required or optional) and "LibAPH" in required:
            if reg is None:
                problems.append("%s: never calls LibAPH.RegisterAddonDependencies" % project)
            else:
                if reg[0] != required:
                    problems.append("%s: registers required %s, manifest says %s" % (project, sorted(reg[0]), sorted(required)))
                if reg[1] != optional:
                    problems.append("%s: registers optional %s, manifest says %s" % (project, sorted(reg[1]), sorted(optional)))
        listed = table.get(project, set()) if table is not None else optional
        if listed != optional:
            problems.append("%s: KnownAddonDependencies lists %s, manifest says %s" % (project, sorted(listed), sorted(optional)))

    for project in TARGETS:
        text = open(manifest_path(project), encoding="utf-8").read()
        for field in ("SavedVariables", "SavedVariablesPerCharacter"):
            m = re.search(r"^## " + field + r":\s*(.+)$", text, re.M)
            if not m:
                continue
            for sv_name in m.group(1).split():
                for lua_path in glob.glob(os.path.join(PROJECTS, project, "**", "*.lua"), recursive=True):
                    code = open(lua_path, encoding="utf-8").read()
                    if re.search(r"^\s*" + re.escape(sv_name) + r"\s*=", code, re.M):
                        problems.append("%s assigns the global %s, which is also its SavedVariables name; ESO's saved data would be overwritten on load" % (os.path.relpath(lua_path, PROJECTS), sv_name))

    if problems:
        print("DEPENDENCY PARITY FAILED:")
        for line in problems:
            print("  " + line)
        return 1
    print("DEPENDENCY PARITY OK: every project's registration and data-table entry match its manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
