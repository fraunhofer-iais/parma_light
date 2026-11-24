import json
import os
import shutil
import tempfile

from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.exceptions import HTTPException

from intern import msg
import intern.dbc as dbc
import intern.database as db
import intern.helper as h

import component.user as user
import component.node as n
import component.data as d
import component.workflow as wf
import component.run as run
import component.litegraph as lg
import component.external_orchestrator as eo

bp = Blueprint('main', __name__)


# -- Error handler -------------------------------------------------------------

@bp.app_errorhandler(Exception)
def handle_exception(e: Exception):
    # Keep Flask/Werkzeug HTTP errors (e.g. 404) intact.
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, dbc.ParmaException):
        try:
            return jsonify({"success": False, "error": msg.get_message_text(e.error_description)}), 200
        except e:
            jsonify({"success": False, "exception": f"Exception in errorhandler: {e}"}), 200
    return jsonify({"success": False, "exception": str(e)}), 200


# -- Frontend ------------------------------------------------------------------

@bp.route('/', methods=["GET"])
def index():
    """
    GET /
    Return the web frontend (static/index.html).
    """
    return current_app.send_static_file('index.html')

@bp.route('/config', methods=['POST'])
def config():
    """
    Return the ui config: the section "ui_config" of the yaml property file.

    Response JSON:
      {
        "success":   true,
        "ui_config": { <dict, key: ui component name, value: definition of form data> }
      }
    """
    ui_config = current_app.config['config']['ui_config']
    return jsonify({
        'ui_config': ui_config,
        'success': True
    })

# -- REST API misc -------------------------------------------------------------

@bp.route("/store", methods=["POST"])
def run_store():
    """
    Store all tables to disk.

    Response JSON:
      { "success": true }
    """
    db.store_tables()
    return jsonify({"success": True})

# -- REST API user -------------------------------------------------------------

@bp.route('/user/login', methods=['POST'])
def user_login():
    """
    POST /user/login
    Log in. The token returned must be sent as header "X-Auth-Token" with all other requests.

    Request JSON:
      { "name": "...", "password": "..." }

    Response JSON:
      { "success": true, "token": "..." }, or { "success": false, "error": "..." } if name or password are wrong
    """
    data = request.get_json()
    login_name = data.get('name', '').strip()
    password = data.get('password', '')
    token = user.login(login_name, password)
    return jsonify({"success": True, "token": token})


@bp.route('/user/logout', methods=['POST'])
def user_logout():
    """
    POST /user/logout
    Log out: the token becomes invalid. Succeeds without or with an unknown token, too.

    Request header:  X-Auth-Token: <token>

    Response JSON:
      { "success": true }
    """
    token = request.headers.get('X-Auth-Token')
    if token:
        user.logout(token)
    return jsonify({"success": True})


@bp.route('/user/change-password', methods=['POST'])
def user_change_password():
    """
    POST /user/change-password
    Change the password of the logged in user. The old password is checked, the new one must not be empty.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "old_password": "...", "new_password": "..." }

    Response JSON:
      { "success": true/false }
    """
    calling_user = _get_authenticated_user()
    data = request.get_json()
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')
    user.change_password(calling_user, old_pw, new_pw)
    return jsonify({"success": True})


@bp.route('/user/add', methods=['POST'])
def user_add():
    """
    POST /user/add
    Add one user. Only admins may do this. A user name can't be used twice.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "name": "...", "admin": true/false, "password": "..." }

    Response JSON:
      { "success": true, "hash": "<hash of the user>" }
    """
    calling_user = _get_authenticated_user()
    data = request.get_json()
    dbc.assert_true(bool(data["name"]), {"msg": "INVALID_NAME"})
    dbc.assert_true(bool(data["password"]), {"msg": "INVALID_PASSWORD"})
    result_hash = user.add(data, calling_user)
    return jsonify({"success": True, "hash": result_hash})


