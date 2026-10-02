import argparse
import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
sys.path.insert(0, HARNESS)
import audit_env
CHECKS = ["api_calls", "bindings", "button_widths", "danger_buttons", "dependency_parity", "id64", "license_format", "local_order", "nil_control_names", "ui_layout"]
MODES = ["keyboard", "gamepad", "console"]

READ_CONFIG = r'''
local chunk = assert(loadfile(arg[1]))
local settings = {}
setfenv(chunk, settings)
local returned = chunk()
local config = type(returned) == "table" and returned or settings
local function list(value)
    if type(value) ~= "table" then return "" end
    local out = {}
    for key, item in pairs(value) do
        if type(key) == "number" then out[#out + 1] = tostring(item) else out[#out + 1] = tostring(key) end
    end
    table.sort(out)
    return table.concat(out, ",")
end
for _, key in ipairs({ "addon", "libraries", "globals", "skip_checks", "skip_commands", "reviewed_id64", "modes" }) do
    local value = config[key]
    print(key .. "=" .. (type(value) == "table" and list(value) or tostring(value or "")))
end
'''


def read_config(path):
    config = {"addon": "", "libraries": [], "globals": [], "skip_checks": [], "skip_commands": [], "reviewed_id64": [], "modes": []}
    if not path or not os.path.exists(path):
        return config
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as handle:
        handle.write(READ_CONFIG)
        reader = handle.name
    try:
        output = subprocess.run(["lua5.1", reader, path], capture_output=True, text=True, check=True).stdout
    finally:
        os.unlink(reader)
    for line in output.splitlines():
        key, _, value = line.partition("=")
        if key == "addon":
            config[key] = value
        elif key in config:
            config[key] = [item for item in value.split(",") if item]
    return config


DOCS_ROOT = None


def find_config(projects, project):
    documentations = DOCS_ROOT
    direct = os.path.join(documentations, project, ".eso-auditrc")
    if os.path.exists(direct):
        return direct
    for candidate in glob.glob(os.path.join(documentations, "*", ".eso-auditrc")):
        if read_config(candidate)["addon"] == project:
            return candidate
    repo_root = os.path.join(projects, project, ".eso-auditrc")
    return repo_root if os.path.exists(repo_root) else None


def lua_list(items):
    return "{ " + ", ".join('"%s"' % item.replace('"', '\\"') for item in items) + " }"


def run_project(projects, esoui, docs, project, config_path, stubs, results):
    config = read_config(config_path)
    for library in config["libraries"]:
        library_config = read_config(find_config(projects, library))
        config["globals"] = config["globals"] + (library_config["globals"] or [library])
    env = dict(os.environ, APH_AUDIT_PROJECTS=projects, APH_AUDIT_TARGETS=project, APH_AUDIT_ESOUI=esoui, APH_AUDIT_DOCS_ROOT=DOCS_ROOT,
               APH_AUDIT_DOCS=docs, APH_AUDIT_REVIEWED_ID64=",".join(config["reviewed_id64"]))

    syntax = []
    for path in glob.glob(os.path.join(projects, project, "**", "*.lua"), recursive=True):
        done = subprocess.run(["luac5.1", "-p", "-o", os.devnull, path], capture_output=True, text=True)
        if done.returncode:
            syntax.append(done.stderr.strip())
    results.append((project, "syntax", not syntax, "\n".join(syntax) or "every .lua file parses"))

    for check in CHECKS:
        if check in config["skip_checks"]:
            results.append((project, check, True, "skipped in .eso-auditrc"))
            continue
        done = subprocess.run([sys.executable, os.path.join(HARNESS, "check_%s.py" % check)], capture_output=True, text=True, env=env, cwd=projects)
        text = (done.stdout + done.stderr).strip()
        results.append((project, check, done.returncode == 0, text))

    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as handle:
        handle.write("return {\n\tlibraries = %s,\n\tglobals = %s,\n\tskip_commands = %s,\n}\n"
                     % (lua_list(config["libraries"]), lua_list(config["globals"]), lua_list(config["skip_commands"])))
        allowed = handle.name
    try:
        for mode in config["modes"] or MODES:
            done = subprocess.run(["lua5.1", os.path.join(HERE, "smoke.lua"), projects, project, mode, stubs, os.path.join(esoui, "esoui"), allowed],
                                  capture_output=True, text=True)
            results.append((project, "smoke " + mode, done.returncode == 0, (done.stdout + done.stderr).strip()))
    finally:
        os.unlink(allowed)


def report(results):
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    failed = [entry for entry in results if not entry[2]]
    for project, check, ok, text in results:
        first = text.splitlines()[0] if text else ""
        print("%s %-20s %-18s %s" % ("PASS" if ok else "FAIL", project, check, first))
        if not ok:
            for line in text.splitlines()[1:40]:
                print("      " + line)
            if in_actions:
                print("::error title=%s %s::%s" % (project, check, first.replace("\n", " ")))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## ESO add-on audit\n\n| Project | Check | Result |\n| --- | --- | --- |\n")
            for project, check, ok, text in results:
                first = (text.splitlines()[0] if text else "").replace("|", "\\|")
                out.write("| %s | %s | %s %s |\n" % (project, check, "pass" if ok else "**fail**", first))
            for project, check, ok, text in failed:
                out.write("\n### %s %s\n\n```\n%s\n```\n" % (project, check, text))
    print("\nAUDIT %s: %d checks, %d failed" % ("OK" if not failed else "FAILED", len(results), len(failed)))
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("projects", nargs="*")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(HARNESS)))
    parser.add_argument("--esoui")
    parser.add_argument("--docs")
    parser.add_argument("--config")
    parser.add_argument("--libraries", action="store_true")
    args = parser.parse_args()
    if args.libraries:
        print("\n".join(read_config(args.config)["libraries"]))
        return 0

    global DOCS_ROOT
    workspace = os.path.abspath(args.root)
    addons = os.path.join(workspace, "AddOns-Project")
    projects = addons if os.path.isdir(addons) else workspace
    DOCS_ROOT = os.path.join(workspace, "#Documentations")
    esoui = os.path.abspath(args.esoui or audit_env.latest_esoui(workspace))
    docs = os.path.abspath(args.docs or os.path.join(esoui, "ESOUIDocumentation.txt"))
    names = args.projects
    if not names:
        names = sorted({os.path.basename(os.path.dirname(path)) for path in glob.glob(os.path.join(projects, "*", "*.addon"))}
                       | {os.path.basename(os.path.dirname(path)) for path in glob.glob(os.path.join(projects, "*", "*.txt"))
                          if os.path.basename(path)[:-4] == os.path.basename(os.path.dirname(path))})

    stubs = os.path.join(tempfile.gettempdir(), "eso_audit_stubs.lua")
    subprocess.run([sys.executable, os.path.join(HERE, "stubgen.py"), docs, os.path.join(esoui, "esoui"), stubs], check=True, capture_output=True)

    results = []
    for name in names:
        config_path = args.config if args.config and len(names) == 1 else find_config(projects, name)
        run_project(projects, esoui, docs, name, config_path, stubs, results)
    return report(results)


if __name__ == "__main__":
    sys.exit(main())
