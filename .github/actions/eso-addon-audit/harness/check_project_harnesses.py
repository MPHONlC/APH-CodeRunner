import glob
import os
import re
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

WORKSPACE = audit_env.workspace_root()
PROJECTS = audit_env.projects_root()
HARNESSES = os.path.join(WORKSPACE, "#Backups", "Harness")
TIMEOUT = 1200


def text_of(path, seen=None):
    seen = seen if seen is not None else set()
    if path in seen or not os.path.exists(path):
        return ""
    seen.add(path)
    text = open(path, encoding="utf-8", errors="replace").read()
    for included in re.findall(r'dofile\(\s*"([^"]+harness_[^"]+\.lua)"', text):
        text += text_of(included, seen)
    return text


def run(command, env_extra, cwd):
    env = dict(os.environ, **env_extra)
    try:
        done = subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "timed out after %d s" % TIMEOUT
    output = (done.stdout + done.stderr).strip().splitlines()
    failed = done.returncode != 0 or any("SUITE FAILED" in line for line in output)
    detail = next((line for line in output if "FAIL" in line or "lua5.1:" in line or "rror" in line), output[-1] if output else "")
    return not failed, detail.strip()[:220]


def main():
    if not os.path.isdir(HARNESSES):
        print("PROJECT HARNESS CHECK OK: no local #Backups/Harness here, the project harnesses run on the developer's machine")
        return 0
    problems, ran = [], 0
    for project in audit_env.targets():
        marker = '"%s/' % project
        for path in sorted(glob.glob(os.path.join(HARNESSES, "harness_*.lua"))):
            text = text_of(path)
            if marker not in text and ('.. "%s/' % project) not in text:
                if ("/%s/" % project) in text:
                    problems.append("%s loads %s's files in a way this check can't see, so it never runs here; load them with dofile(PROJECTS .. \"%s/...\")"
                                    % (os.path.basename(path), project, project))
                continue
            modes = [{}]
            for name in sorted(set(re.findall(r'os\.getenv\("(\w*CONSOLE)"\)', text))):
                modes.append({name: "1"})
            for extra in modes:
                ok, detail = run(["lua5.1", path], extra, WORKSPACE)
                ran += 1
                if not ok:
                    label = " ".join("%s=%s" % item for item in extra.items())
                    problems.append("%s%s: %s" % (os.path.basename(path), (" (" + label + ")") if label else "", detail))
        folder = os.path.realpath(os.path.join(PROJECTS, project))
        suites = glob.glob(os.path.join(os.path.dirname(folder), "tests", "run*.sh"))
        suites += glob.glob(os.path.join(WORKSPACE, "#Scripts", project + "-tool", "tests", "run*.sh"))
        for script in sorted(set(suites)):
            ok, detail = run(["sh", script], {}, os.path.dirname(script))
            ran += 1
            if not ok:
                problems.append("%s: %s" % (os.path.relpath(script, WORKSPACE), detail))
    if problems:
        print("PROJECT HARNESS CHECK FAILED: a project harness or suite no longer passes (stale after a rename, or a regression)")
        for line in problems:
            print("  " + line)
        return 1
    print("PROJECT HARNESS CHECK OK: %d harness and suite runs pass for the audited add-ons" % ran)
    return 0


if __name__ == "__main__":
    sys.exit(main())