@bp.route('/user/upload', methods=['POST'])
def user_upload():
    """
    POST /user/upload
    Add one or more users, defined in an uploaded file. Only admins may do this.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "content": "<JSON, or one or more blocks 'user { \"name\": ..., \"admin\": ..., \"password\": ... };'>" }

    Response JSON:
      { "success": true/false, "hashes": [...], "count": n, ... }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    definitions = h.parse_upload_content(payload.get('content', '{}'), ["user", "User"])
    return _process_definitions(definitions, calling_user, {"user": user.add, "User": user.add})


@bp.route('/user/remove', methods=['POST'])
def user_remove():
    """
    POST /user/remove
    Remove a user. Only admins may do this. Admins can't remove themselves.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "name": "..." }

    Response JSON:
      { "success": true/false }
    """
    calling_user = _get_authenticated_user()
    data = request.get_json()
    user.remove(data.get("name", "").strip(), calling_user)
    return jsonify({"success": True})


# -- REST API data -------------------------------------------------------------

@bp.route('/data/list', methods=['POST'])
def data_list():
    """
    POST /data/list
    Return all data entries known to the backend.

    Request header:  X-Auth-Token: <token>

    Response JSON:
      { "success": true, "data": [ {<data>, "_hash": "..."}, ... ] }
    """
    _get_authenticated_user()
    return jsonify({"success": True, "data": d.get_all_data()})


@bp.route('/data/upload', methods=['POST'])
def data_upload():
    """
    POST /data/upload
    Store a data definition or a list of data definitions. The file referenced by "user_path"
    is read on the server (relative paths are relative to the base directory).

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "content": "<JSON, or one or more blocks 'data { ... };'>" }

    Response JSON:
      { "success": true/false, "hash": "..." }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    definitions = h.parse_upload_content(payload.get('content', '{}'), "data")
    return _process_definitions(definitions, calling_user, {"data": d.add_data})


