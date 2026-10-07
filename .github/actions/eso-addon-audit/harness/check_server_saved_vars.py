import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

PROJECTS = audit_env.projects_root()
CALL = re.compile(r"ZO_SavedVars:New\w*\s*\(")


def args_of(text, start):
    depth, i, parts, cur = 0, start, [], []
    while i < len(text):
        c = text[i]
        if c in "({[":
            depth += 1
        elif c in ")}]":
            if depth == 0:
                parts.append("".join(cur))
                return parts
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    return parts


bad = []
for proj in audit_env.targets():
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "*.lua"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in CALL.finditer(text):
            args = [a.strip() for a in args_of(text, m.end())]
            namespace = args[2] if len(args) > 2 else ""
            ok = "GetWorldName" in namespace
            if not ok and re.match(r"^[A-Za-z_]\w*$", namespace):
                ok = re.search(r"\b%s\s*=\s*GetWorldName\s*\(" % re.escape(namespace), text) is not None
            if not ok:
                bad.append((path, text[:m.start()].count("\n") + 1, namespace or "(missing)"))

if bad:
    print("SERVER SAVED VARIABLES CHECK FAILED: settings must be kept per server (NA, EU, PTS); pass GetWorldName() (or a variable set from it) as the namespace of every ZO_SavedVars:New... call")
    for path, line, ns in bad:
        print("  %s:%d  namespace %s" % (path, line, ns))
    sys.exit(1)
print("SERVER SAVED VARIABLES CHECK OK: every SavedVariables table is kept per server (NA, EU, PTS)")
