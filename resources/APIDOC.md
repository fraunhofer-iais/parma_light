# Documentation For The Platform Parma-Light

This document describes

- how the platform is used (web frontend, command line uploads)
- the definitions of users, data, nodes, workflows, refinements and runs, as they are uploaded to the platform
- the general rules of the REST endpoints of the backend server
- some design decisions of the backend server

The reference of all REST endpoints (request, response, token) and the exact structure of all definitions are
**generated** from the source code into [generated/API-REFERENCE.md](generated/API-REFERENCE.md)
(by `./admin.sh apidoc`, from the route docstrings and the JSON schema
`src/parma/intern/schema-def-for-user-commands.json`). This document describes the semantics. If it and the
schema differ, the schema is right.

## Usage

- `./admin.sh server` starts the backend server. It listens at port `8080` (see `server.port` in `parma_light.yaml`).
- the frontend is a web application served by the backend: open `http://localhost:8080` in a browser and log in.
  It shows lists of data, nodes, workflows and runs. Definitions can be uploaded, downloaded, edited and deleted,
  workflows can be edited graphically (based on LiteGraph) and run, the data and logs of runs can be inspected.
- `./curl.sh` uploads files with definitions from the command line, as the frontend does. See `./curl.sh help`.
- `./admin.sh init-datastore` uploads the definitions of `test/test_cmds` for testing and demonstration.
  See `./admin.sh help`.

## Design decisions for the backend server

- each endpoint (except `GET /`) uses the method `POST` and gets the data from the frontend as a JSON object.
- all entities (users, data, nodes, workflows, runs) are stored in separate tables. The primary key is a hash
  of the content of the entity, called "hash".
- all keys ("metadata") added by the platform when a new entity is stored are prefixed with `_`, e.g. `_version`,
  `_date`, `_hash_of_creating_user`. A key given by the user _must never_ start with `_`.
- **"name" and "\_version"**: the pair is unique. If a new definition is added and its "name" is already used,
  the platform sets "\_version" to the next unused number. The "latest" definition is the one with the highest
  "\_version".
- **referers**: a definition refers to another entity by `{"name": "<name>", "version": "<number or latest>"}`.
  Hashes are not accepted in user definitions, they are used internally only (e.g. by the frontend).
- **the "type" key** describes the kind of a channel or data:
  - `file`, `directory` - data stored by the platform, passed to a node as a path
  - `environment_var` - a string value passed to a node as environment variable or command line parameter
  - `str`, `int`, `float`, `bool`, `json` - constants, passed as environment variable or command line parameter.
    For constants the "format" is optional and defaults to `str`.
- **the "format" key** describes the format of the content of a channel or file: `json`, `str` or `any`.
  This part will be revised in the future to support a richer type system.

## Definitions

The keys, their values and which of them are required are listed in the section "Definitions" of
[generated/API-REFERENCE.md](generated/API-REFERENCE.md). Here the meaning and the rules not expressed by the
schema are described.

### The upload format

The content of an uploaded file (by the frontend or by `curl.sh`) is either

- plain JSON: one definition as object or a list of definitions, or
- one or more blocks `<keyword> { ... }`, each optionally terminated by `;`. The keyword is `user`, `data`, `node`,
  `workflow`, `refine` or `run`. A file for the workflow upload may contain `workflow` and `refine` blocks.

The definitions are stored one after the other. Processing stops at the first error, definitions stored before
remain stored. The response says which.

### User

```json
{
  "name": "<alphanumeric name>",
  "admin": <true or false>,
  "password": "<initial password>"
}
```

Remarks:

- only admins may add or remove users. The initial datastore contains the admin user `root`.
- the "\_version" of a user is always 1. For security there are no different versions of a user.
- the password is stored as a hash. Users change their password in the frontend.

Example:

```json
user {
  "name": "max",
  "admin": false,
  "password": "change_it"
};
```

### Data

Adds a file or a directory to the platform.

```json
{
  "name": "<name, may start with '_'>",
  "type": "<file or directory>",
  "format": "<json, str or any>",
  "storage": "<platform: store a copy in the platform, or extern>",
  "hash": "<\"true\" or \"false\": compute a hash of the content>",
  "user_path": "<path of the file or directory>"
}
```

Remarks:

- all keys are required.
- "user_path" is read on the server. A relative path is relative to the base directory (`store.base_dir` of the
  yaml property file).
- a plain file can be uploaded without a definition (frontend, or `curl.sh data-file <file>`). The definition is
  generated: the name is the file name with `.` replaced by `_` (prefixed by `_` if it starts with a digit),
  type `file`, format `any`, storage `platform`, hash `"true"`.

Example:

```json
data {
  "name": "gen_string",
  "type": "file",
  "storage": "platform",
  "hash": "true",
  "format": "any",
  "user_path": "bash/_gen_string.sh"
};
```

