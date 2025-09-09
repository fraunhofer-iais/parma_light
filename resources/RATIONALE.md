# RATIONALE For The Platform Parma-Light

Please comment on this text and mail to reinhard DOT budde AT iais.fraunhofer.de

## Purpose

... is a demonstrator for the PARMA concept, see _ref missing_.

The platform shall show:

- that fully persisted, fully documented, reproducable workflows can be defined
- with minimal obligations for the developers of the AI and validation tools

This supports the auditable and transparent evaluation of AI tools.

## Overall architecture

The platform builds on well-known concepts:

- running a workflow is the reason why a user uses the platform.
- a workflow is a directed acyclic graph of nodes connected by channels (Note, that nodes and channels of Parma-Light are both _nodes of the graph_ :-).
- nodes consume data from and produce data for channels.
- nodes are either
  - docker images (_terminal nodes_) or
  - (sub) workflows (_workflow nodes_).
- channels are files, directories and environment variables. There will be an extension by streams, dialogs and rpc soon.

- a terminal node defines besides the docker image two lists of input and output channels.
- channels define the properties needed _inside_ of the container to access the channel (pathes and names of environment variables
  used inside of the container)
- the platform puts as _little restrictions as possible_ onto the developer of the docker image. Only simple, well-known concepts are used:
  mounting files and directories and setting environment variables when an image is run.
  
- a workflow defines a list of nodes and how the channels of the nodes are mapped to the channels of the workflow (we call this _renaming_).
- the channels of a workflow are defined in 4 sections:
  - the "input" and "output" sections of workflow define the channels for communication with the environment (super workflows e.g.). The lists are empty for the typical workflow, which is run by the user.
  - the "bind" section binds constants values to a channel, e.g. files or environment variables.
  - the "connect" section defines the channels, which are used to glue nodes together in a workflow. The network of all the nodes build with the help of the "connect" channels must be an acyclic graph.

Such a workflow architecture is standard and used by many workflow engines and orchestrators. What is then the interesting part of Parma-Light?

- transparent and auditable workflows with AI nodes and validation nodes.
- if a workflow is run, logging of the invocation of all nodes, all inputs and outputs, are safely stored in the database of Parma-Light.
  This is the responsibility of the platform, not of the programmer of an docker image.
- it is possible at any time to repeat any past workflow, i.e.,
  - using the previously saved versions of the nodes, including the versions of the docker images,
  - and the previously saved inputs of the nodes
  - to check whether they generate the outputs that was saved in the past.

## Software architecture

- Parma-Light contains a database that persists all the data described above permanently.
- Hashes are used to ensure that modifications of stored data can be detected.
- Hashes are used as primary keys of all tables.

The main modules are:

- users.py contains the user management (e.g. adding and viewing of users)
- data.py contains the data management (e.g. storing files permanently for use by nodes as input and output).
- nodes.py contains the node management (e.g. adding and viewing nodes). Besides the docker image a node definition states the input
  and output data needed by the node to operate correctly.
- workflow.py contains the workflow management (e.g. adding and viewing workflows). A workflow defines the connection between the nodes by data (e.g. that the data, which is output of one node, is the data, which is input of another node).
- run.py contains the runs of workflows (e.g. starting a workflow and storing all input, intermediate and final data permanently). It is a simple, but robust orchestrator.

The software architecture is based on 'design by contract'. If assertions are violated an exception of type 'ParmaException' is thrown.
An exception is either user scope (wrong user input) or system scope (programming inconsistency detected). The exception message is a JSON object
which contains a message key and is prepared for easy i18n. Exceptions are thrown everywhere, but they are caught at the system border and an understandable message is
sent back to the user.

## Topics for discussion

- the orchestrator of the platform should be exchangeable. Especially data-driven frameworks as _snakemake_ or _CWL_ seem very promising. They can add platform independency and scalability without sacrifying the PARMA concept.

- the channels

- Complex AI or validation nodes that are orchestrated in a network of its own should be
  connected to the PARMA demonstrator via an adapter (this also allows federated systems). The unique identification of these systems for auditability remains a
  problem.
  
- In the near future, communication between must will be possible via new channels types
  (pipes, sockets, rpc, etc.).

## Relation to other activities of the department AAA

- Tools like the copyright tool, fuzzy tool, etc. can be easily used as nodes with Parma-Light.
- Tools like the va_tool can be integrated in the style of human-in-the-loop. Such a tool is ok for auditable workflows, but obviously the workflows are not reproducable in general.
- The barebone from MissionKI is a generator for docker images. These images can be used by Parma-Light. The generation of Docker images is out of scope offor the platform.
- DeployAI promotes Graphene, a framework for deployments and orchestration of AI applications. Orchestration of Graphene can be used as a runtime engine for running workflows.