@bp.route('/data/upload-file', methods=['POST'])
def data_upload_file():
    """
    POST /data/upload-file
    Store a plain file (no metadata) as data. The data definition is generated:
      { "name": <file name, '.' replaced by '_', prefixed by '_' if it starts with a digit>,
        "type": "file", "storage": "platform", "hash": "true", "format": "any", "user_path": <file name> }
    Example: "1.data.csv" -> "_1_data_csv"
    If the optional form field "name" is given, it is used as data name (e.g. by an exported Snakefile, that
    stores outputs under the channel name like a run does).

    Request header:  X-Auth-Token: <token>
    Request: multipart/form-data with the part "file" and the optional field "name"

    Response JSON:
      { "success": true/false, "hash": "...", "name": "..." }
    """
    calling_user = _get_authenticated_user()
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return jsonify({"success": False, "error": "no file uploaded (multipart part 'file' missing)"})
    file_name = os.path.basename(uploaded.filename.replace('\\', '/'))
    data_name = request.form.get('name') or file_name.replace('.', '_')
    if data_name[:1].isdigit():
        data_name = "_" + data_name  # data names must not start with a digit
    definition = {
        "name": data_name,
        "type": "file",
        "storage": "platform",
        "hash": "true",
        "format": "any",
        "user_path": file_name,
    }
    tmp_dir = tempfile.mkdtemp(prefix="parma_upload_")
    try:
        tmp_path = os.path.join(tmp_dir, "content")
        uploaded.save(tmp_path)
        data_hash = d.add_data(definition, calling_user, source_path=tmp_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return jsonify({"success": True, "hash": data_hash, "hashes": [data_hash], "count": 1,
                    "name": definition["name"]})


@bp.route('/data/content', methods=['POST'])
def data_content():
    """
    POST /data/content
    Return the content of a data entry of type "file" as download.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "hash": "..." }

    Response:
        the file (application/octet-stream), or JSON { "success": false, ... } on error
    """
    _get_authenticated_user()
    payload = request.get_json()
    hash_value = d.get_data_hash_by_referer({"hash": payload.get("hash", "").strip()})
    data_def = d.get_data_by_hash(hash_value)
    dbc.assert_true(data_def["type"] == "file",
                    {"msg": "DOWNLOAD_ONLY_FILES", "name": data_def["name"], "type": data_def["type"]})
    path = d.get_path_by_hash(hash_value)
    download_name = os.path.basename(data_def.get("user_path", "")) or data_def["name"]
    return send_file(os.path.abspath(path), as_attachment=True, download_name=download_name,
                     mimetype="application/octet-stream")


# -- REST API node -------------------------------------------------------------

@bp.route('/node/list', methods=['POST'])
def node_list():
    """
    POST /node/list
    Return all nodes known to the backend.

    Request header:  X-Auth-Token: <token>

    Only a summary of each node is returned, the complete node is returned by /node/get.

    Response JSON:
      { "success": true, "nodes": [ {"_hash", "name", "_version", "_date", "kind": "image"|"bash"|"nix"}, ... ] }
    """
    _get_authenticated_user()
    summaries = []
    for node in n.get_all_nodes():
        summary = _summary(node)
        summary["kind"] = next((kind for kind in ("image", "bash", "nix") if kind in node), "")
        summaries.append(summary)
    return jsonify({"success": True, "nodes": summaries})


def _summary(entry: dict) -> dict:
    """the fields of a stored entry shown in lists"""
    return {key: entry.get(key) for key in ("_hash", "name", "_version", "_date")}


def _referer_of(payload: dict) -> dict:
    """the referer of a get request: a hash, or name and version"""
    if payload.get("hash"):
        return {"hash": str(payload["hash"]).strip()}
    name = payload.get("name", "")
    version = payload.get("version")
    dbc.assert_true(bool(name), {"msg": "INVALID_NAME"})
    dbc.assert_true(version is not None, {"msg": "INVALID_VERSION"})
    return {"name": name, "version": str(version)}


def _get_entry(get_hash_by_referer, get_by_hash, keyword: str):
    """
    Common part of the routes /node/get, /workflow/get and /run/get.
    Request JSON: { "hash": "...", "export": true/false } or { "name": "...", "version": ..., "export": ... }
    export false: the complete stored entry, as "entry" and (for compatibility) as "<keyword>".
    export true: the upload text without internal fields.
    """
    _get_authenticated_user()
    payload = request.get_json() or {}
    hash_value = get_hash_by_referer(_referer_of(payload))
    entry = dict(get_by_hash(hash_value), _hash=hash_value)
    if not payload.get("export"):
        return jsonify({"success": True, "entry": entry, keyword: entry})
    filename = f"{entry.get('name', keyword)}_{entry.get('_version', 1)}.txt"
    return jsonify({"success": True, "content": h.export_definition(keyword, entry), "filename": filename})


@bp.route('/node/get', methods=['POST'])
def node_get():
    """
    POST /node/get
    Return one node.

    Request header:  X-Auth-Token: <token>
    Request JSON:    { "hash": "...", "export": true/false } or { "name": "...", "version": ..., "export": ... }

    Response JSON:
      export false: { "success": true, "entry": {<node>, "_hash": "..."}, "node": <the same> }
      export true:  { "success": true, "content": "node { ... };", "filename": "<name>_<version>.txt" }
                    (without internal fields, can be uploaded again)
    """
    return _get_entry(n.get_node_hash_by_referer, n.get_node_by_hash, "node")


@bp.route('/node/delete', methods=['POST'])
def node_delete():
    """
    POST /node/delete
    Delete a node by its hash.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "hash": "..." }

    Response JSON:
        { "success": true/false }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    hash_value = payload.get('hash', '').strip()
    dbc.assert_true_system(bool(hash_value), "node hash darf nicht leer sein")
    n.delete_node(hash_value, calling_user)
    return jsonify({"success": True})


@bp.route('/node/upload', methods=['POST'])
def node_upload():
    """
    POST /node/upload
    Store a node or a list of nodes in the datastore.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "content": "<JSON (object or list), or one or more blocks 'node { ... };'>" }

    Response JSON:
      { "success": true/false, "hash": "<hash of the last node>", "hashes": [...], "count": n, ... }
      see _process_definitions()
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    content  = payload.get('content', '{}')
    definitions = h.parse_upload_content(content, "node")
    return _process_definitions(definitions, calling_user, {"node": n.add_node})