### Node

A node is a program with input and output channels. It is executed as a docker image, a bash script or a nix
derivation.

```json
{
  "name": "<alphanumeric name>",
  "image": {"name": "<docker image>", "version": "<tag>"},
  "bash":  {"name": "<name of a data entry containing the script>", "version": "<number or latest>"},
  "nix":   {"uri": "<nix uri>"} or {"hash": "<nix hash>"},
  "input":  {"<channel name>": channel_def, ...},
  "output": {"<channel name>": channel_def, ...}
}
```

Part of a node definition: channel_def

```json
{
  "type": "<see design decisions>",
  "format": "<json, str or any>",
  "path_in_container": "<path in the running container>",
  "environment_var_in_container": "<name of an environment variable>",
  "command_line_parameter": "<parameter, e.g. --seed>"
}
```

Remarks:

- exactly one of "image", "bash" and "nix" is required. Bash and nix nodes are not supported on windows.
- "input" and "output" are required, but may be empty.
- instead of "input"/"output" the list format "inputs"/"outputs" can be used:
  `"inputs": [{"name": "<channel name>", "type": ..., ...}, ...]`. Both formats must not be mixed for one direction.
- every channel_def has exactly one of "path_in_container", "environment_var_in_container" and
  "command_line_parameter".
- `file` and `directory` channels are passed by path (in the container or in an environment variable).
- constants and `environment_var` are passed as environment variable or command line parameter, never by path.
- command line parameters are allowed for inputs only and not for nix nodes.
- outputs must not have a constant type: node outputs are always files or directories.

Example:

```json
node {
    "name": "nd_metric",
    "image": { "name": "sklearn_metric", "version": "1" },
    "inputs": [
        { "name": "cmd",         "type": "str",  "command_line_parameter": "--metric" },
        { "name": "pred_labels", "type": "file", "format": "json", "path_in_container": "/data/pred_labels.json" },
        { "name": "true_labels", "type": "file", "format": "json", "path_in_container": "/data/true_labels.json" }
    ],
    "outputs": [
        { "name": "result", "type": "file", "format": "json", "path_in_container": "/data/result.json" }
    ]
};
```

### Workflow

A workflow connects nodes, sub workflows and if nodes by channels.

```json
{
  "name": "<alphanumeric name>",
  "input":   {"<workflow channel name>": channel_decl, ...},
  "output":  {"<workflow channel name>": channel_decl, ...},
  "bind":    {"<workflow channel name>": channel_binding, ...},
  "connect": {"<workflow channel name>": channel_decl, ...},
  "nodes":   {"<node name>": node_use or if_node, ...}
}
```

Part of a workflow definition: channel_decl

```json
{
  "type": "<see design decisions>",
  "format": "<json, str or any>"
}
```

Part of a workflow definition: channel_binding

```json
{
  "type": "<see design decisions>",
  "format": "<json, str or any>",
  "data": {"name": "<name of a data entry>", "version": "<number or latest>"},
  "environment_var_value": "<string>",
  "value": <constant>
}
```

Part of a workflow definition: node_use (a node or a sub workflow)

```json
{
  "node":     {"name": "<name>", "version": "<number or latest>"},
  "workflow": {"name": "<name>", "version": "<number or latest>"},
  "input":    {"<node channel name>": "<workflow channel name>", ...},
  "output":   {"<node channel name>": "<workflow channel name>", ...}
}
```

Part of a workflow definition: if_node

```json
{
  "if":   "<workflow channel name of type bool>",
  "then": node_use,
  "else": node_use
}
```

Remarks:

- all six sections are required, but may be empty.
- the channel names of the four sections "input", "output", "bind" and "connect" are the channels of the workflow.
  All names have to be disjoint.
- "input" and "output" are the channels for the communication with the environment. A workflow with inputs is a
  sub workflow: it can't be run on its own, only as part of another workflow.
- "bind" binds a value to a channel: exactly one of "data" (for `file` and `directory`), "environment_var_value"
  (for `environment_var`) and "value" (for constants).
- "connect" declares the channels between the nodes.
- in node_use exactly one of "node" and "workflow" is required. The channels of the node or sub workflow are
  mapped to workflow channels (_renaming_). All channels of a node should be renamed, a channel that is not renamed
  is reported in the log.
- a sub workflow input can be fed by an input of the calling workflow, by a "connect" channel (an output of another
  node) or by a "bind" channel of the calling workflow (data, environment var value or constant).
- the nodes and channels must form an acyclic graph. A channel is written by one node at most.
- **if nodes** are a functional construct: depending on the bool channel "if", either the "then" or the "else"
  branch is executed. Both branches are a node or a sub workflow. Their inputs may differ, but they must write
  the same set of workflow channels, with equal type and format. The names of the node channels may differ.
