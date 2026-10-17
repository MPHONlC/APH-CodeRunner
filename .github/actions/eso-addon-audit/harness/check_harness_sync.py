import glob
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

WORKSPACE = audit_env.workspace_root()
ESO_ROOT = os.path.dirname(WORKSPACE)
MASTER = os.path.join(ESO_ROOT, "Github-Actions", "eso-addon-audit", "harness")
PROJECTS = audit_env.projects_root()


def harness_files(root):
    found = []
    for pattern in ("*.py", os.path.join("audit", "*.py"), os.path.join("audit", "*.lua")):
        for path in glob.glob(os.path.join(root, pattern)):
            found.append(os.path.relpath(path, root))
    return sorted(found)


def copies():
    out = [os.path.join(WORKSPACE, "#Backups", "Harness")]
    for base in (os.path.join(WORKSPACE, "#Documentations"), os.path.join(ESO_ROOT, "Github-Repo")):
        for path in sorted(glob.glob(os.path.join(base, "*", ".github", "actions", "eso-addon-audit", "harness"))):
            project = path[len(base) + 1:].split(os.sep)[0]
            if base.endswith("#Documentations") or os.path.isdir(os.path.join(PROJECTS, project)):
                out.append(path)
    return [path for path in out if os.path.isdir(path)]


def main():
    if not os.path.isdir(MASTER):
        print("HARNESS SYNC CHECK OK: no Github-Actions master here, nothing to compare")
        return 0
    wanted = harness_files(MASTER)
    master_text = {name: open(os.path.join(MASTER, name), "rb").read() for name in wanted}
    problems = []
    for copy in copies():
        stale = []
        for name in wanted:
            path = os.path.join(copy, name)
            if not os.path.exists(path):
                stale.append(name + " (missing)")
            elif open(path, "rb").read() != master_text[name]:
                stale.append(name)
        if stale:
            problems.append("%s differs from the Github-Actions master: %s" % (os.path.relpath(copy, ESO_ROOT), ", ".join(stale)))
    if problems:
        print("HARNESS SYNC CHECK FAILED: copy these from Github-Actions/eso-addon-audit/harness")
        for line in problems:
            print("  " + line)
        return 1
    print("HARNESS SYNC CHECK OK: every local audit harness copy matches the Github-Actions master (%d files)" % len(wanted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
