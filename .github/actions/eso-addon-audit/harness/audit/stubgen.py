import os
import re
import sys

TYPE_CODES = {"integer": "i", "number": "i", "luaindex": "i", "id64": "i", "bool": "b", "string": "s"}


def return_codes(line):
    codes = []
    for match in re.finditer(r"\*(\[[^\]]*\]|[a-z0-9_]+)(:nilable)?\*", line):
        kind, nilable = match.group(1), match.group(2)
        if nilable:
            codes.append("n")
        elif kind.startswith("["):
            codes.append("i")
        else:
            codes.append(TYPE_CODES.get(kind, "o"))
    return "".join(codes)


def parse_docs(path):
    constants, funcs, methods = [], {}, {}
    section = None
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("h2. "):
            section = line[4:]
            continue
        if section == "Events":
            match = re.match(r"\* (EVENT_[A-Z0-9_]+)", line)
            if match:
                constants.append(match.group(1))
            continue
        if section == "Global Variables":
            match = re.match(r"\* ([A-Z][A-Z0-9_]+)$", line)
            if match:
                constants.append(match.group(1))
            continue
        match = re.match(r"\* ([A-Za-z0-9_]+)(?: \*[a-z]+\*)?\s*\(", line)
        if not match:
            continue
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        codes = return_codes(following) if following.startswith("** _Returns:_") else ""
        if section == "Game API" or section == "VM Functions":
            funcs.setdefault(match.group(1), codes)
        elif section == "Object API":
            methods.setdefault(match.group(1), codes)
            funcs.setdefault(match.group(1), codes)
    return constants, funcs, methods


def lua_globals(source_root):
    names, values = set(), {}
    define = re.compile(r"^(?:function\s+([A-Za-z_][A-Za-z0-9_]*)\s*[(.:]|([A-Za-z_][A-Za-z0-9_]*)\s*=[^=])")
    nested = re.compile(r"^\s+([A-Z][A-Z0-9_]{2,})\s*=[^=]")
    inner_function = re.compile(r"^\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*[(.:]")
    literal = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?|\"[^\"]*\"|true|false)\s*(?:--.*)?$")
    for root, _dirs, files in os.walk(source_root):
        for name in files:
            if not name.endswith(".lua"):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = define.match(line)
                    if match:
                        names.add(match.group(1) or match.group(2))
                        constant = literal.match(line.strip()) if not line[:1].isspace() else None
                        if constant:
                            values.setdefault(constant.group(1), constant.group(2))
                        continue
                    match = inner_function.match(line) or nested.match(line)
                    if match:
                        names.add(match.group(1))
    return names, values


def lua_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    docs, source_root, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    constants, funcs, methods = parse_docs(docs)
    source_names, source_values = lua_globals(source_root)
    source_names = source_names - set(funcs) - set(constants)
    with open(out_path, "w", encoding="utf-8") as out:
        out.write("ESO_CONSTANTS = {\n")
        for number, name in enumerate(sorted(set(constants)), 1):
            out.write("\t%s = %d,\n" % (name, number))
        out.write("}\nESO_FUNCS = {\n")
        for name in sorted(funcs):
            out.write("\t[%s] = %s,\n" % (lua_string(name), lua_string(funcs[name])))
        out.write("}\nESO_METHODS = {\n")
        for name in sorted(methods):
            out.write("\t[%s] = %s,\n" % (lua_string(name), lua_string(methods[name])))
        out.write("}\nESO_LUA_VALUES = {\n")
        for name in sorted(source_values):
            if name not in funcs and name not in constants:
                out.write("\t[%s] = %s,\n" % (lua_string(name), source_values[name]))
        out.write("}\nESO_LUA_GLOBALS = {\n")
        for name in sorted(source_names):
            out.write("\t[%s] = true,\n" % lua_string(name))
        out.write("}\n")
    print("STUBS OK: %d constants, %d functions, %d methods, %d UI globals" % (len(set(constants)), len(funcs), len(methods), len(source_names)))


if __name__ == "__main__":
    main()