@bp.route('/node/download', methods=['POST'])
def node_download():
        """
        POST /node/download
        Download a node by referer and return it as JSON content.

        Request header:  X-Auth-Token: <token>
        Request JSON:
            {
                "referer": {"name": "...", "version": "<number or latest>"}
            }
        The referer is a user input (a file selected by the user): a hash is not accepted.

        Response JSON:
            { "success": true/false, "content": "<node json>", ... }
        """
        _get_authenticated_user()
        payload = request.get_json() or {}
        referer = payload.get("referer", {})
        h.validate_user_input(referer, "name_version")
        hash_value = n.get_node_hash_by_referer(referer)
        node_def = n.get_node_by_hash(hash_value)
        return jsonify({"success": True, "content": json.dumps(node_def, indent=2, ensure_ascii=False)})


@bp.route('/nodes/litegraph', methods=['POST'])
def nodes_litegraph():
    """
    POST /nodes/litegraph
    Return all node definitions and all workflows transformed to the format expected by
    the JavaScript function register_parma_node(title, hierarchy, description, inputs, outputs).
    Workflows can be used as sub workflows in the editor, their hierarchy is "wf/<name>:<version>".

    Request header:  X-Auth-Token: <token>

    Response JSON:
      {
        "success": true,
        "nodes": [
          {
            "title":       "<name>:<version>",
            "hierarchy":   "parma/<name>:<version>",
            "description": "<execution-type summary>",
            "inputs":      [["<channel>", "<type>"], ...],
            "outputs":     [["<channel>", "<type>"], ...]
          },
          ...
        ],
        "workflows": [ <same structure, "hierarchy": "wf/<name>:<version>", "description": "workflow"> ]
      }
    """
    _get_authenticated_user()
    result = []
    for node in n.get_all_nodes():
        name    = node.get("name", "")
        version = node.get("_version", 1)
        if "image" in node:
            img = node["image"]
            description = f"image: {img.get('name', '')}:{img.get('version', '')}"
        elif "bash" in node:
            description = "bash"
        elif "nix" in node:
            description = "nix"
        else:
            description = ""
        inputs  = [[ch, meta.get("type", "")] for ch, meta in node.get("input",  {}).items()]
        outputs = [[ch, meta.get("type", "")] for ch, meta in node.get("output", {}).items()]
        result.append({
            "title":       f"{name}:{version}",
            "hierarchy":   f"{lg.PARMA_PREFIX}{name}:{version}",
            "description": description,
            "inputs":      inputs,
            "outputs":     outputs,
        })
    workflows = []
    for workflow_def in wf.get_all_workflows():
        name    = workflow_def.get("name", "")
        version = workflow_def.get("_version", 1)
        workflows.append({
            "title":       f"{name}:{version}",
            "hierarchy":   f"{lg.WF_PREFIX}{name}:{version}",
            "description": "workflow",
            "inputs":      [[ch, meta.get("type", "")] for ch, meta in workflow_def.get("input",  {}).items()],
            "outputs":     [[ch, meta.get("type", "")] for ch, meta in workflow_def.get("output", {}).items()],
        })
    return jsonify({"success": True, "nodes": result, "workflows": workflows})


# -- REST API workflow ---------------------------------------------------------

@bp.route('/workflow/list', methods=['POST'])
def workflow_list():
    """
    POST /workflow/list
    Return all workflows known to the backend.

    Request header:  X-Auth-Token: <token>

    Only a summary of each workflow is returned, the complete workflow is returned by /workflow/get.
    "inputs" are the names of the input channels: a workflow with inputs is a sub workflow.

    Response JSON:
      { "success": true, "workflows": [ {"_hash", "name", "_version", "_date", "inputs": [...]}, ... ] }
    """
    _get_authenticated_user()
    summaries = []
    for workflow_def in wf.get_all_workflows():
        summary = _summary(workflow_def)
        summary["inputs"] = list((workflow_def.get("input") or {}).keys())
        summaries.append(summary)
    return jsonify({"success": True, "workflows": summaries})


