import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

PROJECTS = audit_env.projects_root()
BUTTON = re.compile(r'type\s*=\s*"button"')
CONTROL = re.compile(r'type\s*=\s*(?:"[a-z]+"|lhas\.ST_[A-Z]+)')


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
    return i, j


def width_of(block):
    m = re.search(r'\bwidth\s*=\s*([^,\n}]+)', block)
    value = m.group(1).strip() if m else '"full"'
    return '"half"' if '"half"' in value or value == 'reset_width' else value


bad = []
for proj in audit_env.targets():
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "*.lua"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in BUTTON.finditer(text):
            start, end = enclosing_table(text, m.start())
            if width_of(text[start:end]) != '"half"':
                continue
            nxt = CONTROL.search(text, end)
            if not nxt or not BUTTON.match(text, nxt.start()):
                continue
            n_start, n_end = enclosing_table(text, nxt.start())
            if text[end:n_start].count("{") or text[end:n_start].count("}") > 1:
                continue
            if width_of(text[n_start:n_end]) != '"half"':
                bad.append((path, text[:n_start].count("\n") + 1))

if bad:
    print("BUTTON WIDTH CHECK FAILED: a button right after a half-width button must be half-width too, or the pair does not line up")
    for path, line in bad:
        print("  %s:%d" % (path, line))
    sys.exit(1)
print("BUTTON WIDTH CHECK OK: settings buttons that sit next to each other are both half-width")