- runs are evaluated lazily: a node is only executed, if its outputs are needed (a workflow output, or an input of a
  node that is executed). The branch of an if node that is not selected and the nodes feeding only this branch are
  skipped.
- all nodes, channels and workflows may have an optional key "litegraph" with layout data of the workflow editor
  (`{"pos": [x, y], "state": "expanded" or "collapsed"}`).

Example (the condition selects the metric):

```json
workflow {
    "name": "wf_seed_42_with_if",
    "input": {},
    "output": {
        "accuracy_result": { "type": "file", "format": "json" }
    },
    "bind": {
        "seed_setting":              { "type": "int",  "value": 42 },
        "condition":                 { "type": "bool", "value": true },
        "metric_accuracy":           { "type": "str",  "value": "accuracy" },
        "metric_accuracy_precision": { "type": "str",  "value": "accuracy,precision" }
    },
    "connect": {
        "model_file":       { "type": "file", "format": "any" },
        "X_test_file":      { "type": "file", "format": "any" },
        "pred_labels_file": { "type": "file", "format": "any" },
        "true_labels_file": { "type": "file", "format": "any" }
    },
    "nodes": {
        "model": {
            "node": { "name": "nd_train", "version": "1" },
            "input":  { "seed": "seed_setting" },
            "output": { "model": "model_file", "X_test": "X_test_file", "true_labels": "true_labels_file" }
        },
        "predict": {
            "node": { "name": "nd_predict", "version": "1" },
            "input":  { "model": "model_file", "X_test": "X_test_file" },
            "output": { "pred_labels": "pred_labels_file" }
        },
        "metric": {
            "if": "condition",
            "then": {
                "node": { "name": "nd_metric", "version": "1" },
                "input":  { "cmd": "metric_accuracy", "pred_labels": "pred_labels_file", "true_labels": "true_labels_file" },
                "output": { "result": "accuracy_result" }
            },
            "else": {
                "node": { "name": "nd_metric", "version": "1" },
                "input":  { "cmd": "metric_accuracy_precision", "pred_labels": "pred_labels_file", "true_labels": "true_labels_file" },
                "output": { "result": "accuracy_result" }
            }
        }
    }
};
```

More examples are in `test/test_cmds/**/workflow*.txt`.

### Refine

Adds a workflow by modifying an existing workflow: nodes can be replaced by other nodes or by sub workflows,
bind channels can get other bindings.

```json
{
  "name": "<name of the new workflow>",
  "workflow": {"name": "<name>", "version": "<number or latest>"},
  "replace_by_node":     {"<node name>": {"name": "<node>", "version": "<number or latest>"}, ...},
  "replace_by_workflow": {"<node name>": {"name": "<workflow>", "version": "<number or latest>"}, ...},
  "replace_bind":        {"<workflow channel name>": channel_binding, ...}
}
```

Remarks:

- a replacement must have the same channels as the node it replaces.
- if nodes can't be replaced.

Example:

```json
refine {
    "name": "wf_seed_42_precision",
    "workflow": { "name": "wf_seed_42_with_if", "version": "latest" },
    "replace_bind": {
        "condition": { "type": "bool", "value": false }
    }
};
```

### Run

Runs an existing workflow. A workflow with inputs (a sub workflow) can't be run.

```json
{
  "name": "<name of the run>",
  "workflow": {"name": "<name>", "version": "<number or latest>"}
}
```

Example:

```json
run {
  "name": "run_seed_42",
  "workflow": { "name": "wf_seed_42_with_if", "version": "latest" }
};
```

The stored run contains the metadata `_log` (the log of the execution) and `_channel_bindings` (channel name ->
hash of the data read and written).

## The REST endpoints of the backend server

General rules:

- all endpoints use the method `POST` and expect a JSON object as payload (except `GET /` and
  `/data/upload-file`).
- most endpoints require the header `X-Auth-Token: <token>` (see the column "Token" of the generated reference).
  The token is returned by `/user/login`.
- responses are JSON objects with the key `"success"`. On errors the HTTP status is 200 as well, the response is
  `{"success": false, "error": "<text>"}` (or `"exception"` for unexpected errors).
- `<referer>` in a request is either `{"hash": "..."}` or `{"name": "...", "version": <number>}`.

All endpoints with request, response and whether they need a token are listed in
[generated/API-REFERENCE.md](generated/API-REFERENCE.md).

### Upload responses

All `.../upload` endpoints (except `/data/upload-file`) store the definitions one after the other:

- success: `{"success": true, "hash": "<hash of the last definition>", "hashes": [...], "count": n}`
- error: `{"success": false, "error": "<keyword> <i> of <n> (name \"...\") failed: <reason>. <k> definition(s) stored before.", "hashes": [<hashes stored before the error>], "count": n}`
