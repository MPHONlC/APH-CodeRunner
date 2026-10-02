import re, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

SRC = os.path.join(audit_env.esoui_dir(), "esoui")
PROJECTS = audit_env.projects_root()

def template_block(name):
    pat = re.compile(r'<(\w+)\s[^>]*name="%s"' % re.escape(name))
    for path in glob.glob(os.path.join(SRC, "**", "*.xml"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        m = pat.search(text)
        if not m:
            continue
        tag = m.group(1)
        start = m.start()
        open_end = text.find(">", m.end())
        if open_end == -1:
            return ""
        if text[open_end - 1] == "/":
            return ""
        close = text.find("</%s>" % tag, open_end)
        return text[open_end:close if close != -1 else open_end + 4000]
    return None

bad = []
for proj in audit_env.targets():
    for path in glob.glob(os.path.join(PROJECTS, proj, "**", "*.lua"), recursive=True):
        for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            m = re.search(r'CreateControlFromVirtual\(\s*nil\s*,[^,]+,\s*"([^"]+)"', line)
            if not m:
                continue
            tpl = m.group(1)
            block = template_block(tpl)
            if block is None:
                print("  ? %s:%d unknown template %s" % (path, n, tpl))
                continue
            if '$(parent)' in block:
                bad.append((path, n, tpl))

if bad:
    print("NIL-NAME CHECK FAILED: these templates declare $(parent) children, so a nil name makes them global")
    for path, n, tpl in bad:
        print("  %s:%d  %s" % (path, n, tpl))
    sys.exit(1)
print("NIL-NAME CHECK OK: no nil-named CreateControlFromVirtual uses a template with $(parent) children")