@bp.route('/workflow/get', methods=['POST'])
def workflow_get():
    """
    POST /workflow/get
    Return one workflow.

    Request header:  X-Auth-Token: <token>
    Request JSON:    { "hash": "...", "export": true/false } or { "name": "...", "version": ..., "export": ... }

    Response JSON:
      export false: { "success": true, "entry": {<workflow>, "_hash": "..."}, "workflow": <the same> }
      export true:  { "success": true, "content": "workflow { ... };", "filename": "<name>_<version>.txt" }
                    (without internal fields, can be uploaded again)
    """
    return _get_entry(wf.get_workflow_hash_by_referer, wf.get_workflow_by_hash, "workflow")


@bp.route('/workflow/delete', methods=['POST'])
def workflow_delete():
    """
    POST /workflow/delete
    Delete a workflow by its hash.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "hash": "..." }

    Response JSON:
        { "success": true/false }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    hash_value = payload.get('hash', '').strip()
    dbc.assert_true_system(bool(hash_value), "workflow hash darf nicht leer sein")
    wf.delete_workflow(hash_value, calling_user)
    return jsonify({"success": True})


@bp.route('/workflow/upload', methods=['POST'])
def workflow_upload():
    """
    POST /workflow/upload
    Store a workflow or a list of workflows in the datastore. Refinements of workflows are accepted too.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "content": "<JSON (object or list), or one or more blocks 'workflow { ... };' or 'refine { ... };'>" }

    Response JSON:
      { "success": true/false, "hash": "<hash of the last workflow>", "hashes": [...], "count": n, ... }
      see _process_definitions()
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    content  = payload.get('content', '{}')
    definitions = h.parse_upload_content(content, ["workflow", "refine"])
    return _process_definitions(definitions, calling_user, {"workflow": wf.add_workflow, "refine": wf.refine_workflow})


@bp.route('/workflow/download', methods=['POST'])
def workflow_download():
        """
        POST /workflow/download
        Download a workflow by referer and return it as JSON content.

        Request header:  X-Auth-Token: <token>
        Request JSON:
            {
                "referer": {"name": "...", "version": "<number or latest>"}
            }
        The referer is a user input (a file selected by the user): a hash is not accepted.

        Response JSON:
            { "success": true/false, "content": "<workflow json>", ... }
        """
        _get_authenticated_user()
        payload = request.get_json() or {}
        referer = payload.get("referer", {})
        h.validate_user_input(referer, "name_version")
        hash_value = wf.get_workflow_hash_by_referer(referer)
        workflow_def = wf.get_workflow_by_hash(hash_value)
        return jsonify({"success": True, "content": json.dumps(workflow_def, indent=2, ensure_ascii=False)})


@bp.route('/workflow/litegraph', methods=['POST'])
def workflow_litegraph():
    """
    POST /workflow/litegraph
    Return a stored workflow converted to a serialized LiteGraph graph for the workflow editor.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "hash": "..." } or { "name": "...", "version": ... }

    Response JSON:
        { "success": true/false, "hash": "...", "name": "<workflow name>", "version": <version>,
          "graph": { <litegraph graph> } }
    """
    _get_authenticated_user()
    payload = request.get_json() or {}
    hash_value = wf.get_workflow_hash_by_referer(_referer_of(payload))
    workflow_def = wf.get_workflow_by_hash(hash_value)
    graph = lg.workflow_to_litegraph(workflow_def)
    return jsonify({"success": True, "hash": hash_value, "name": workflow_def["name"],
                    "version": workflow_def.get("_version"), "graph": graph})


def _name_version_referer(payload: dict) -> dict:
    """the referer of a request, that requires name and version (a hash is not accepted)"""
    dbc.assert_true(bool(payload.get("name")), {"msg": "INVALID_NAME"})
    dbc.assert_true(payload.get("version") not in (None, ""), {"msg": "INVALID_VERSION"})
    referer = {"name": str(payload["name"]), "version": str(payload["version"])}
    h.validate_user_input(referer, "name_version")
    return referer


