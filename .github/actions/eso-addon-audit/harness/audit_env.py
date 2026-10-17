import os
import re

DEFAULT_TARGETS = ["LibAPH", "APH-OnManager", "AutoLuaMemoryCleaner", "PermMemento", "CharacterBoundItemHider", "APH-Profiler", "APH-Search", "OneAPHaTime"]
HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_FOLDER = "AddOns-Project"


def workspace_root():
    listed = os.environ.get("APH_AUDIT_PROJECTS")
    if listed:
        return os.path.dirname(listed) if os.path.basename(listed.rstrip(os.sep)) == ADDONS_FOLDER else listed
    return os.path.dirname(os.path.dirname(HERE))


def projects_root():
    listed = os.environ.get("APH_AUDIT_PROJECTS")
    if listed:
        return listed
    addons = os.path.join(workspace_root(), ADDONS_FOLDER)
    return addons if os.path.isdir(addons) else workspace_root()


def docs_root():
    return os.environ.get("APH_AUDIT_DOCS_ROOT") or os.path.join(workspace_root(), "#Documentations")


def targets():
    listed = os.environ.get("APH_AUDIT_TARGETS")
    if listed:
        return [name for name in listed.split(",") if name]
    return list(DEFAULT_TARGETS)


def only_targets():
    return bool(os.environ.get("APH_AUDIT_TARGETS"))


def latest_esoui(workspace):
    found = []
    sources = os.path.join(workspace, "#Sources")
    if not os.path.isdir(sources):
        sources = os.path.join(workspace, "Sources")
    if os.path.isdir(sources):
        for name in os.listdir(sources):
            match = re.fullmatch(r"esoui-(\d+(?:\.\d+)*)", name)
            if match:
                found.append((tuple(int(part) for part in match.group(1).split(".")), name))
    if not found:
        return os.path.join(sources, "esoui")
    return os.path.join(sources, max(found)[1])


def esoui_dir():
    return os.environ.get("APH_AUDIT_ESOUI") or latest_esoui(workspace_root())


def docs_file():
    return os.environ.get("APH_AUDIT_DOCS") or os.path.join(esoui_dir(), "ESOUIDocumentation.txt")


def reviewed_id64():
    pairs = {}
    for entry in (os.environ.get("APH_AUDIT_REVIEWED_ID64") or "").split(","):
        if ":" in entry:
            path, name = entry.rsplit(":", 1)
            pairs[(path, name)] = "listed in .eso-auditrc"
    return pairs


def docs_api_version(docs_path):
    try:
        with open(docs_path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = re.search(r"API Version (\d+)", line)
                if match:
                    return match.group(1)
    except OSError:
        pass
    return "current"
