"""
Generates the API reference of the backend: resources/generated/API-REFERENCE.md

- the REST endpoints: taken from the Flask routes (app.url_map) and the docstrings of the route functions.
- the definitions (user, data, node, workflow, refine, run): taken from the JSON schema
  intern/schema-def-for-user-commands.json

The semantics (design decisions, if nodes, lazy evaluation, ...) are described by hand in resources/APIDOC.md.

usage: python src/parma/apidoc.py           (re)generates the file
       python src/parma/apidoc.py --check   exit code 1 if the file is not up to date (nothing is written)
"""
import inspect
import json
import re
import sys
from pathlib import Path

PARMA_DIR = Path(__file__).resolve().parent
REPO_DIR = PARMA_DIR.parent.parent
OUTPUT_FILE = REPO_DIR / "resources" / "generated" / "API-REFERENCE.md"
SCHEMA_FILE = PARMA_DIR / "intern" / "schema-def-for-user-commands.json"

if str(PARMA_DIR) not in sys.path:
    sys.path.insert(0, str(PARMA_DIR))

# the definitions users upload, in this order
USER_DEFINITIONS = [("user_def", "user"), ("data_def", "data"), ("node_def", "node"),
                    ("workflow_def", "workflow"), ("refine_def", "refine"), ("run_def", "run")]

# a docstring line like "Request JSON:", "Response:" or "Args:" begins the technical part (shown as preformatted text)
TECHNICAL_PART = re.compile(r"^(Request|Response)( \w+)?:|^(Returns|Args|Raises):")


def generate() -> str:
    """the complete content of API-REFERENCE.md"""
    lines = [
        "# API Reference of Parma-Light",
        "",
        "<!-- GENERATED FILE, DO NOT EDIT. Regenerate with: ./admin.sh apidoc -->",
        "",
        "This file is generated from the source code: the REST endpoints from the Flask routes and the docstrings",
        "in `src/parma/routes.py`, the definitions from the JSON schema",
        "`src/parma/intern/schema-def-for-user-commands.json`. The semantics are described in `resources/APIDOC.md`.",
        "",
    ]
    lines += _endpoints_section()
    lines += _definitions_section()
    return "\n".join(lines).rstrip("\n") + "\n"


# -- endpoints -----------------------------------------------------------------------------------------------

def _endpoints_section() -> list:
    from main import app  # creating the app has no side effects, the server is started by main()
    import routes
    authenticating = _authenticating_functions(routes)

    rules = sorted((rule for rule in app.url_map.iter_rules() if rule.endpoint != "static"), key=lambda r: r.rule)
    lines = ["## REST endpoints", "",
             "All endpoints except `GET /` use the method `POST` and return a JSON object with the key `success`.",
             "\"token\" means: the request needs the header `X-Auth-Token: <token>` (returned by `/user/login`).", "",
             "| Endpoint | Method | Token | Summary |", "| --- | --- | --- | --- |"]
    details = []
    for rule in rules:
        function = app.view_functions[rule.endpoint]
        methods = ", ".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        token = "yes" if function.__name__ in authenticating else "no"
        description, technical = _split_docstring(inspect.getdoc(function) or "", rule.rule)
        summary = _first_sentence(description) if description else "*(no docstring)*"
        anchor = _anchor(rule.rule)
        link = f"[`{rule.rule}`](#{anchor})" if anchor else f"`{rule.rule}`"
        lines.append(f"| {link} | {methods} | {token} | {_cell(summary)} |")
        details += [f"### `{rule.rule}`", ""]
        details += (description or ["*(no docstring)*"]) + [""]
        if technical:
            details += ["```text"] + technical + ["```", ""]
    return lines + [""] + details


def _authenticating_functions(module) -> set:
    """names of the functions of the module that call _get_authenticated_user, directly or by a helper"""
    sources = {name: inspect.getsource(f) for name, f in inspect.getmembers(module, inspect.isfunction)
               if f.__module__ == module.__name__}
    result = {"_get_authenticated_user"}
    changed = True
    while changed:
        changed = False
        for name, source in sources.items():
            body = source[source.index("def "):].split("\n", 1)[-1]  # without decorators and the def line
            if name not in result and any(f"{called}(" in body for called in result):
                result.add(name)
                changed = True
    return result


def _first_sentence(description: list) -> str:
    text = " ".join(line for line in description if line)
    match = re.search(r"^(.+?\.)(\s|$)", text)
    return match.group(1) if match else text


