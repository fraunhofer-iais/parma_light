// Value of an Environment Variable

function EnvVarValue() {
    this.addOutput("value", "environment_var");
    this.addProperty("value", "", "string");
    this.widget = this.addWidget("text","value","","value");
    this.widgets_up = true;
    this.size = [180, 30];
}

EnvVarValue.title = "EnvVarValue";
EnvVarValue.desc = "Defines the value of an environment variable";

EnvVarValue.prototype.onExecute = function() {
    this.setOutputData(0, this.properties["value"]);
};

EnvVarValue.prototype.getTitle = function() {
    if (this.flags.collapsed) {
        return this.properties.value;
    }
    return this.title;
};

EnvVarValue.prototype.setValue = function(v)
{
    this.setProperty("value",v);
}

EnvVarValue.prototype.onDrawBackground = function(ctx) {
    //show the current value
    this.outputs[0].label = this.properties["value"];
};

LiteGraph.registerNodeType("parma/env_var_value", EnvVarValue);

// Define which data from the data store can be used as input file

function InputFile() {
    this.addOutput("data", "file");
    this.addProperty("name", "", "string");
    this.addProperty("version", "", "string");
    this.widget = this.addWidget("text","name","","name");
    this.widget = this.addWidget("text","version","","version");
    this.widgets_up = true;
    this.size = [180, 90];
}

InputFile.title = "InputFile";
InputFile.desc = "Defines data by its name and version in the data store, which will be resolved to a file to be read by a node";

InputFile.prototype.getTitle = function() {
    if (this.flags.collapsed) {
        return this.properties.name + ':' + this.properties.version;
    }
    return this.title;
};

InputFile.prototype.onDrawBackground = function(ctx) {
    //show the current value
    this.outputs[0].label = this.properties["name"] + ':' + this.properties["version"];
};

LiteGraph.registerNodeType("parma/infile", InputFile);

// Define which name is used to save output as a file in the data store

function OutputFile() {
    this.addInput("data", "file");
    this.addProperty("name", "", "string");
    this.widget = this.addWidget("text","name","","name");
    this.widgets_up = true;
    this.size = [180, 90];
}

OutputFile.title = "OutputFile";
OutputFile.desc = "Defines the name used to save output as a file in the data store";

InputFile.prototype.getTitle = function() {
    if (this.flags.collapsed) {
        return this.properties.name;
    }
    return this.title;
};

InputFile.prototype.onDrawBackground = function(ctx) {
    //show the current value
    this.outputs[0].label = this.properties["name"];
};

LiteGraph.registerNodeType("parma/outfile", OutputFile);

function register_parma_node(title, hierarchy, description, inputs, outputs) {
    const node_def_object = {
        title: title,
        type: hierarchy,
        desc: description,
        inputs: inputs || [],
        outputs: outputs || [],
        onMouseEnter: function(e) {
            let tooltip = document.getElementById("lg-tooltip");
            if (!tooltip) {
                tooltip = document.createElement("div");
                tooltip.id = "lg-tooltip";
                tooltip.style.cssText = "position:fixed;background:#333;color:#fff;padding:4px 8px;border-radius:4px;font-size:14px;font-family:sans-serif;pointer-events:none;z-index:9999;";
                document.body.appendChild(tooltip);
            }
            tooltip.textContent = this.desc;
            tooltip.style.left = e.clientX + 12 + "px";
            tooltip.style.top = e.clientY + 12 + "px";
            tooltip.style.display = "block";
        },
        onMouseLeave: function(e) {
            const tooltip = document.getElementById("lg-tooltip");
            if (tooltip) tooltip.style.display = "none";
        }
    };
    LiteGraph.buildNodeClassFromObject(hierarchy, node_def_object);
}

const graph = new LGraph();
const canvas = new LGraphCanvas("#workflow-litegraph", graph);

nodes = [
    {
        "name": "nd_train",
        "image": { "name": "sklearn_train", "version": "1" },
        "input": {
            "seed":         {"type": "environment_var", "format": "str", "environment_var_in_container": "SEED"}
        },
        "output": {
            "model":       { "type": "file", "format": "any",  "path_in_container": "/data/model.pkl" },
            "X_test":      { "type": "file", "format": "json", "path_in_container": "/data/X_test.json" },
            "true_labels": { "type": "file", "format": "json", "path_in_container": "/data/true_labels.json" }
        }
    },
    {
        "name": "nd_predict",
        "image": { "name": "sklearn_predict", "version": "1"},
        "input": {
            "model":  { "type": "file", "format": "any", "path_in_container": "/data/model.pkl" },
            "X_test": { "type": "file", "format": "any", "path_in_container": "/data/X_test.json" }
        },
        "output": {
            "pred_labels": { "type": "file", "format": "json", "path_in_container": "/data/pred_labels.json" }
        }
    },
    {
        "name": "nd_metric",
        "image": { "name": "sklearn_metric", "version": "1"},
        "input": {
            "cmd":         {"type": "environment_var", "format": "str", "environment_var_in_container": "CMD"},
            "pred_labels": { "type": "file", "format": "json", "path_in_container": "/data/pred_labels.json" },
            "true_labels": { "type": "file", "format": "json", "path_in_container": "/data/true_labels.json" }
        },
        "output": {
            "result":      {"type": "file", "format": "json", "path_in_container": "/data/result.json"}
        }
    }
]
for (const node of nodes) {
    lgname = node.name;
    lghierarchy = "parma/" + node.name;
    lgdescription = "Parma node " + node.name + " based on image: " + node.image.name + ":" + node.image.version;
    lginputs = [];
    for (const [input_name, input_info] of Object.entries(node.input)) {
        lginputs.push([input_name, input_info.type]);
    }
    lgoutputs = [];
    for (const [output_name, output_info] of Object.entries(node.output)) {
        lgoutputs.push([output_name, output_info.type]);
    }
    register_parma_node(lgname, lghierarchy, lgdescription, lginputs, lgoutputs);
}

graph.start()
