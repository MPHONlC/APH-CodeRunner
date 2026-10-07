import glob
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

DOCS = audit_env.docs_root()
LIBAPH = os.path.join(DOCS, "LibAPH", ".github", "workflows")
WAIT = "./.github/actions/eso-wait-for-libaph"
READERS = {
    "version-refresh.yml": "./.github/actions/version-refresh",
    "dependency-check.yml": "./.github/actions/eso-dependency-check",
    "api-version-refresh.yml": "./.github/actions/eso-api-version-refresh",
    "readme-badge-check.yml": "./.github/actions/eso-readme-badge-check",
}
SCHEDULED = {
    "api-version-refresh.yml": "api-version-refresh.yml",
    "dependency-check.yml": "api-version-refresh.yml",
    "esoui-auto-release.yml": "esoui-auto-release.yml",
    "github-auto-release.yml": "github-auto-release.yml",
    "bethesda-auto-release.yml": "bethesda-auto-release.yml",
}
DISPATCH = {
    "api-version-refresh.yml": "libaph-api-version-refresh",
    "dependency-check.yml": "libaph-api-version-refresh",
    "esoui-auto-release.yml": "libaph-esoui-auto-release",
    "github-auto-release.yml": "libaph-github-auto-release",
    "bethesda-auto-release.yml": "libaph-bethesda-auto-release",
}
NOTIFIED_BY = ["API Version Refresh", "ESOUI Auto Release", "GitHub Auto Release", "Bethesda Auto Release"]
DAILY = re.compile(r"cron:\s*['\"](\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*['\"]")


def read(path):
    return open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""


def daily_minutes(text):
    return [int(h) * 60 + int(m) for m, h in DAILY.findall(text)]


def follows_libaph(folder):
    workflows = os.path.join(folder, ".github", "workflows")
    text = read(os.path.join(workflows, "version-refresh.yml")) + read(os.path.join(workflows, "dependency-check.yml"))
    return "MPHONlC/LibAPH" in text or "dependency_name: 'LibAPH'" in text


bad = []
if not os.path.isdir(LIBAPH):
    print("LIBAPH FIRST CHECK OK: no LibAPH workflows here to compare against")
    sys.exit(0)
notify = read(os.path.join(LIBAPH, "notify-dependents.yml"))
if "./.github/actions/eso-notify-dependents" not in notify or "workflow_run:" not in notify:
    bad.append("LibAPH: .github/workflows/notify-dependents.yml must run ./.github/actions/eso-notify-dependents on workflow_run, so the add-ons start when its daily runs finish")
else:
    for name in NOTIFIED_BY:
        if '"%s"' % name not in notify:
            bad.append("LibAPH/notify-dependents.yml: workflow_run does not list \"%s\"" % name)
    if "github.event.workflow_run.event == 'schedule'" not in notify:
        bad.append("LibAPH/notify-dependents.yml: notify only after scheduled runs (github.event.workflow_run.event == 'schedule')")
if not os.path.exists(os.path.join(DOCS, "LibAPH", ".github", "actions", "eso-notify-dependents", "notify_dependents.py")):
    bad.append("LibAPH: .github/actions/eso-notify-dependents is missing")
for folder in sorted(glob.glob(os.path.join(DOCS, "*"))):
    name = os.path.basename(folder)
    if name == "LibAPH" or not os.path.isdir(os.path.join(folder, ".github", "workflows")) or not follows_libaph(folder):
        continue
    workflows = os.path.join(folder, ".github", "workflows")
    if not os.path.exists(os.path.join(folder, ".github", "actions", "eso-wait-for-libaph", "wait_for_libaph.py")):
        bad.append("%s: .github/actions/eso-wait-for-libaph is missing" % name)
    waiter = read(os.path.join(folder, ".github", "actions", "eso-wait-for-libaph", "wait_for_libaph.py"))
    if waiter and ("GITHUB_EVENT_NAME" not in waiter or "due_today" in waiter):
        bad.append("%s: eso-wait-for-libaph is the old copy that waits on every run and for scheduled runs GitHub has not started; copy the current Github-Actions/eso-wait-for-libaph" % name)
    for workflow, kind in DISPATCH.items():
        text = read(os.path.join(workflows, workflow))
        if text and not re.search(r"repository_dispatch:\s*\n\s*types:\s*\[[^\]]*\b%s\b" % re.escape(kind), text):
            bad.append("%s/%s: add 'repository_dispatch: types: [%s]' so it starts when LibAPH's daily run finishes" % (name, workflow, kind))
    calver = read(os.path.join(folder, ".github", "actions", "version-refresh", "calver_refresh.py"))
    if calver and "api.github.com/repos/%s/contents" not in calver:
        bad.append("%s: version-refresh reads LibAPH from raw.githubusercontent.com, which can be minutes old; copy the current Github-Actions/version-refresh" % name)
    for workflow, reader in READERS.items():
        text = read(os.path.join(workflows, workflow))
        if not text or reader not in text:
            continue
        if WAIT not in text or text.index(WAIT) > text.index(reader):
            bad.append("%s/%s: %s runs without waiting for LibAPH first (add '- uses: %s' before it)" % (name, workflow, reader, WAIT))
    for workflow, libaph_workflow in SCHEDULED.items():
        mine = daily_minutes(read(os.path.join(workflows, workflow)))
        theirs = daily_minutes(read(os.path.join(LIBAPH, libaph_workflow)))
        if mine and theirs and min(mine) < max(theirs) + 60:
            bad.append("%s/%s: daily cron at %02d:%02d UTC is less than an hour after LibAPH's %s (%02d:%02d UTC)"
                       % (name, workflow, min(mine) // 60, min(mine) % 60, libaph_workflow, max(theirs) // 60, max(theirs) % 60))

if bad:
    print("LIBAPH FIRST CHECK FAILED: LibAPH must stamp and release before the add-ons that follow it")
    for entry in bad:
        print("  " + entry)
    sys.exit(1)
print("LIBAPH FIRST CHECK OK: LibAPH starts the add-ons that follow it when its daily runs finish, their own schedule stays an hour later as a fallback, and they wait only on scheduled runs while a LibAPH run is active")
