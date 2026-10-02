import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

PROJECTS = audit_env.projects_root()
DANGER = re.compile(r"reset|delete|wipe|clear|forget|unrestricted|remove|erase|purge", re.I)
BUTTON = re.compile(r'type\s*=\s*"button"')


def enclosing_table(text, at):
    i, depth = at, 0
    while i > 0:
        c = text[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                break
            depth -= 1
        i -= 1
    j, depth = at, 0
    while j < len(text):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                break
            depth -= 1
        j += 1
    return i, text[i:j + 1]


def name_of(block):
    m = re.search(r'\bname\s*=\s*([^\n]+)', block)
    return m.group(1) if m else ""


def label_of(block):
    expr = name_of(block)
    keys = re.findall(r'L\("([A-Z0-9_]+)"\)', expr)
    return " ".join(keys) or expr


RED = re.compile(r'\|c[Ff][Ff]([0-6][0-9A-Fa-f])\1')


def lang_values(proj):
    values = {}
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "default.lua"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        for key, value in re.findall(r'^\s*([A-Z0-9_]+)\s*=\s*"((?:[^"\\]|\\.)*)"', text, re.M):
            values.setdefault(key, value)
    return values


def is_red(expr, text, values, depth=0):
    if RED.search(expr):
        return True
    for key in re.findall(r'L\("([A-Z0-9_]+)"\)', expr):
        if RED.match(values.get(key, "")):
            return True
    name = re.fullmatch(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*', expr)
    if name and depth < 3:
        found = re.search(r'local\s+' + name.group(1) + r'\s*=\s*([^\n]+)', text)
        if found:
            return is_red(found.group(1), text, values, depth + 1)
    return False


bad = []
for proj in audit_env.targets():
    values = lang_values(proj)
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "*.lua"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in BUTTON.finditer(text):
            start, block = enclosing_table(text, m.start())
            label = label_of(block)
            if not DANGER.search(label):
                continue
            missing = [key for key in ("isDangerous", "warning") if key not in block]
            if not is_red(name_of(block), text, values):
                missing.append("a red name (|cFF0000), which is how console shows it")
            if missing:
                bad.append((path, text[:start].count("\n") + 1, label, ", ".join(missing)))

if bad:
    print("DANGER BUTTON CHECK FAILED: buttons that reset, delete, wipe, clear, forget or unlock need isDangerous, a warning and a red name")
    for path, line, label, missing in bad:
        print("  %s:%d  %s (missing %s)" % (path, line, label, missing))
    sys.exit(1)
print("DANGER BUTTON CHECK OK: every reset/delete/wipe/clear/forget/unrestricted button has isDangerous, a warning icon and a red name for console")
