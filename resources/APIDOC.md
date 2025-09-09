# Documentation For The Platform Parma-Light

this documents describes

- the commands of the CLI. The CLI ist a text-based frontend for the backend server of the platform Parma-Light
- in the near future the GUI-based frontend will be added
- the API of the endpoints of the backend server of the platform Parma-Light
- some design decisions of the backend server

## Usage

- the backend server is run by calling `./admin.sh backend`. This starts the backend server listening at port `8080`
- then the CLI is run by calling `./admin.sh cli`. It enters into a toplevel loop, reading a command and then executing it by
  calling the matching endpoint of the backend server.

## Commands of the CLI

### General commands

- `exit` OR `quit` OR `''` terminate the CLI
- `store` store all tables in the file system
- `redirect <path>` load commands from file `<path>`. Commands may spawn many lines and are terminated by a ';'
   as last character of a line
- `login <user_name>` login with <user_name>
- `logout`
- `test_data` to load some test data into the pl-database. In directory 'test/test_cmds' the commands (and more) are found.
  Copy, edit and paste.

To be discussed and not yet implemented:

- `statistics` to print statistics
- `gc` to remove unused data
- `commit` to commit all changes of the PL-database permanently (currently each command commits its changes)
- `reset` remove all data changed in the PL-database since the last commit, includes a gc() call

### CLI commands to add new entities to the database