@bp.route('/workflow/snakemake_gen', methods=['POST'])
def workflow_snakemake_gen():
    """
    POST /workflow/snakemake_gen
    Generate a Snakefile that executes a stored workflow with Snakemake (only workflows with docker nodes)
    and store it as data named "snakefile_<workflow name>_<workflow version>" (for "latest" the version
    found is used). The Snakefile is not returned, get it from the data store (e.g. /data/content) or
    run it with /workflow/snakemake_run. A run of the Snakefile stores its run record with the name
    "run_snakefile_<workflow name>_<workflow version>" and the snakemake log as "_log_snakemake".

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "name": "<workflow name>", "version": "<number or latest>" }
    Name and version are required, a hash is not accepted.

    Response JSON:
        { "success": true/false, "hash": "<hash of the data>", "name": "snakefile_<name>_<version>",
          "version": <version of the data>, "workflow": { "hash": "...", "name": "...", "version": <version> } }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json() or {}
    workflow_hash = wf.get_workflow_hash_by_referer(_name_version_referer(payload))
    workflow_def = wf.get_workflow_by_hash(workflow_hash)
    workflow_version = workflow_def.get("_version", 1)
    data_name = f"snakefile_{workflow_def['name']}_{workflow_version}"
    content = eo.parma2snakemake({"hash": workflow_hash}, run_name=f"run_{data_name}")

    definition = {"name": data_name, "type": "file", "storage": "platform", "hash": "true",
                  "format": "any", "user_path": data_name}
    tmp_dir = tempfile.mkdtemp(prefix="parma_snakefile_")
    try:
        tmp_path = os.path.join(tmp_dir, "Snakefile")
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        data_hash = d.add_data(definition, calling_user, source_path=tmp_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return jsonify({"success": True, "hash": data_hash, "name": data_name,
                    "version": d.get_data_by_hash(data_hash).get("_version"),
                    "workflow": {"hash": workflow_hash, "name": workflow_def["name"], "version": workflow_version}})


@bp.route('/workflow/snakemake_run', methods=['POST'])
def workflow_snakemake_run():
    """
    POST /workflow/snakemake_run
    Run a Snakefile stored as data (see /workflow/snakemake_gen) with Snakemake on the backend machine. The
    request returns when Snakemake has finished. The Snakefile stores the outputs and the run record (with the
    run log) by the REST API, using the token of this request. Thus the backend must serve requests in parallel
    (server "waitress"; not "development_debug"). Not available if the backend runs in a container.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "name": "<name of the Snakefile data>", "version": "<number or latest>", "cores": <number, default 1> }
    Name and version are required, a hash is not accepted.

    Response JSON:
        { "success": true/false, "exit_code": <exit code of snakemake>,
          "run": { "hash": "...", "name": "...", "version": <version> } or null if no run record was stored,
          "output": [ "<last lines of the snakemake output>", ... ] }
    """
    _get_authenticated_user()
    payload = request.get_json() or {}
    referer = _name_version_referer(payload)
    cores = payload.get("cores", 1)
    dbc.assert_true(isinstance(cores, int) and not isinstance(cores, bool) and cores >= 1,
                    {"msg": "SYSTEM_ERROR", "details": f"\"cores\" must be a number >= 1, not {cores!r}"})
    port = (current_app.config.get('config') or {}).get('server', {}).get('port', 8080)
    result = eo.run_snakefile(referer, cores, f"http://127.0.0.1:{port}", request.headers.get('X-Auth-Token'))
    return jsonify(result)


@bp.route('/workflow/run', methods=['POST'])
def workflow_run():
    """
    POST /workflow/run
    Runs a stored workflow. The request returns when the run has finished.
    The run gets the name of the workflow (a new version for every run).

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "hash": "<hash of the workflow>" }

    Response JSON:
        { "success": true/false, "hash": "<hash of the run>", "name": "...", "version": <version>, "log": [ "...", ... ] }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    hash_value = wf.get_workflow_hash_by_referer({"hash": payload.get("hash", "").strip()})
    workflow_def = wf.get_workflow_by_hash(hash_value)
    # the run definition is validated like a user input: it refers to the workflow by name and version
    workflow_referer = {"name": workflow_def["name"], "version": str(workflow_def["_version"])}
    run_hash = run.run_workflow({"name": workflow_def["name"], "workflow": workflow_referer}, {}, calling_user)
    run_def = run.get_run_by_hash(run_hash)
    return jsonify({"success": True, "hash": run_hash, "name": run_def["name"],
                    "version": run_def.get("_version"), "log": run_def.get("_log", [])})


