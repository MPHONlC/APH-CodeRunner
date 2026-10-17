import glob
import importlib.util
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
SIGN_CODES = "&#%d;&#%d;" % (0x26A0, 0xFE0F)
CANON = {
    "README_BBCODE.txt": ['[b][COLOR="Orange"]⚠️ CONSOLE TESTING NOTES ⚠️[/COLOR][/b]',
                          'This addon was developed and tested on [b][COLOR="#FF69B4"]PC / Steam Deck[/COLOR][/b] [COLOR="Gray"][i](using Force Console Flow for console testing)[/i][/COLOR].'],
    "README_COMMONMARK.txt": ["**Console Testing Notes:** This addon was developed and tested on **PC / Steam Deck** (using Force Console Flow for console testing)."],
    "README.md": ["> [!WARNING]",
                  "> **Console Testing Notes:** This addon was developed and tested on **PC / Steam Deck** *(using Force Console Flow for console testing)*."],
}


def has_block(lines, block):
    for index in range(len(lines) - len(block) + 1):
        if [line.rstrip() for line in lines[index:index + len(block)]] == block:
            return True
    return False


bad, checked = [], 0
for folder in sorted(glob.glob(os.path.join(DOCS, "*"))):
    texts = {}
    for name in CANON:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            texts[name] = open(path, encoding="utf-8", errors="replace").read()
    if not any("console testing notes" in text.lower() for text in texts.values()):
        continue
    checked += 1
    project = os.path.basename(folder)
    for name, block in CANON.items():
        if name not in texts:
            bad.append("%s/%s: missing, but the project has console testing notes" % (project, name))
        elif not has_block(texts[name].split("\n"), block):
            bad.append("%s/%s: the console testing note is not the shared one:\n      %s" % (project, name, "\n      ".join(block)))
    converter = os.path.join(folder, ".github", "actions", "esoui-safe-text", "esoui_safe_text.py")
    if os.path.isfile(converter):
        spec = importlib.util.spec_from_file_location("esoui_safe_text_%d" % checked, converter)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if SIGN_CODES not in module.convert("⚠️", "esoui"):
            bad.append("%s: esoui-safe-text turns ⚠️ into %r for ESOUI; it must send %s like a browser paste, so the uploaded page shows the sign" % (project, module.convert("⚠️", "esoui"), SIGN_CODES))

if bad:
    print("CONSOLE TESTING NOTES CHECK FAILED: one console testing note per format (ESOUI ⚠️ heading, Bethesda bold CommonMark, GitHub WARNING block), and ESOUI uploads keep the ⚠️")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("CONSOLE TESTING NOTES CHECK OK: %d projects use the shared console testing note in all three formats, and ESOUI uploads keep the ⚠️" % checked)