- `user <json>`
  - add a new user.
  - \<json\> as in [user definition](#the-endpoint-user)

- `data <json>`
  - add a new file.
  - \<json\> as in [data definition](#the-endpoint-data)

- `node <json>`
  - add a new node.
  - \<json\> as in [node definition](#the-endpoint-node)

- `workflow <json>`
  - add a new workflow.
  - \<json\> as in [workflow definition](#the-endpoint-workflow)

- `refine <json>`
  - modify an existing workflow.
  - \<json\> as in [refine definition](#the-endpoint-refine)

### CLI command to run a workflow

- `run <json>`
  - run an existing workflow.
  - \<json\> as in [run definition](#the-endpoint-run)

### CLI commands to view tables of entities

- `view user` see relevant data of all user added in the past
- `view data` see relevant data of all data added in the past
- `view node` see relevant data of all nodes added in the past
- `view workflow` see relevant data of all workflows added in the past
- `view run` see relevant data of all workflow runs

These commands can be fine-tuned by a pattern to filter the output and a count to restrict the number of output lines.
These properties can be set and reset

- `view pattern <PATTERN>` to define a pattern
- `view count <number>` to define a restriction for the number of lines shown
- `view reset` to reset the pattern and count properties

### CLI commands to view and export data content

- `view data_of <ENTITY>` to see the data read and written by an ENTITY.
- `view log_of <ENTITY>` to see the logging data of an ENTITY.
- `cat <DATA>` to see the content of the data object.
- `export <DATA> <path-to-a-file>` copy the content of a data object into a file.

`<DATA>` and `<ENTITY>` can be either

- a string without white space that specifies a hash value,
- two strings separated by white space that specify name and version, or
- a json object with either the properties `name` and `version` or the property `hash`

## Design decisions for the backend server

- each endpoint uses the method `POST` and gets the data expected from the user (i.e. from the frontend) as a JSON object
- all keys ("metadata") added by the platform when a new entity is stored, are prefixed with '\_', a key given by the user
  _must never_ start with '_'.
- all entities (data, nodes, workflows, runs) of the parma-light platform are stored in a database in separate tables. As the primary key a hash of the content of the entity is used. This key is called "hash".

- database tables contain keys **"name" and "_version"** (an int value). The pair "name" and "_version" is guaranteed to be unique. If a
  new definition is added to the pl-database and the "name" is already used, the "_version" key is incremented automaticaly to the next
  unused number. This is done by the platform, not the user. The do-called "latest" definition is the one with the highest "_version".

- **the "type" key** is used in the entities "data", "node" and "workflow". The key describes the type of data. This part will be revised
  in the next future to support a rich system (directories, streams, rpc channels, ...). Currently there is only support for:

  - file
  - directory
  - environment_var

- **the "format" key** is used in the entities "data", "node" and "workflow". The key describes the format/type of the content of channels
  and files. This part will be revised in the next future to support a rich type system (jsonschema, arrow definition, numpy types, ...).
  Currently there is only support for:

  - json
  - str
  - any

## The FLASK endpoints of the backend server

All endpoints use the POST method. All endpoints expect a JSON object as payload.

### The endpoint `/user`

Add a user to the pl-database.

```json
{
  "name": "<user chosen name>",
  "display_name": "<user chosen display name>",
  "su": "<super user or not: true or false>"
}
```

Remarks:

- the "_version" attribute in the pl-database attribute is always "1"
- For security there are no different versions of a user with given "name".

Example:

```json
user {
  "name":"ibudde",
  "display_name":"Inte Budde",
  "su":false
};
```

### The endpoint `/data`

Add a data object to the pl-database

```json
{
  "name": "<user chosen name of the data>",
  "type": <see section about special_keys>,
  "format": <see section about special_keys>,
  "storage": "<platform or extern: save copy of file in the platform>",
  "hash": "<true or false: compute a hash of the content of a file>",
  "user_path": "<path in the user space>"
}
```

Example:

```json
data {
  "name": "pred_labels",
  "type": "file",
  "format": "json",
  "user_path": "test/test_data/scikit-learn/pred_labels.json"
};
```

### The endpoint `/node`

Add a node to the pl-database.

```json
{
  "name": "<user chosen name of the node>",
  "image": {"name": "<image>", "version":<version>},
  "input": {"<name-of-the-channel": datadef, ...},
  "output": {"<name-of-the-channel": datadef, ...}
}
```

Part of a node definition: datadef

```json
{
  "type": <see section about special_keys>,
  "format": <see section about special_keys>,
  "path_in_container": "<path in the running container>",
  "environment_var_in_container": "<name of a environment variable in the container, that will contain data (a json object, e.g.) at runtime>"
}
```

Remarks:

- "input" and "output" are two kinds lists of channels a node is using.
- a channel list may be empty.
- "environment_var_in_container" is only legal for "input" channels
- only one of "path_in_container" and "environment_var_in_container" may be used in a datadef and must match the requirements of "type".

Example:

```json
node {
  "name": "scikit_learn",
  "image": {"name": "scikit_learn", "version": "2",
  "input": {
      "cmd":         { "type": "environment_var", "format": "str",  "environment_var_in_container": "CMD"},
      "pred_labels": { "type": "file", "format": "json", "path_in_container": "/data/pred_labels.json" },
      "true_labels": { "type": "file", "format": "json", "path_in_container": "/data/true_labels.json" }
  },
  "output": {
      "result": {"path_in_container": "/data/result.json"}
  }
};
```

## The endpoint `/workflow`

Add a workflow to the pl-database.

```json
{
  "name": "<user chosen name of the workflow>",
  "input":   {"<workflow_channel_name>": channel_decl, ...},
  "output":  {"<workflow_channel_name>": channel_decl, ...},
  "bind":    {"<workflow_channel_name>": channel_binding, ...},
  "connect": {"<workflow_channel_name>": channel_decl, ...},
  "nodes":   {"<node_name>": node_def, ... }
}
```

Part of workflow definition: channel_decl

```json
{
  "type": <see section about special_keys>,
  "format": <see section about special_keys>
}
```

Part of workflow definition: channel_binding

```json
{
  "type": <see section about special_keys>,
  "format": <see section about special_keys>,
  "environment_var_value": <value bound to a channel, which is an "environment_var">,
  "data": {<definition either by "name" and "version", or "hash">}
}
```

Part of workflow definition: node_def

```json
{
  "node": {<definition either by "name" and "version", or "hash">},
  "workflow": {<definition either by "name" and "version", or "hash">},
  "input":   {"<node_channel_name>": "<renaming_to_workflow_channel_name>", ...},
  "output":  {"<node_channel_name>": "<renaming_to_workflow_channel_name>", ...}
}
```

Remarks:

- in channel_binding either "environment_var_value" or "data" are valid. Must match "type".
- in node_def either "node" or "workflow" are valid.
- consistency requirements for workflow definitions:
  - the channel names `<workflow_channel_name>` of the four sections "input", "output", "bind" and "connect" define the channels of the
    workflow. All names have to be disjunct.
  - the "input" and "output" sections of workflow define the channels for communication with the environment (super workflows e.g.). The
    lists are empty for the typical workflow, which is run by the user.
  - the "bind" section binds constants values to a channel, e.g. files or environment variables.
  - the "nodes" section defines the nodes, which are glued together in a workflow. To achieve this, the "input" and "output" channels
    `<node_channel_name>` of the nodes are matched with a `<workflow_channel_name>`. We call this _renaming_.
  - the renamed channel names are those, which are effective in a workflow.
  - a workflow must define an acyclic graph of nodes connected by channels. The graph is build using the channels
    from the "connect" section.

Example:

```json
workflow {
    "name": "scikit_learn_accuracy",
    "input": {
    },
    "output": {
        "accuracy_result":  { "type": "file", "format": "json" }
    },
    "bind": {
        "accuracy_cmd":     { "type": "environment_var", "format": "str", "environment_var_value": "accuracy" },
        "pred_labels_file": { "type": "file", "format": "json", "data": {"name": "pred_labels", "version": "latest" } },
        "true_labels_file": { "type": "file", "format": "json", "data": {"name": "true_labels", "version": "latest" } }
    },
    "connect": {
    },
    "nodes": {
        "scikit_learn": {
            "node": {"name": "scikit_learn", "version": "1"},
            "input": {
                "cmd":         "accuracy_cmd",
                "pred_labels": "pred_labels_file",
                "true_labels": "true_labels_file"
            },
            "output": {
                "result": "accuracy_result"
            }
        }
    }
}
```

## The endpoint `/refine`

Add a workflow to the pl-database by refining an existing workflow. The existing workflow can be modified by substituting either
node definitions by nodes or (sub-)workflows, or, by replacing a bind channel definition.

```json
{
  "name": "<user chosen name of the workflow>",
  "workflow": {<definition either by "name" and "version", or "hash">},
  "replace_by_node":     {"<node_name>": replace_node_def, ...},
  "replace_by_workflow": {"<node_name>": replace_node_def, ...},
  "replace_bind":        {"<workflow_channel_name>": channel_binding, ...}
}
```

Example:

```json
refine {
    "name": "scikit_learn_accuracy",
    "workflow": { "name": "scikit_learn_accuracy", "version": "latest" },
    "replace_bind": {
      "accuracy_cmd": { "type": "environment_var", "format": "str", "environment_var_value": "accuracy,f1" }
    }
}
```

## The endpoint `/run`

Run an existing workflow.

```json
{
  "name": "<user chosen name of the workflow to run>",
  "workflow": {<definition either by "name" and "version", or "hash">}
}
```

Example:

```json
run {
  "name": "scikit_learn_accuracy",
  "workflow": { "name": "scikit_learn_accuracy", "version": "latest" }
}
```