@bp.route('/run/list', methods=['POST'])
def run_list():
    """
    POST /run/list
    Return all runs known to the backend.

    Request header:  X-Auth-Token: <token>

    Only a summary of each run is returned, the complete run is returned by /run/get.

    Response JSON:
      { "success": true, "runs": [ {"_hash", "name", "_version", "_date"}, ... ] }
    """
    _get_authenticated_user()
    return jsonify({"success": True, "runs": [_summary(r) for r in run.get_all_runs()]})


@bp.route('/run/data', methods=['POST'])
def run_data():
    """
    POST /run/data
    Return the data entries of a run: those referenced in the metadata of the run under "_channel_bindings"
    (channel -> hash of data). Each entry gets the channel name as "_channel". If a data entry doesn't
    exist anymore (e.g. deleted), only "_channel", "_hash" and "_missing": true are returned.

    Request header:  X-Auth-Token: <token>
    Request JSON:    { "hash": "..." } or { "name": "...", "version": ... }

    Response JSON:
      { "success": true, "name": "<run name>", "version": <run version>,
        "data": [ {<data>, "_hash": "...", "_channel": "..."}, ... ] }
    """
    _get_authenticated_user()
    payload = request.get_json() or {}
    run_entry = run.get_run_by_hash(run.get_run_hash_by_referer(_referer_of(payload)))
    entries = []
    for channel, data_hash in (run_entry.get("_channel_bindings") or {}).items():
        if data_hash in db._data:
            entries.append(dict(db._data[data_hash], _hash=data_hash, _channel=channel))
        else:
            entries.append({"_channel": channel, "_hash": data_hash, "_missing": True})
    return jsonify({"success": True, "name": run_entry.get("name"), "version": run_entry.get("_version"),
                    "data": entries})


@bp.route('/run/get', methods=['POST'])
def run_get():
    """
    POST /run/get
    Return one run. Runs can't be uploaded, thus "export" is ignored: the complete entry is returned.

    Request header:  X-Auth-Token: <token>
    Request JSON:    { "hash": "..." } or { "name": "...", "version": ... }

    Response JSON:
      { "success": true, "entry": {<run>, "_hash": "..."}, "run": <the same> }
    """
    _get_authenticated_user()
    payload = request.get_json() or {}
    hash_value = run.get_run_hash_by_referer(_referer_of(payload))
    entry = dict(run.get_run_by_hash(hash_value), _hash=hash_value)
    return jsonify({"success": True, "entry": entry, "run": entry})


@bp.route('/run/upload', methods=['POST'])
def run_upload():
    """
    POST /run/upload
    Execute all runs defined in the uploaded content, one after the other. The request returns when the
    last run has finished. Processing stops at the first run that fails.

    Request header:  X-Auth-Token: <token>
    Request JSON:
      { "content": "<run definitions: JSON or blocks like 'run { \"name\": ..., \"workflow\": {<referer>} };'>" }

    Response JSON:
      { "success": true/false, "hash": "<hash of the last run>", "hashes": [...], "count": n, ... }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    content = payload.get('content', '{}')
    definitions = h.parse_upload_content(content, "run")
    return _process_definitions(definitions, calling_user,
                                {"run": lambda run_def, user: run.run_workflow(run_def, {}, user)})


@bp.route('/run/register', methods=['POST'])
def run_register():
    """
    POST /run/register
    Store the run record of a workflow executed by an external orchestrator (e.g. an exported Snakefile, see
    /workflow/snakemake_gen and /workflow/snakemake_run). The record looks like the record of a run executed
    by the backend ("_executor" is "builtin" there). The log of the orchestrator itself is stored as
    "_log_<executor>" (e.g. "_log_snakemake"). The data written by the run must have been stored before
    (e.g. by /data/upload-file). The tables are persisted immediately.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "workflow": { "hash": "<hash of the workflow>" }, "success": true/false, "log": [ "...", ... ],
          "channel_bindings": { "<channel>": "<hash of data>", ... }, "executor": "snakemake",
          "name": "<run name, optional, default: the workflow name>",
          "executor_log": [ "<line of the orchestrator log>", ... ] (optional) }

    Response JSON:
        { "success": true/false, "hash": "<hash of the run>", "name": "...", "version": <version> }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json() or {}
    workflow_referer = payload.get("workflow") or {}
    dbc.assert_true(isinstance(workflow_referer, dict) and workflow_referer.get("hash"), {"msg": "INVALID_COMMAND"})
    workflow_hash = wf.get_workflow_hash_by_referer({"hash": str(workflow_referer["hash"]).strip()})
    run_hash = run.register_external_run(workflow_hash, payload.get("success"), payload.get("log", []),
                                         payload.get("channel_bindings", {}), str(payload.get("executor", "snakemake")),
                                         calling_user, run_name=payload.get("name"),
                                         executor_log=payload.get("executor_log"))
    run_def = run.get_run_by_hash(run_hash)
    return jsonify({"success": True, "hash": run_hash, "name": run_def["name"], "version": run_def.get("_version")})


