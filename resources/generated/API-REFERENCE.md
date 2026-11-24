# API Reference of Parma-Light

<!-- GENERATED FILE, DO NOT EDIT. Regenerate with: ./admin.sh apidoc -->

This file is generated from the source code: the REST endpoints from the Flask routes and the docstrings
in `src/parma/routes.py`, the definitions from the JSON schema
`src/parma/intern/schema-def-for-user-commands.json`. The semantics are described in `resources/APIDOC.md`.

## REST endpoints

All endpoints except `GET /` use the method `POST` and return a JSON object with the key `success`.
"token" means: the request needs the header `X-Auth-Token: <token>` (returned by `/user/login`).

| Endpoint | Method | Token | Summary |
| --- | --- | --- | --- |
| `/` | GET | no | Return the web frontend (static/index.html). |
| [`/config`](#config) | POST | no | Return the ui config: the section "ui_config" of the yaml property file. |
| [`/data/content`](#datacontent) | POST | yes | Return the content of a data entry of type "file" as download. |
| [`/data/list`](#datalist) | POST | yes | Return all data entries known to the backend. |
| [`/data/upload`](#dataupload) | POST | yes | Store a data definition or a list of data definitions. |
| [`/data/upload-file`](#dataupload-file) | POST | yes | Store a plain file (no metadata) as data. |
| [`/node/delete`](#nodedelete) | POST | yes | Delete a node by its hash. |
| [`/node/download`](#nodedownload) | POST | yes | Download a node by referer and return it as JSON content. |
| [`/node/get`](#nodeget) | POST | yes | Return one node. |
| [`/node/list`](#nodelist) | POST | yes | Return all nodes known to the backend. |
| [`/node/upload`](#nodeupload) | POST | yes | Store a node or a list of nodes in the datastore. |
| [`/nodes/litegraph`](#nodeslitegraph) | POST | yes | Return all node definitions and all workflows transformed to the format expected by the JavaScript function register_parma_node(title, hierarchy, description, inputs, outputs). |
| [`/run/data`](#rundata) | POST | yes | Return the data entries of a run: those referenced in the metadata of the run under "_channel_bindings" (channel -> hash of data). |
| [`/run/get`](#runget) | POST | yes | Return one run. |
| [`/run/list`](#runlist) | POST | yes | Return all runs known to the backend. |
| [`/run/register`](#runregister) | POST | yes | Store the run record of a workflow executed by an external orchestrator (e.g. |
| [`/run/upload`](#runupload) | POST | yes | Execute all runs defined in the uploaded content, one after the other. |
| [`/store`](#store) | POST | no | Store all tables to disk. |
| [`/user/add`](#useradd) | POST | yes | Add one user. |
| [`/user/change-password`](#userchange-password) | POST | yes | Change the password of the logged in user. |
| [`/user/login`](#userlogin) | POST | no | Log in. |
| [`/user/logout`](#userlogout) | POST | no | Log out: the token becomes invalid. |
| [`/user/remove`](#userremove) | POST | yes | Remove a user. |
| [`/user/upload`](#userupload) | POST | yes | Add one or more users, defined in an uploaded file. |
| [`/workflow/delete`](#workflowdelete) | POST | yes | Delete a workflow by its hash. |
| [`/workflow/download`](#workflowdownload) | POST | yes | Download a workflow by referer and return it as JSON content. |
| [`/workflow/get`](#workflowget) | POST | yes | Return one workflow. |
| [`/workflow/list`](#workflowlist) | POST | yes | Return all workflows known to the backend. |
| [`/workflow/litegraph`](#workflowlitegraph) | POST | yes | Return a stored workflow converted to a serialized LiteGraph graph for the workflow editor. |
| [`/workflow/run`](#workflowrun) | POST | yes | Runs a stored workflow. |
| [`/workflow/save`](#workflowsave) | POST | yes | Convert a LiteGraph graph from the workflow editor to the backend format and store it as workflow. |
| [`/workflow/snakemake_gen`](#workflowsnakemake_gen) | POST | yes | Generate a Snakefile that executes a stored workflow with Snakemake (only workflows with docker nodes) and store it as data named "snakefile_<workflow name>_<workflow version>" (for "latest" the version found is used). |
| [`/workflow/snakemake_run`](#workflowsnakemake_run) | POST | yes | Run a Snakefile stored as data (see /workflow/snakemake_gen) with Snakemake on the backend machine. |
| [`/workflow/upload`](#workflowupload) | POST | yes | Store a workflow or a list of workflows in the datastore. |

### `/`

Return the web frontend (static/index.html).

### `/config`

Return the ui config: the section "ui_config" of the yaml property file.

```text
Response JSON:
  {
    "success":   true,
    "ui_config": { <dict, key: ui component name, value: definition of form data> }
  }
```

### `/data/content`

Return the content of a data entry of type "file" as download.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "hash": "..." }

Response:
    the file (application/octet-stream), or JSON { "success": false, ... } on error
```

### `/data/list`

Return all data entries known to the backend.

```text
Request header:  X-Auth-Token: <token>

Response JSON:
  { "success": true, "data": [ {<data>, "_hash": "..."}, ... ] }
```

### `/data/upload`

Store a data definition or a list of data definitions. The file referenced by "user_path"
is read on the server (relative paths are relative to the base directory).

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "content": "<JSON, or one or more blocks 'data { ... };'>" }

Response JSON:
  { "success": true/false, "hash": "..." }
```

### `/data/upload-file`

Store a plain file (no metadata) as data. The data definition is generated:
{ "name": <file name, '.' replaced by '_', prefixed by '_' if it starts with a digit>,
"type": "file", "storage": "platform", "hash": "true", "format": "any", "user_path": <file name> }
Example: "1.data.csv" -> "_1_data_csv"
If the optional form field "name" is given, it is used as data name (e.g. by an exported Snakefile, that
stores outputs under the channel name like a run does).

```text
Request header:  X-Auth-Token: <token>
Request: multipart/form-data with the part "file" and the optional field "name"

Response JSON:
  { "success": true/false, "hash": "...", "name": "..." }
```

### `/node/delete`

Delete a node by its hash.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "hash": "..." }

Response JSON:
    { "success": true/false }
```

### `/node/download`

Download a node by referer and return it as JSON content.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    {
        "referer": {"name": "...", "version": "<number or latest>"}
    }
The referer is a user input (a file selected by the user): a hash is not accepted.

Response JSON:
    { "success": true/false, "content": "<node json>", ... }
```

### `/node/get`

Return one node.

```text
Request header:  X-Auth-Token: <token>
Request JSON:    { "hash": "...", "export": true/false } or { "name": "...", "version": ..., "export": ... }

Response JSON:
  export false: { "success": true, "entry": {<node>, "_hash": "..."}, "node": <the same> }
  export true:  { "success": true, "content": "node { ... };", "filename": "<name>_<version>.txt" }
                (without internal fields, can be uploaded again)
```

### `/node/list`

Return all nodes known to the backend.

```text
Request header:  X-Auth-Token: <token>

Only a summary of each node is returned, the complete node is returned by /node/get.

Response JSON:
  { "success": true, "nodes": [ {"_hash", "name", "_version", "_date", "kind": "image"|"bash"|"nix"}, ... ] }
```

### `/node/upload`

Store a node or a list of nodes in the datastore.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "content": "<JSON (object or list), or one or more blocks 'node { ... };'>" }

Response JSON:
  { "success": true/false, "hash": "<hash of the last node>", "hashes": [...], "count": n, ... }
  see _process_definitions()
```

### `/nodes/litegraph`

Return all node definitions and all workflows transformed to the format expected by
the JavaScript function register_parma_node(title, hierarchy, description, inputs, outputs).
Workflows can be used as sub workflows in the editor, their hierarchy is "wf/<name>:<version>".

```text
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
```

### `/run/data`

Return the data entries of a run: those referenced in the metadata of the run under "_channel_bindings"
(channel -> hash of data). Each entry gets the channel name as "_channel". If a data entry doesn't
exist anymore (e.g. deleted), only "_channel", "_hash" and "_missing": true are returned.

```text
Request header:  X-Auth-Token: <token>
Request JSON:    { "hash": "..." } or { "name": "...", "version": ... }

Response JSON:
  { "success": true, "name": "<run name>", "version": <run version>,
    "data": [ {<data>, "_hash": "...", "_channel": "..."}, ... ] }
```

### `/run/get`

Return one run. Runs can't be uploaded, thus "export" is ignored: the complete entry is returned.

```text
Request header:  X-Auth-Token: <token>
Request JSON:    { "hash": "..." } or { "name": "...", "version": ... }

Response JSON:
  { "success": true, "entry": {<run>, "_hash": "..."}, "run": <the same> }
```

### `/run/list`

Return all runs known to the backend.

```text
Request header:  X-Auth-Token: <token>

Only a summary of each run is returned, the complete run is returned by /run/get.

Response JSON:
  { "success": true, "runs": [ {"_hash", "name", "_version", "_date"}, ... ] }
```

### `/run/register`

Store the run record of a workflow executed by an external orchestrator (e.g. an exported Snakefile, see
/workflow/snakemake_gen and /workflow/snakemake_run). The record looks like the record of a run executed
by the backend ("_executor" is "builtin" there). The log of the orchestrator itself is stored as
"_log_<executor>" (e.g. "_log_snakemake"). The data written by the run must have been stored before
(e.g. by /data/upload-file). The tables are persisted immediately.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "workflow": { "hash": "<hash of the workflow>" }, "success": true/false, "log": [ "...", ... ],
      "channel_bindings": { "<channel>": "<hash of data>", ... }, "executor": "snakemake",
      "name": "<run name, optional, default: the workflow name>",
      "executor_log": [ "<line of the orchestrator log>", ... ] (optional) }

Response JSON:
    { "success": true/false, "hash": "<hash of the run>", "name": "...", "version": <version> }
```

### `/run/upload`

Execute all runs defined in the uploaded content, one after the other. The request returns when the
last run has finished. Processing stops at the first run that fails.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "content": "<run definitions: JSON or blocks like 'run { "name": ..., "workflow": {<referer>} };'>" }

Response JSON:
  { "success": true/false, "hash": "<hash of the last run>", "hashes": [...], "count": n, ... }
```

### `/store`

Store all tables to disk.

```text
Response JSON:
  { "success": true }
```

### `/user/add`

Add one user. Only admins may do this. A user name can't be used twice.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "name": "...", "admin": true/false, "password": "..." }

Response JSON:
  { "success": true, "hash": "<hash of the user>" }
```

### `/user/change-password`

Change the password of the logged in user. The old password is checked, the new one must not be empty.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "old_password": "...", "new_password": "..." }

Response JSON:
  { "success": true/false }
```

### `/user/login`

Log in. The token returned must be sent as header "X-Auth-Token" with all other requests.

```text
Request JSON:
  { "name": "...", "password": "..." }

Response JSON:
  { "success": true, "token": "..." }, or { "success": false, "error": "..." } if name or password are wrong
```

### `/user/logout`

Log out: the token becomes invalid. Succeeds without or with an unknown token, too.

```text
Request header:  X-Auth-Token: <token>

Response JSON:
  { "success": true }
```

### `/user/remove`

Remove a user. Only admins may do this. Admins can't remove themselves.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "name": "..." }

Response JSON:
  { "success": true/false }
```

### `/user/upload`

Add one or more users, defined in an uploaded file. Only admins may do this.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "content": "<JSON, or one or more blocks 'user { "name": ..., "admin": ..., "password": ... };'>" }

Response JSON:
  { "success": true/false, "hashes": [...], "count": n, ... }
```

### `/workflow/delete`

Delete a workflow by its hash.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "hash": "..." }

Response JSON:
    { "success": true/false }
```

### `/workflow/download`

Download a workflow by referer and return it as JSON content.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    {
        "referer": {"name": "...", "version": "<number or latest>"}
    }
The referer is a user input (a file selected by the user): a hash is not accepted.

Response JSON:
    { "success": true/false, "content": "<workflow json>", ... }
```

### `/workflow/get`

Return one workflow.

```text
Request header:  X-Auth-Token: <token>
Request JSON:    { "hash": "...", "export": true/false } or { "name": "...", "version": ..., "export": ... }

Response JSON:
  export false: { "success": true, "entry": {<workflow>, "_hash": "..."}, "workflow": <the same> }
  export true:  { "success": true, "content": "workflow { ... };", "filename": "<name>_<version>.txt" }
                (without internal fields, can be uploaded again)
```

### `/workflow/list`

Return all workflows known to the backend.

```text
Request header:  X-Auth-Token: <token>

Only a summary of each workflow is returned, the complete workflow is returned by /workflow/get.
"inputs" are the names of the input channels: a workflow with inputs is a sub workflow.

Response JSON:
  { "success": true, "workflows": [ {"_hash", "name", "_version", "_date", "inputs": [...]}, ... ] }
```

### `/workflow/litegraph`

Return a stored workflow converted to a serialized LiteGraph graph for the workflow editor.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "hash": "..." } or { "name": "...", "version": ... }

Response JSON:
    { "success": true/false, "hash": "...", "name": "<workflow name>", "version": <version>,
      "graph": { <litegraph graph> } }
```

### `/workflow/run`

Runs a stored workflow. The request returns when the run has finished.
The run gets the name of the workflow (a new version for every run).

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "hash": "<hash of the workflow>" }

Response JSON:
    { "success": true/false, "hash": "<hash of the run>", "name": "...", "version": <version>, "log": [ "...", ... ] }
```

### `/workflow/save`

Convert a LiteGraph graph from the workflow editor to the backend format and store it as workflow.
If a workflow with this name exists, a new version is created.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "name": "<workflow name>", "graph": { <serialized litegraph graph> } }

Response JSON:
    { "success": true/false, "hash": "...", "version": <version> }
```

### `/workflow/snakemake_gen`

Generate a Snakefile that executes a stored workflow with Snakemake (only workflows with docker nodes)
and store it as data named "snakefile_<workflow name>_<workflow version>" (for "latest" the version
found is used). The Snakefile is not returned, get it from the data store (e.g. /data/content) or
run it with /workflow/snakemake_run. A run of the Snakefile stores its run record with the name
"run_snakefile_<workflow name>_<workflow version>" and the snakemake log as "_log_snakemake".

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "name": "<workflow name>", "version": "<number or latest>" }
Name and version are required, a hash is not accepted.

Response JSON:
    { "success": true/false, "hash": "<hash of the data>", "name": "snakefile_<name>_<version>",
      "version": <version of the data>, "workflow": { "hash": "...", "name": "...", "version": <version> } }
```

### `/workflow/snakemake_run`

Run a Snakefile stored as data (see /workflow/snakemake_gen) with Snakemake on the backend machine. The
request returns when Snakemake has finished. The Snakefile stores the outputs and the run record (with the
run log) by the REST API, using the token of this request. Thus the backend must serve requests in parallel
(server "waitress"; not "development_debug"). Not available if the backend runs in a container.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
    { "name": "<name of the Snakefile data>", "version": "<number or latest>", "cores": <number, default 1> }
Name and version are required, a hash is not accepted.

Response JSON:
    { "success": true/false, "exit_code": <exit code of snakemake>,
      "run": { "hash": "...", "name": "...", "version": <version> } or null if no run record was stored,
      "output": [ "<last lines of the snakemake output>", ... ] }
```

### `/workflow/upload`

Store a workflow or a list of workflows in the datastore. Refinements of workflows are accepted too.

```text
Request header:  X-Auth-Token: <token>
Request JSON:
  { "content": "<JSON (object or list), or one or more blocks 'workflow { ... };' or 'refine { ... };'>" }

Response JSON:
  { "success": true/false, "hash": "<hash of the last workflow>", "hashes": [...], "count": n, ... }
  see _process_definitions()
```

## Definitions

The definitions uploaded by users. Keys must not start with `_`, these are reserved for the platform.
References like [name_version](#name_version) point to the common definitions at the end.

### user (`user_def`)

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [alphanumeric_name](#alphanumeric_name) |
| `admin` | yes | boolean |
| `password` | yes | string, at least 1 character(s) |

No other keys are allowed.

### data (`data_def`)

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [data_name](#data_name) |
| `type` | yes | [type_def](#type_def) |
| `storage` | yes | [storage_def](#storage_def) |
| `hash` | yes | [bool_def](#bool_def) |
| `format` | yes | [format_def](#format_def) |
| `user_path` | yes | [path_pattern](#path_pattern) |

No other keys are allowed.

### node (`node_def`)

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [alphanumeric_name](#alphanumeric_name) |
| `image` | no | [name_version](#name_version) |
| `bash` | no | [name_version](#name_version) |
| `nix` | no | [nix_uri_or_nix_hash](#nix_uri_or_nix_hash) |
| `input` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: object, see [node.input.*](#nodeinput) |
| `output` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: object, see [node.output.*](#nodeoutput) |

No other keys are allowed.

Exactly one of these alternatives: {`image`} / {`bash`} / {`nix`}

#### node.input.*

| Key | Required | Value |
| --- | --- | --- |
| `type` | yes | [type_def](#type_def) |
| `format` | yes | [format_def](#format_def) |
| `path_in_container` | no | [path_pattern](#path_pattern) |
| `environment_var_in_container` | no | [alphanumeric_name](#alphanumeric_name) |
| `command_line_parameter` | no | string, at least 1 character(s) |

No other keys are allowed.

Exactly one of these alternatives: {`path_in_container`} / {`environment_var_in_container`} / {`command_line_parameter`}

#### node.output.*

| Key | Required | Value |
| --- | --- | --- |
| `type` | yes | [type_def](#type_def) |
| `format` | yes | [format_def](#format_def) |
| `path_in_container` | no | [path_pattern](#path_pattern) |
| `environment_var_in_container` | no | [alphanumeric_name](#alphanumeric_name) |
| `command_line_parameter` | no | string, at least 1 character(s) |

No other keys are allowed.

Exactly one of these alternatives: {`path_in_container`} / {`environment_var_in_container`} / {`command_line_parameter`}

### workflow (`workflow_def`)

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [alphanumeric_name](#alphanumeric_name) |
| `input` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: object, see [workflow.input.*](#workflowinput) |
| `output` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [full_channel_def](#full_channel_def) |
| `bind` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: object, see [workflow.bind.*](#workflowbind) |
| `connect` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [full_channel_def](#full_channel_def) |
| `nodes` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: object, see [workflow.nodes.*](#workflownodes) |

No other keys are allowed.

#### workflow.input.*

| Key | Required | Value |
| --- | --- | --- |
| `type` | yes | [type_def](#type_def) |
| `format` | yes | [format_def](#format_def) |
| `litegraph` | no | [litegraph_def](#litegraph_def) |

No other keys are allowed.

#### workflow.bind.*

| Key | Required | Value |
| --- | --- | --- |
| `type` | yes | [type_def](#type_def) |
| `format` | yes | [format_def](#format_def) |
| `data` | no | [name_version](#name_version) |
| `environment_var_value` | no | string |
| `value` | no | any value - the constant bound to a channel of type str, int, float, bool or json |
| `litegraph` | no | [litegraph_def](#litegraph_def) |

No other keys are allowed.

Exactly one of these alternatives: {`data`} / {`environment_var_value`} / {`value`}

#### workflow.nodes.*

| Key | Required | Value |
| --- | --- | --- |
| `node` | no | [name_version](#name_version) |
| `workflow` | no | [name_version](#name_version) |
| `input` | no | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [alphanumeric_name](#alphanumeric_name) |
| `output` | no | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [alphanumeric_name](#alphanumeric_name) |
| `if` | no | [alphanumeric_name](#alphanumeric_name) |
| `then` | no | [wf_branch_def](#wf_branch_def) |
| `else` | no | [wf_branch_def](#wf_branch_def) |
| `litegraph` | no | [litegraph_def](#litegraph_def) |

No other keys are allowed.

Exactly one of these alternatives: {`node`, `input`, `output`} / {`workflow`, `input`, `output`} / {`if`, `then`, `else`}

### refine (`refine_def`)

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [alphanumeric_name](#alphanumeric_name) |
| `workflow` | yes | [name_version](#name_version) |
| `replace_by_node` | no | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [name_version](#name_version) |
| `replace_by_workflow` | no | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [name_version](#name_version) |
| `replace_bind` | no | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: object, see [refine.replace_bind.*](#refinereplace_bind) |

No other keys are allowed.

#### refine.replace_bind.*

| Key | Required | Value |
| --- | --- | --- |
| `type` | yes | [type_def](#type_def) |
| `format` | yes | [format_def](#format_def) |
| `data` | no | [name_version](#name_version) |
| `environment_var_value` | no | string |
| `value` | no | any value - the constant bound to a channel of type str, int, float, bool or json |
| `litegraph` | no | [litegraph_def](#litegraph_def) |

No other keys are allowed.

Exactly one of these alternatives: {`data`} / {`environment_var_value`} / {`value`}

### run (`run_def`)

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [alphanumeric_name](#alphanumeric_name) |
| `workflow` | yes | [name_version](#name_version) |

No other keys are allowed.

## Common definitions

### alphanumeric_name

string matching `^[a-zA-Z][a-zA-Z0-9_]*$`

### data_name

string matching `^[a-zA-Z_][a-zA-Z0-9_]*$` - Name of a data entry: like alphanumeric_name, but may start with '_' too.

### version_pattern

string matching `^(latest|[0-9]+)$`

### hash_pattern

string matching `^[a-fA-F0-9]{40}$`

### path_pattern

string matching `^(?:[a-zA-Z]:\\|\\\\|/)?([^<>:"|?*]+[\\/])*[^<>:"|?*]+$` - A valid file path that supports both Linux and Windows formats.

### name_version

Reference to a stored entity (data, node, workflow, run) by name and version. Hashes are not accepted.

| Key | Required | Value |
| --- | --- | --- |
| `name` | yes | [data_name](#data_name) |
| `version` | yes | [version_pattern](#version_pattern) |

No other keys are allowed.

### wf_branch_def

A branch (then or else) of an if node of a workflow: a node or a sub workflow with its channel renamings.

| Key | Required | Value |
| --- | --- | --- |
| `node` | no | [name_version](#name_version) |
| `workflow` | no | [name_version](#name_version) |
| `input` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [alphanumeric_name](#alphanumeric_name) |
| `output` | yes | object, keys matching `^[a-zA-Z][a-zA-Z0-9_]*$`, values: [alphanumeric_name](#alphanumeric_name) |

No other keys are allowed.

Exactly one of these alternatives: {`node`} / {`workflow`}

### nix_uri_or_nix_hash

| Key | Required | Value |
| --- | --- | --- |
| `uri` | no | string - A valid nix uri. |
| `hash` | no | string - A valid nix hash. |

No other keys are allowed.

Exactly one of these alternatives: {`uri`} / {`hash`}

### type_def

one of `"file"`, `"directory"`, `"environment_var"`, `"str"`, `"int"`, `"float"`, `"bool"`, `"json"`

### bool_def

one of `"true"`, `"false"`

### storage_def

one of `"platform"`, `"extern"`

### format_def

one of `"json"`, `"str"`, `"any"`

### full_channel_def

| Key | Required | Value |
| --- | --- | --- |
| `type` | yes | [type_def](#type_def) |
| `format` | yes | [format_def](#format_def) |
| `storage` | no | [storage_def](#storage_def) |
| `hash` | no | [bool_def](#bool_def) |
| `user_path` | no | [path_pattern](#path_pattern) |
| `litegraph` | no | [litegraph_def](#litegraph_def) |

No other keys are allowed.

### position_def

array of 2 of number - position [x, y] of a node on the canvas of the workflow editor

### litegraph_def

optional layout data of the workflow editor (LiteGraph)

| Key | Required | Value |
| --- | --- | --- |
| `pos` | no | [position_def](#position_def) |
| `state` | no | one of `"expanded"`, `"collapsed"` - state of the node on the canvas. Default: expanded |

No other keys are allowed.
