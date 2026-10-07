import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

ROOT = audit_env.projects_root()
TARGETS = audit_env.targets()
HANDLER = re.compile(r'SLASH_COMMANDS\["(/[^"]+)"\]\s*=\s*function\s*\([^)]*\)\s*\n((?:[^\n]*\n){1,3})')
SILENT_RETURN = re.compile(r'^\s*if\s+(.+?)\s+then\s+return\s+end\s*$')
NIL_GUARD = re.compile(r'^not\s+[A-Za-z_]\w*(\.\w+)?\.settings$|^not\s+[A-Za-z_]\w*$')
DEV_GATE_INSIDE = re.compile(r'if\s+GetDisplayName\(\)\s*~=\s*"@[^"]+"\s+then\s+return\s+end')
HIDDEN_FIELD = re.compile(r'\b(hidden|aphVisible)\s*=\s*function\b')
LISTS = re.compile(r'\b(COMMAND_REFERENCE|COMMAND_CATEGORIES)\s*=\s*\{')
GATED = re.compile(r'\b(available|disabled_check)\s*=\s*function')
REMOVED_API = re.compile(r'LibAPH\.(PrepareSettingsControls|RefreshSettingsVisibility)\b')

bad = []
for project in TARGETS:
    folder = os.path.join(ROOT, project)
    files = sorted(glob.glob(os.path.join(folder, "**", "*.lua"), recursive=True))
    texts = {path: open(path, encoding="utf-8", errors="replace").read() for path in files}
    has_list, uses_refresh = False, False
    for path, text in texts.items():
        rel = os.path.relpath(path, ROOT)
        for m in HANDLER.finditer(text):
            first = next((l for l in m.group(2).splitlines() if l.strip()), "")
            gate = SILENT_RETURN.match(first)
            line = text[:m.start()].count("\n") + 1
            if gate and DEV_GATE_INSIDE.search(first):
                bad.append("%s:%d  %s checks the developer's name inside the command; register it only for that account instead" % (rel, line, m.group(1)))
            elif gate and not NIL_GUARD.match(gate.group(1).strip()):
                bad.append("%s:%d  %s returns silently when '%s'; hide the command while that is true (LibAPH.SetSlashCommandsShown) or say why" % (rel, line, m.group(1), gate.group(1).strip()))
        for m in HIDDEN_FIELD.finditer(text):
            bad.append("%s:%d  '%s =' does nothing in LibAddonMenu or LibHarvensAddonSettings; build the control only when it applies and say /reloadui to apply changes when that flips" % (rel, text[:m.start()].count("\n") + 1, m.group(1)))
        if LISTS.search(text) and GATED.search(text):
            has_list = True
        if "SetSlashCommandsShown" in text:
            uses_refresh = True
        for m in REMOVED_API.finditer(text):
            bad.append("%s:%d  LibAPH.%s was removed (settings could not hide live in LibAddonMenu); build the control only when it applies" % (rel, text[:m.start()].count("\n") + 1, m.group(1)))
    if has_list and not uses_refresh:
        bad.append("%s: its command list hides commands that do not apply, but the commands stay registered; refresh them with LibAPH.SetSlashCommandsShown" % project)

if bad:
    print("COMMAND VISIBILITY CHECK FAILED: commands and settings that need a module or feature that is off are hidden, never left doing nothing")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("COMMAND VISIBILITY CHECK OK: no silent command gates, dev commands registered only for the developer, no dead hidden or aphVisible fields")