@bp.route('/workflow/save', methods=['POST'])
def workflow_save():
    """
    POST /workflow/save
    Convert a LiteGraph graph from the workflow editor to the backend format and store it as workflow.
    If a workflow with this name exists, a new version is created.

    Request header:  X-Auth-Token: <token>
    Request JSON:
        { "name": "<workflow name>", "graph": { <serialized litegraph graph> } }

    Response JSON:
        { "success": true/false, "hash": "...", "version": <version> }
    """
    calling_user = _get_authenticated_user()
    payload = request.get_json()
    workflow_def = lg.litegraph_to_workflow(payload.get("name", "").strip(), payload.get("graph") or {})
    hash_value = wf.add_workflow(workflow_def, calling_user)
    return jsonify({"success": True, "hash": hash_value, "version": wf.get_workflow_by_hash(hash_value).get("_version")})


# -- helper --------------------------------------------------------------------

def _get_authenticated_user() -> str:
    """
    Checks the X-Auth-Token header to to authenticate the user. Raise error if missing or invalid.

    Returns:
        the name of the authenticated user
    """
    token = request.headers.get('X-Auth-Token')
    dbc.assert_true(bool(token), {"msg": "TOKEN_INVALID"})
    return user.get_user_hash_from_session_token(token)


def _process_definitions(definitions: list, calling_user: str, handlers: dict):
    """
    Stores a list of uploaded definitions (data, nodes, workflows, refinements, ...) one after the other.
    Processing stops at the first error. Definitions stored before remain stored, the response says which.

    Args:
        definitions (list): (keyword, definition) pairs, see helper.parse_upload_content().
        calling_user (str): The user performing the operation.
        handlers (dict): keyword -> function called with (definition, calling_user), returning a hash.

    Returns:
        Response: A Flask JSON response
            success: { "success": true, "hash": "<hash of the last definition>", "hashes": [...], "count": n }
            error:   { "success": false, "error": "<text>", "hashes": [<hashes stored before the error>], "count": n }
    """
    if not definitions:
        return jsonify({"success": False, "error": "the uploaded file contains no definitions", "hashes": [], "count": 0})
    hashes = []
    for index, (keyword, definition) in enumerate(definitions, start=1):
        try:
            hashes.append(handlers[keyword](definition, calling_user))
        except Exception as e:
            if isinstance(e, dbc.ParmaException):
                reason = msg.get_message_text(e.error_description)
            else:
                reason = str(e)
            reason = reason.rstrip(". ")
            name = definition.get("name", "?") if isinstance(definition, dict) else "?"
            error = (f"{keyword} {index} of {len(definitions)} (name \"{name}\") failed: {reason}. "
                     f"{len(hashes)} definition(s) stored before.")
            return jsonify({"success": False, "error": error, "hashes": hashes, "count": len(definitions)})
    return jsonify({"success": True, "hash": hashes[-1], "hashes": hashes, "count": len(definitions)})
