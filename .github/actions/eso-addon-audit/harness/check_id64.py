import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
DOCS = audit_env.docs_file()
TARGETS = audit_env.targets()

SAFE_HELPERS = ("Id64ToString(", "zo_getSafeId64Key(", "StringToId64(", "CompareId64s(", "AreId64sEqual(", "zo_id64ToString(")
ALWAYS_FLAGGED = ("NumberToId64", "Id64ToNumber")

REVIEWED = {
    ("APH-Search/UTILS/Sources.lua", "GetFriendCharacterInfo"): "only the first three returns are read; the consoleId id64 is never captured",
}


def id64_functions():
    names = set()
    with open(DOCS, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"\* ([A-Za-z0-9_]+)\((.*)\)", line.strip())
        if not match:
            continue
        returns = lines[index + 1] if index + 1 < len(lines) else ""
        if "*id64" in match.group(2) or ("_Returns:_" in returns and "*id64" in returns):
            names.add(match.group(1))
    return names


def lua_files():
    for target in TARGETS:
        for root, _, files in os.walk(os.path.join(PROJECTS, target)):
            for name in files:
                if name.endswith(".lua"):
                    yield os.path.join(root, name)


def main():
    watched = id64_functions() | set(ALWAYS_FLAGGED)
    call = re.compile(r"(?<![\w.:])(" + "|".join(sorted(watched, key=len, reverse=True)) + r")\s*\(")
    problems = []
    for path in lua_files():
        rel = os.path.relpath(path, PROJECTS).replace(os.sep, "/")
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                for match in call.finditer(line):
                    name = match.group(1)
                    if (rel, name) in REVIEWED or (rel.split("/", 1)[-1], name) in audit_env.reviewed_id64():
                        continue
                    if name not in ALWAYS_FLAGGED and any(helper in line for helper in SAFE_HELPERS):
                        continue
                    problems.append(f"  {rel}:{number}: {name} takes or returns an id64; key it with Id64ToString, compare with CompareId64s, pass saved ids through StringToId64")
    if problems:
        print("ID64 CHECK FAILED: id64 values must never be table keys, == compared, or turned into Lua numbers")
        print("\n".join(problems))
        return 1
    print(f"ID64 CHECK OK: no unreviewed id64 use across {len(TARGETS)} projects ({len(watched)} id64 functions watched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
