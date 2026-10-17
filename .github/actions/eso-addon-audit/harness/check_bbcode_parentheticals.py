import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
TAG = re.compile(r'\[(/?)(\w+)(?:=[^\]]*)?\]')
BLOCKING = {'b', 'color', 'url', 'code', 'size', 'i', 'quote', 'img', 'email', 'font'}
LAYOUT = {'*', 'list', 'center', 'spoiler', 'indent', 'left', 'right', 'u', 's', 'highlight'}


def plain_asides(text):
    tokens = {m.start(): (m.end(), m.group(1) == '/', m.group(2).lower()) for m in TAG.finditer(text)}
    stack, found, pos = [], [], 0
    while pos < len(text):
        if pos in tokens:
            end, closing, name = tokens[pos]
            if closing:
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k] == name:
                        del stack[k:]
                        break
            elif name not in LAYOUT:
                stack.append(name)
            pos = end
            continue
        if text[pos] == '(' and not (set(stack) & BLOCKING):
            prev = text[pos - 1] if pos else ' '
            close, nl = text.find(')', pos), text.find('\n', pos)
            if not (prev.isalnum() or prev in '_.:]') and close > 0 and (nl < 0 or close < nl) \
                    and '(' not in text[pos + 1:close] and '[' not in text[pos + 1:close]:
                found.append(text[pos:close + 1])
        pos += 1
    return found


bad, checked = [], 0
for path in sorted(glob.glob(os.path.join(DOCS, "*", "README_BBCODE.txt"))):
    checked += 1
    for aside in plain_asides(open(path, encoding="utf-8", errors="replace").read()):
        bad.append("%s: %s is not gray italic; wrap it as [COLOR=\"Gray\"][i]%s[/i][/COLOR]" % (os.path.relpath(path, DOCS), aside[:70], aside[:30] + ("..." if len(aside) > 30 else "")))

if bad:
    print("BBCODE PARENTHETICALS CHECK FAILED: every ( ) aside in an ESOUI description is gray italic (names inside keep their own color)")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("BBCODE PARENTHETICALS CHECK OK: every ( ) aside in %d ESOUI descriptions is gray italic" % checked)
