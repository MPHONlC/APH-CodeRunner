import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_env

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = audit_env.projects_root()
TARGETS = audit_env.targets()
ALWAYS_ON = {"SI_KEYBINDINGS_LAYER_GENERAL", "SI_KEYBINDINGS_LAYER_USER_INTERFACE_SHORTCUTS"}


def binding_files():
    for target in TARGETS:
        for root, _dirs, files in os.walk(os.path.join(PROJECTS, target)):
            for name in files:
                if name.lower() == "bindings.xml":
                    yield os.path.join(root, name)


def main():
    problems = []
    for path in binding_files():
        text = open(path, encoding="utf-8", errors="replace").read()
        for layer in re.finditer(r'<Layer\s+name="([^"]+)"(.*?)</Layer>', text, re.S):
            if layer.group(1) not in ALWAYS_ON:
                continue
            for action in re.finditer(r'<Action\s+name="([^"]+)"[^>]*inheritsBindFrom="([^"]+)"', layer.group(2)):
                problems.append("%s: %s inherits %s inside %s, so it shadows the game's own use of that key everywhere"
                                % (os.path.relpath(path, PROJECTS), action.group(1), action.group(2), layer.group(1)))

    if problems:
        print("BINDINGS CHECK FAILED:")
        for line in problems:
            print("  " + line)
        return 1
    print("BINDINGS CHECK OK: no inherited UI shortcut sits in an always-on layer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