def _split_docstring(doc: str, route: str):
    """(description lines, technical lines). A first line 'POST /route' is dropped"""
    doc_lines = doc.splitlines()
    if doc_lines and doc_lines[0].strip().split()[-1:] == [route]:
        doc_lines = doc_lines[1:]
    split = next((i for i, line in enumerate(doc_lines) if TECHNICAL_PART.match(line.strip())), len(doc_lines))
    description = [line.strip() for line in doc_lines[:split]]
    while description and not description[-1]:
        description.pop()
    while description and not description[0]:
        description.pop(0)
    return description, [line.rstrip() for line in doc_lines[split:]]


def _anchor(route: str) -> str:
    """the anchor GitHub generates for the heading '### `<route>`'"""
    return "".join(c for c in route.lower() if c.isalnum() or c in "-_ ").replace(" ", "-")


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


# -- definitions ----------------------------------------------------------------------------------------------

def _definitions_section() -> list:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    user_def_names = [name for name, _ in USER_DEFINITIONS]
    lines = ["## Definitions", "",
             "The definitions uploaded by users. Keys must not start with `_`, these are reserved for the platform.",
             "References like [name_version](#name_version) point to the common definitions at the end.", ""]
    for def_name, keyword in USER_DEFINITIONS:
        lines += _render_object(f"{keyword} (`{def_name}`)", defs[def_name], level=3)
    lines += ["## Common definitions", ""]
    for def_name, definition in defs.items():
        if def_name in user_def_names:
            continue
        if definition.get("type") == "object":
            lines += _render_object(def_name, definition, level=3, anchor_name=def_name)
        else:
            lines += [f"### {def_name}", "", _value_description(definition), ""]
    return lines


def _render_object(title: str, schema: dict, level: int, anchor_name: str = None) -> list:
    """a heading, the description, a table of the keys and the alternatives. Inline objects get sub sections"""
    heading = "#" * level
    lines = [f"{heading} {anchor_name if anchor_name else title}", ""]
    if schema.get("description"):
        lines += [schema["description"], ""]
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    nested = []
    if properties:
        lines += ["| Key | Required | Value |", "| --- | --- | --- |"]
        for key, value in properties.items():
            sub_title = f"{title.split(' ')[0]}.{key}"
            lines.append(f"| `{key}` | {'yes' if key in required else 'no'} | {_cell(_value_description(value, sub_title, nested))} |")
        lines.append("")
    for pattern, value in (schema.get("patternProperties") or {}).items():
        lines += [f"Keys matching `{pattern}`: {_cell(_value_description(value, title + '.*', nested))}", ""]
    if schema.get("additionalProperties") is False and properties:
        lines += ["No other keys are allowed.", ""]
    alternatives = [variant.get("required") for variant in schema.get("oneOf", []) if variant.get("required")]
    if alternatives:
        lines += ["Exactly one of these alternatives: " +
                  " / ".join("{" + ", ".join(f"`{key}`" for key in keys) + "}" for keys in alternatives), ""]
    for sub_title, sub_schema in nested:
        lines += _render_object(sub_title, sub_schema, min(level + 1, 6))
    return lines


def _value_description(value: dict, title: str = "", nested: list = None) -> str:
    """a short text for the value of a key. Inline objects with keys are added to 'nested' (rendered later)"""
    if "$ref" in value:
        name = value["$ref"].split("/")[-1]
        text = f"[{name}](#{name.lower()})"
    elif "enum" in value:
        text = "one of " + ", ".join(f"`{json.dumps(v)}`" for v in value["enum"])
    elif value.get("type") == "object" and value.get("patternProperties"):
        (pattern, inner), = value["patternProperties"].items()
        text = f"object, keys matching `{pattern}`, values: {_value_description(inner, title + '.*', nested)}"
    elif value.get("type") == "object" and value.get("properties") and nested is not None:
        nested.append((title, value))
        text = f"object, see [{title}](#{_anchor(title)})"
    elif value.get("type") == "array":
        items = value.get("items", {})
        size = ""
        if "minItems" in value and value.get("minItems") == value.get("maxItems"):
            size = f" of {value['minItems']}"
        text = f"array{size} of {_value_description(items, title, nested)}"
    elif value.get("type") == "string" and "pattern" in value:
        text = f"string matching `{value['pattern']}`"
    elif value.get("type") == "string" and "minLength" in value:
        text = f"string, at least {value['minLength']} character(s)"
    elif "type" in value:
        text = str(value["type"])
    else:
        text = "any value"
    if value.get("description") and "$ref" not in value:
        text += f" - {value['description']}"
    return text


def main() -> int:
    content = generate()
    if "--check" in sys.argv[1:]:
        current = OUTPUT_FILE.read_text(encoding="utf-8") if OUTPUT_FILE.exists() else ""
        if current != content:
            print(f"{OUTPUT_FILE} is not up to date. Regenerate it with: ./admin.sh apidoc")
            return 1
        print(f"{OUTPUT_FILE} is up to date")
        return 0
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content, encoding="utf-8", newline="\n")
    print(f"generated {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
