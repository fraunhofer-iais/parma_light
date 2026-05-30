/* global app.js – plain JavaScript, no frameworks */

// -- Session token -------------------------------------------------------------
// Set by login, cleared by logout, sent as X-Auth-Token header with every request.
var _loginToken = null; // Set by login, cleared by logout, sent as X-Auth-Token header with every request.
var _uiConfig = null; // Loaded at startup, read-only, contains ui configuration from parma_light.yaml

// -- API Helper ----------------------------------------------------------------

// Only one backend call may run at a time. A call made while another one is running is ignored:
// an error toast is shown (it replaces the toast of the running call, e.g. the seconds of a
// workflow run), and the returned promise never settles, thus no handler of the caller runs.
// The running call ends when its response has been read completely; its result toast is shown.
var _apiRunningUrl = null;

function _apiIsBusy() {
  return _apiRunningUrl !== null;
}

// For callers that change the UI before calling the backend: shows the error toast and returns
// true, if a call is running. The caller must then return without changing anything.
function _apiBusyToast() {
  if (!_apiIsBusy()) return false;
  showToast(
    "Ignored: the backend is still busy with " + _apiRunningUrl +
      ". Please wait until it has finished",
    "error",
  );
  return true;
}

// Runs "request" (a function returning a promise for the complete response) if no other call is running
function _guardedCall(url, request) {
  if (_apiBusyToast()) return new Promise(function () {});
  _apiRunningUrl = url;
  var done = function () {
    _apiRunningUrl = null;
  };
  var result;
  try {
    result = request();
  } catch (e) {
    done();
    return Promise.reject(e);
  }
  return result.then(
    function (value) {
      done();
      return value;
    },
    function (error) {
      done();
      throw error;
    },
  );
}

function apiCall(method, url, body) {
  var options = { method: method, headers: {} };
  if (_loginToken) {
    options.headers["X-Auth-Token"] = _loginToken;
  }
  if (body !== undefined && body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  return _guardedCall(url, function () {
    return fetch(url, options).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (t) {
          throw new Error("HTTP " + res.status + ": " + t);
        });
      }
      return res.json();
    });
  });
}

// -- App Initialization -------------------------------------------------------
(function loadAppConfig() {
  apiCall("POST", "/config", {})
    .then(function (data) {
      _uiConfig = data["ui_config"];
    })
    .catch(function (e) {
      console.error("Error loading app configuration:", e.message);
    });
})();

// -- Toast Notification --------------------------------------------------------

// A toast stays visible until the next click on a menu item or a button. The click listener
// runs in the capture phase, i.e. BEFORE the handler of the button: a toast shown by that
// handler (or later by its backend request) replaces the old one and stays visible.
function showToast(message, type) {
  var toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = "toast " + (type || "info");
  delete toast.dataset.owner; // a new message ends updates of an older one (see _updateOwnedToast)
}

// Shows a toast, that can be updated later by _updateOwnedToast(owner, ...)
function _showOwnedToast(owner, message, type) {
  showToast(message, type);
  document.getElementById("toast").dataset.owner = owner;
}

// Updates the text of the toast, if it is still visible and still shows the message of "owner"
function _updateOwnedToast(owner, message) {
  var toast = document.getElementById("toast");
  if (toast.dataset.owner !== owner || toast.classList.contains("hidden")) return;
  toast.textContent = message;
}

function hideToast() {
  var toast = document.getElementById("toast");
  if (toast) toast.classList.add("hidden");
}

document.addEventListener(
  "click",
  function (e) {
    if (e.target.closest && e.target.closest("button, .menu-item")) hideToast();
  },
  true,
);

// -- Panel Navigation ----------------------------------------------------------

function showPanel(panelId) {
  var welcome = document.getElementById("welcome-panel");
  if (welcome) welcome.remove();

  document.querySelectorAll(".panel").forEach(function (p) {
    p.classList.remove("active");
  });
  document.querySelectorAll(".menu-item").forEach(function (i) {
    i.classList.remove("active");
  });

  var panel = document.getElementById("panel-" + panelId);
  if (panel) panel.classList.add("active");

  var menuItem = document.querySelector(
    '.menu-item[data-panel="' + panelId + '"]',
  );
  if (menuItem) menuItem.classList.add("active");
}

// Wire up every menu leaf to showPanel
document.querySelectorAll(".menu-item").forEach(function (item) {
  item.addEventListener("click", function () {
    var panelId = item.getAttribute("data-panel");
    _nodeEditFromWorkflow = false; // a menu click leaves a node opened from the workflow editor
    if (panelId) showPanel(panelId);
  });
});

// -- Sidebar Accordion ---------------------------------------------------------

function toggleSection(headerBtn) {
  var items = headerBtn
    .closest(".menu-section")
    .querySelector(".menu-section-items");
  if (items.classList.contains("expanded")) {
    items.classList.remove("expanded");
    headerBtn.classList.remove("expanded");
  } else {
    items.classList.add("expanded");
    headerBtn.classList.add("expanded");
  }
}

// -- Password Visibility Toggle ------------------------------------------------

function togglePassword(inputId, btn) {
  var input = document.getElementById(inputId);
  if (input.type === "password") {
    input.type = "text";
    btn.title = "Hide password";
    btn.innerHTML = "&#128584;";
  } else {
    input.type = "password";
    btn.title = "Show password";
    btn.innerHTML = "&#128065;";
  }
}

// -- User Management -----------------------------------------------------------

// Logout is enabled only while logged in
function _updateLogoutButton() {
  var btn = document.getElementById("logout-btn");
  if (btn) {
    btn.disabled = !_loginToken;
    btn.title = _loginToken ? "" : "Please log in first";
  }
}

function handleLogin(event) {
  event.preventDefault();
  var name = document.getElementById("login-name").value.trim();
  var password = document.getElementById("login-password").value;
  if (!name) {
    showToast("Please enter a name", "error");
    return;
  }
  apiCall("POST", "/user/login", { name: name, password: password })
    .then(function (result) {
      if (result.success) {
        _loginToken = result.token;
        _updateLogoutButton();
        document.getElementById("login-status").textContent =
          "Logged in as " + name;
        document.getElementById("form-login").reset();
        showToast("Login successful", "success");
      } else {
        var msg = result.parma_exception
          ? JSON.stringify(result.parma_exception)
          : result.error || result.exception || "Login failed";
        showToast(msg, "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function handleLogout() {
  apiCall("POST", "/user/logout")
    .then(function () {
      _loginToken = null;
      _updateLogoutButton();
      document.getElementById("login-status").textContent = "Not logged in";
      showToast("Logout successful", "success");
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function handleChangePassword(event) {
  event.preventDefault();
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  var oldPwd = document.getElementById("old-password").value;
  var newPwd = document.getElementById("new-password").value;
  var repeatPwd = document.getElementById("repeat-password").value;
  if (newPwd !== repeatPwd) {
    showToast("The new passwords do not match", "error");
    return;
  }
  apiCall("POST", "/user/change-password", {
    old_password: oldPwd,
    new_password: newPwd,
  })
    .then(function (result) {
      if (result.success) {
        event.target.reset();
        showToast("Password changed successfully", "success");
      } else {
        showToast(
          result.error || result.exception || "Error changing password",
          "error",
        );
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function openAddUser() {
  showPanel("add-user");
  if (!_uiConfig) {
    showToast(
      "Configuration not yet loaded \u2013 please wait a moment and try again.",
      "info",
    );
    return;
  }
  renderDynamicForm(
    document.getElementById("add-user-form-container"),
    "add_user",
    null,
  );
}

function openRemoveUser() {
  showPanel("remove-user");
  if (!_uiConfig) {
    showToast(
      "Configuration not yet loaded \u2013 please wait a moment and try again.",
      "info",
    );
    return;
  }
  renderDynamicForm(
    document.getElementById("remove-user-form-container"),
    "remove_user",
    null,
  );
}

function handleAddUser() {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (!_uiConfig || !_uiConfig.add_user) {
    showToast("Configuration not loaded", "error");
    return;
  }
  var container = document.getElementById("add-user-form-container");
  var wrapper = container && container.querySelector(".df-form");
  if (!wrapper) {
    showToast("No form loaded", "error");
    return;
  }
  var data = _dfCollectData(wrapper, _uiConfig.add_user);
  if (!data.name || !data.name.trim()) {
    showToast("Please enter a name", "error");
    return;
  }
  if (!data.password) {
    showToast("Please enter a password", "error");
    return;
  }
  var name = data.name.trim();
  apiCall("POST", "/user/add", data)
    .then(function (result) {
      if (result.success) {
        showToast("User '" + name + "' added successfully", "success");
        openAddUser();
      } else {
        var msg = result.parma_exception
          ? JSON.stringify(result.parma_exception)
          : result.error || result.exception || "Error";
        showToast(msg, "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// Upload of a file with one or more user definitions (JSON, or blocks 'user { ... };')
var _userUploadState = { file: null };

function userUploadFileSelected(input) {
  _onFileSelected(input, _userUploadState, "user-upload-filename");
}

function handleUserUpload() {
  _uploadFromFile({
    state: _userUploadState,
    endpoint: "/user/upload",
    noun: ["user", "users"],
    fileInputId: "user-upload-file-input",
    filenameInputId: "user-upload-filename",
  });
}

function handleRemoveUser() {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (!_uiConfig || !_uiConfig.remove_user) {
    showToast("Configuration not loaded", "error");
    return;
  }
  var container = document.getElementById("remove-user-form-container");
  var wrapper = container && container.querySelector(".df-form");
  if (!wrapper) {
    showToast("No form loaded", "error");
    return;
  }
  var data = _dfCollectData(wrapper, _uiConfig.remove_user);
  if (!data.name || !data.name.trim()) {
    showToast("Please enter a name", "error");
    return;
  }
  var name = data.name.trim();
  apiCall("POST", "/user/remove", { name: name })
    .then(function (result) {
      if (result.success) {
        showToast("User '" + name + "' removed successfully", "success");
        openRemoveUser();
      } else {
        var msg = result.parma_exception
          ? JSON.stringify(result.parma_exception)
          : result.error || result.exception || "Error";
        showToast(msg, "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- Node Upload -------------------------------------------------------------

var _nodeUploadState = { file: null };
var _dataUploadState = { file: null };
var _dataMetadataUploadState = { file: null };
var _workflowUploadState = { file: null };
var _nodeDownloadState = { file: null };
var _workflowDownloadState = { file: null };

// File selections: every selection (upload or download panel) has its own state object, a hidden
// <input type="file">, a "Select File" button and a read-only field showing the selected file name.
// The action button (Upload / Download) is the first button of the row. It is enabled only, if a
// file is selected. "Select File" can be used at any time and replaces the selected file. If the
// file dialog is cancelled, the previous selection is kept.
function _onFileSelected(input, state, filenameInputId) {
  if (input.files && input.files[0]) {
    state.file = input.files[0];
  }
  document.getElementById(filenameInputId).value = state.file
    ? state.file.name
    : "";
  _updateFileActionButton(filenameInputId);
}

function _clearFileSelection(state, fileInputId, filenameInputId) {
  state.file = null;
  document.getElementById(fileInputId).value = "";
  document.getElementById(filenameInputId).value = "";
  _updateFileActionButton(filenameInputId);
}

// Enables the action button of a file selection row if (and only if) a file name is displayed
function _updateFileActionButton(filenameInputId) {
  var filenameInput = document.getElementById(filenameInputId);
  var row = filenameInput && filenameInput.closest(".upload-row");
  var actionButton = row && row.querySelector("button");
  if (actionButton) {
    actionButton.disabled = !filenameInput.value;
    actionButton.title = filenameInput.value ? "" : "Please select a file first";
  }
}

// Initially no file is selected: disable all action buttons of file selection rows
document.querySelectorAll(".upload-row .upload-filename").forEach(function (el) {
  if (el.id) _updateFileActionButton(el.id);
});

function _resultError(result, fallback) {
  return result.parma_exception
    ? JSON.stringify(result.parma_exception)
    : result.error || result.exception || fallback;
}

function nodeUploadFileSelected(input) {
  _onFileSelected(input, _nodeUploadState, "node-upload-filename");
}

function _uploadFromFile(config) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (!config.state.file) {
    showToast("Please select a file first", "error");
    return;
  }
  var reader = new FileReader();
  reader.onload = function (e) {
    apiCall("POST", config.endpoint, { content: e.target.result })
      .then(function (result) {
        if (result.success) {
          var count = (result.hashes || [result.hash]).length;
          showToast(
            count + " " + (count === 1 ? config.noun[0] : config.noun[1]) + " uploaded",
            "success",
          );
          _clearFileSelection(
            config.state,
            config.fileInputId,
            config.filenameInputId,
          );
        } else {
          showToast(_resultError(result, "Error uploading"), "error");
        }
      })
      .catch(function (e) {
        showToast("Error: " + e.message, "error");
      });
  };
  reader.readAsText(config.state.file);
}

function handleNodeUpload() {
  _uploadFromFile({
    state: _nodeUploadState,
    endpoint: "/node/upload",
    noun: ["node", "nodes"],
    fileInputId: "node-upload-file-input",
    filenameInputId: "node-upload-filename",
  });
}

// -- Workflow Upload ---------------------------------------------------------

function workflowUploadFileSelected(input) {
  _onFileSelected(input, _workflowUploadState, "workflow-upload-filename");
}

function handleWorkflowUpload() {
  _uploadFromFile({
    state: _workflowUploadState,
    endpoint: "/workflow/upload",
    noun: ["workflow", "workflows"],
    fileInputId: "workflow-upload-file-input",
    filenameInputId: "workflow-upload-filename",
  });
}

// -- Node Download -----------------------------------------------------------

function nodeDownloadFileSelected(input) {
  _onFileSelected(input, _nodeDownloadState, "node-download-filename");
}

function _downloadFromEndpoint(config) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (!config.state.file) {
    showToast("Please select a file first", "error");
    return;
  }

  var reader = new FileReader();
  reader.onload = function (e) {
    try {
      var referer = JSON.parse(e.target.result);
      apiCall("POST", config.endpoint, { referer: referer })
        .then(function (result) {
          if (result.success) {
            var content = result.content || "{}";
            var blob = new Blob([content], { type: "application/json" });
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = config.state.file.name;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(a.href);
            showToast(config.successLabel, "success");
            _clearFileSelection(
              config.state,
              config.fileInputId,
              config.filenameInputId,
            );
          } else {
            showToast(_resultError(result, "Error downloading"), "error");
          }
        })
        .catch(function (err) {
          showToast("Error: " + err.message, "error");
        });
    } catch (err) {
      showToast("Invalid referer file: " + err.message, "error");
    }
  };
  reader.readAsText(config.state.file);
}

function handleNodeDownload() {
  _downloadFromEndpoint({
    state: _nodeDownloadState,
    endpoint: "/node/download",
    successLabel: "Node downloaded",
    fileInputId: "node-download-file-input",
    filenameInputId: "node-download-filename",
  });
}

// -- Workflow Download -------------------------------------------------------

function workflowDownloadFileSelected(input) {
  _onFileSelected(input, _workflowDownloadState, "workflow-download-filename");
}

function handleWorkflowDownload() {
  _downloadFromEndpoint({
    state: _workflowDownloadState,
    endpoint: "/workflow/download",
    successLabel: "Workflow downloaded",
    fileInputId: "workflow-download-file-input",
    filenameInputId: "workflow-download-filename",
  });
}

// -- Admin --------------------------------------------------------------------

function handleStore() {
  apiCall("POST", "/store")
    .then(function (result) {
      if (result.success) {
        showToast("Store successful", "success");
      } else {
        showToast(result.error || result.exception || "Error saving", "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- Theme & UI properties ---------------------------------------------------

function applyTheme(btn) {
  var theme = btn.getAttribute("data-theme");
  document.body.setAttribute("data-theme", theme);
  document.querySelectorAll(".theme-card").forEach(function (c) {
    c.classList.remove("active");
  });
  btn.classList.add("active");
  try {
    localStorage.setItem("parma-theme", theme);
  } catch (_) {}
}

var _canvasThemes = {
  dark: {
    background: "#222",
    backgroundImage: LGraphCanvas
      ? LGraphCanvas.DEFAULT_BACKGROUND_IMAGE
      : null,
    nodeColor: "#333",
    nodeBgColor: "#353535",
    titleColor: "#999",
    nodeTextColor: "#AAA",
    linkColor: "#9A9",
  },
  light: {
    background: "#f0f0f0",
    backgroundImage: null,
    nodeColor: "#e0e0e0",
    nodeBgColor: "#d4d4d4",
    titleColor: "#fff",
    nodeTextColor: "#333",
    linkColor: "#555",
  },
};

function applyCanvasTheme(themeName, btn) {
  var theme = _canvasThemes[themeName];
  if (!theme) return;
  if (_lgCanvas) {
    _lgCanvas.clear_background_color = theme.background;
    _lgCanvas.background_image = theme.backgroundImage;
    _lgCanvas.node_title_color = theme.titleColor;
    _lgCanvas.default_link_color = theme.linkColor;
    LiteGraph.NODE_DEFAULT_COLOR = theme.nodeColor;
    LiteGraph.NODE_DEFAULT_BGCOLOR = theme.nodeBgColor;
    LiteGraph.NODE_TEXT_COLOR = theme.nodeTextColor;
    _lgCanvas.setDirty(true, true);
  }
  document.querySelectorAll(".canvas-theme-btn").forEach(function (b) {
    b.classList.remove("active");
  });
  if (btn) btn.classList.add("active");
  try {
    localStorage.setItem("parma-canvas-theme", themeName);
  } catch (_) {}
}

function applyFormDensity(value) {
  document.body.setAttribute("data-form-density", value);
  var sel = document.getElementById("form-density-select");
  if (sel) sel.value = value;
  try {
    localStorage.setItem("parma-form-density", value);
  } catch (_) {}
}

// Restore saved theme and density on load
(function restoreUiPrefs() {
  var savedTheme = null;
  var savedDensity = null;
  try {
    savedTheme = localStorage.getItem("parma-theme");
    savedDensity = localStorage.getItem("parma-form-density");
  } catch (_) {}
  if (savedTheme) {
    document.body.setAttribute("data-theme", savedTheme);
    var card = document.querySelector(
      '.theme-card[data-theme="' + savedTheme + '"]',
    );
    if (card) card.classList.add("active");
  }
  if (savedDensity) {
    applyFormDensity(savedDensity);
  }
  var savedCanvasTheme = null;
  try {
    savedCanvasTheme = localStorage.getItem("parma-canvas-theme");
  } catch (_) {}
  if (savedCanvasTheme) {
    var canvasBtn = document.getElementById("canvas-theme-" + savedCanvasTheme);
    applyCanvasTheme(savedCanvasTheme, canvasBtn || null);
  }
})();

// -- Dynamic Form Engine -------------------------------------------------------
//
// Public API:
//   renderDynamicForm(container, configKey, data)
//     container  – HTMLElement to render into
//     configKey  – key in _uiConfig (e.g. 'node')
//     data       – pre-fill object, or null for an empty form
//
// Field types defined in _uiConfig:
//   type: 'str'    → <input type="text">
//   type: 'number' → <input type="number">
//   type: 'bool'   → <input type="checkbox">
//   type: [...]    → <select> dropdown; following {if: value} blocks are shown/hidden on change
//   type: 'list'   → repeatable block with + / × buttons
// -----------------------------------------------------------------------------

var _dfCounter = 0;

function _dfNewId() {
  return "df" + ++_dfCounter;
}

// Normalise conditional entries: handles both {if: 'image'} and {'if file': null}
function _dfGetIfValue(field) {
  if (Object.prototype.hasOwnProperty.call(field, "if"))
    return String(field["if"]);
  var keys = Object.keys(field);
  for (var i = 0; i < keys.length; i++) {
    if (keys[i].length > 3 && keys[i].slice(0, 3) === "if ")
      return keys[i].slice(3);
  }
  return null;
}

function _dfIsConditional(field) {
  return _dfGetIfValue(field) !== null;
}

// Group each dropdown field with the {if:...} blocks that immediately follow it.
function _dfProcessDefs(fieldDefs) {
  var result = [];
  var i = 0;
  while (i < fieldDefs.length) {
    var field = fieldDefs[i];
    if (_dfIsConditional(field)) {
      i++;
      continue;
    }
    if (field.name && Array.isArray(field.type)) {
      var conditionals = [];
      var j = i + 1;
      while (j < fieldDefs.length && _dfIsConditional(fieldDefs[j])) {
        conditionals.push(fieldDefs[j]);
        j++;
      }
      result.push({ field: field, conditionals: conditionals });
      i = j;
    } else {
      result.push({ field: field, conditionals: [] });
      i++;
    }
  }
  return result;
}

function _dfMakeRow(labelText, inputEl, tooltip, required) {
  var row = document.createElement("div");
  row.className = "df-row";

  var labelWrap = document.createElement("div");
  labelWrap.className = "df-label";

  var labelSpan = document.createElement("span");
  labelSpan.textContent = labelText;
  labelWrap.appendChild(labelSpan);

  if (required) {
    var req = document.createElement("span");
    req.className = "df-required";
    req.textContent = "*";
    req.title = "Required";
    labelWrap.appendChild(req);
  }

  if (tooltip) {
    var tip = document.createElement("button");
    tip.type = "button";
    tip.className = "df-tooltip-btn";
    tip.textContent = "?";
    tip.addEventListener("click", function (e) {
      e.preventDefault();
      _dfToggleTooltip(tip, tooltip);
    });
    labelWrap.appendChild(tip);
  }

  row.appendChild(labelWrap);
  var val = document.createElement("div");
  val.className = "df-value";
  val.appendChild(inputEl);
  row.appendChild(val);
  return row;
}

function _dfToggleTooltip(btn, text) {
  var existing = btn.parentNode.querySelector(".df-tooltip-popup");
  if (existing) {
    existing.remove();
    return;
  }
  var popup = document.createElement("span");
  popup.className = "df-tooltip-popup";
  popup.textContent = text;
  btn.parentNode.appendChild(popup);
  // close on next outside click
  function onOutside(e) {
    if (!popup.contains(e.target) && e.target !== btn) {
      popup.remove();
      document.removeEventListener("click", onOutside, true);
    }
  }
  setTimeout(function () {
    document.addEventListener("click", onOutside, true);
  }, 0);
}

function _dfRenderSimple(container, field, data, formId) {
  var fieldId = formId + "_" + field.name;
  var value = data && data[field.name] !== undefined ? data[field.name] : "";
  var inputEl;

  if (field.type === "bool") {
    inputEl = document.createElement("input");
    inputEl.type = "checkbox";
    inputEl.id = fieldId;
    inputEl.dataset.dfKey = field.name;
    inputEl.className = "df-checkbox";
    inputEl.checked = !!value;
  } else if (field.type === "number") {
    inputEl = document.createElement("input");
    inputEl.type = "number";
    inputEl.id = fieldId;
    inputEl.dataset.dfKey = field.name;
    inputEl.className = "df-input";
    if (value !== "") inputEl.value = value;
  } else {
    inputEl = document.createElement("input");
    inputEl.type = "text";
    inputEl.id = fieldId;
    inputEl.dataset.dfKey = field.name;
    inputEl.className = "df-input";
    if (value !== "") inputEl.value = value;
  }
  container.appendChild(
    _dfMakeRow(field.display, inputEl, field.tooltip, field.required),
  );
}

function _dfRenderDropdown(container, field, data, formId, conditionals) {
  var select = document.createElement("select");
  select.id = formId + "_" + field.name;
  select.dataset.dfKey = field.name;
  select.className = "df-select";

  var emptyOpt = document.createElement("option");
  emptyOpt.value = "";
  emptyOpt.textContent = "\u2013 please select \u2013";
  select.appendChild(emptyOpt);

  field.type.forEach(function (opt) {
    var option = document.createElement("option");
    option.value = opt;
    option.textContent = opt;
    select.appendChild(option);
  });

  // Prefer data[field.name]; fall back to detecting which option key exists as object in data
  var currentValue =
    data && data[field.name] !== undefined ? String(data[field.name]) : "";
  if (!currentValue && data) {
    field.type.forEach(function (opt) {
      if (!currentValue && data[opt] !== null && data[opt] !== undefined) {
        currentValue = opt;
      }
    });
  }
  if (currentValue) select.value = currentValue;

  container.appendChild(
    _dfMakeRow(field.display, select, field.tooltip, field.required),
  );

  // Render conditional sub-blocks
  var conditionalDivs = [];
  conditionals.forEach(function (cond) {
    var ifVal = _dfGetIfValue(cond);
    var div = document.createElement("div");
    div.className = "df-conditional";
    div.setAttribute("data-if", ifVal);

    // If data[ifVal] is a nested object, use it as the sub-form data; otherwise use current data level
    var condData =
      data &&
      data[ifVal] !== undefined &&
      data[ifVal] !== null &&
      typeof data[ifVal] === "object" &&
      !Array.isArray(data[ifVal])
        ? data[ifVal]
        : data || {};

    _dfRenderFieldDefs(div, cond.items || [], condData, formId + "_" + ifVal);
    container.appendChild(div);
    conditionalDivs.push(div);
  });

  function updateConditionals() {
    var val = select.value;
    conditionalDivs.forEach(function (div) {
      div.style.display = div.getAttribute("data-if") === val ? "" : "none";
    });
  }
  select.addEventListener("change", updateConditionals);
  updateConditionals();
}

function _dfRenderList(container, field, data, formId) {
  var section = document.createElement("div");
  section.className = "df-list-section";
  section.dataset.dfListField = field.name;

  var header = document.createElement("div");
  header.className = "df-list-header";
  var headerLabel = document.createElement("span");
  headerLabel.className = "df-list-label";
  headerLabel.textContent = field.display;
  header.appendChild(headerLabel);
  var addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "btn btn-secondary btn-sm df-list-add-btn";
  addBtn.textContent = "+";
  addBtn.title = "Add item";
  header.appendChild(addBtn);
  section.appendChild(header);

  var itemsContainer = document.createElement("div");
  itemsContainer.className = "df-list-items";
  section.appendChild(itemsContainer);

  // Normalise: array stays as-is; object keyed by name is converted to array
  var raw = data && data[field.name];
  var listData = [];
  if (Array.isArray(raw)) {
    listData = raw;
  } else if (raw && typeof raw === "object") {
    listData = Object.keys(raw).map(function (key) {
      var val = raw[key];
      return val && typeof val === "object"
        ? Object.assign({ name: key }, val)
        : { name: key };
    });
  }

  var baseId = formId + "_" + field.name;
  listData.forEach(function (itemData) {
    _dfAddListItem(itemsContainer, field.items || [], itemData, baseId);
  });

  addBtn.addEventListener("click", function () {
    _dfAddListItem(itemsContainer, field.items || [], {}, baseId);
  });

  container.appendChild(section);
}

function _dfAddListItem(container, itemDefs, itemData, baseId) {
  var item = document.createElement("div");
  item.className = "df-list-item";

  // Count existing items to label this one
  var idx = container.querySelectorAll(".df-list-item").length + 1;

  var itemHeader = document.createElement("div");
  itemHeader.className = "df-list-item-bar";

  var itemLabel = document.createElement("span");
  itemLabel.className = "df-list-item-index";
  itemLabel.textContent = "#" + idx;
  itemHeader.appendChild(itemLabel);

  var deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "btn btn-danger btn-sm df-list-item-delete";
  deleteBtn.textContent = "\u00d7";
  deleteBtn.title = "Remove item";
  deleteBtn.addEventListener("click", function () {
    item.remove();
    // Re-number remaining items
    var siblings = container.querySelectorAll(".df-list-item-index");
    siblings.forEach(function (el, i) {
      el.textContent = "#" + (i + 1);
    });
  });
  itemHeader.appendChild(deleteBtn);
  item.appendChild(itemHeader);

  var itemContent = document.createElement("div");
  itemContent.className = "df-list-item-content";
  _dfRenderFieldDefs(
    itemContent,
    itemDefs,
    itemData,
    baseId + "_" + _dfNewId(),
  );
  item.appendChild(itemContent);

  container.appendChild(item);
}

function _dfRenderFieldDefs(container, fieldDefs, data, formId) {
  _dfProcessDefs(fieldDefs).forEach(function (processed) {
    var field = processed.field;
    if (!field.name) return;
    if (Array.isArray(field.type)) {
      _dfRenderDropdown(container, field, data, formId, processed.conditionals);
    } else if (field.type === "list") {
      _dfRenderList(container, field, data, formId);
    } else {
      _dfRenderSimple(container, field, data, formId);
    }
  });
}

/**
 * Renders a dynamic form based on _uiConfig[configKey] into the given container.
 * @param {HTMLElement} container - Target element; its content is replaced.
 * @param {string}      configKey - Key in _uiConfig (e.g. 'node').
 * @param {Object|null} data      - Pre-fill values, or null for an empty form.
 */
function renderDynamicForm(container, configKey, data) {
  container.innerHTML = "";
  if (!_uiConfig || !_uiConfig[configKey]) {
    container.innerHTML =
      '<p class="placeholder-text">Configuration for "' +
      configKey +
      '" not found.</p>';
    return;
  }
  var wrapper = document.createElement("div");
  wrapper.className = "df-form";
  _dfRenderFieldDefs(wrapper, _uiConfig[configKey], data || {}, _dfNewId());
  container.appendChild(wrapper);
}

// -- Node Form ----------------------------------------------------------------

// Tracks whether the currently open form was opened for 'new' or 'edit'
var _nodeFormMode = "new";

function _setNodeFormTitle(text) {
  var el = document.getElementById("node-form-title");
  if (el) el.textContent = text;
}

// true, if the node form was opened by a double click on a node in the workflow editor:
// the form is read-only, the button Back returns to the editor
var _nodeEditFromWorkflow = false;
var _nodeEditFromList = false;

// Menu Node -> Edit (empty form, nodeData undefined), button "Edit" in the node list (a stored node,
// fromList true) or double click on a node in the workflow editor (fromWorkflow true: read-only).
// Back is shown, if the form was opened from the node list or the workflow editor
function openNodeEdit(nodeData, fromWorkflow, fromList) {
  _nodeEditFromWorkflow = !!fromWorkflow;
  _nodeEditFromList = !fromWorkflow && !!fromList;
  ["node-edit-save", "node-edit-reset"].forEach(function (id) {
    var btn = document.getElementById(id);
    if (btn) btn.style.display = _nodeEditFromWorkflow ? "none" : "";
  });
  var backBtn = document.getElementById("node-edit-back");
  if (backBtn) {
    backBtn.style.display = _nodeEditFromWorkflow || _nodeEditFromList ? "" : "none";
    backBtn.title = _nodeEditFromWorkflow
      ? "Back to the workflow editor"
      : _nodeEditFromList
        ? "Back to the node list"
        : "";
  }
  _nodeFormMode = nodeData ? "edit" : "new";
  _setNodeFormTitle(
    !nodeData
      ? "Node – Edit"
      : _nodeEditFromWorkflow
        ? "Node – View " + _resourceNameVer(nodeData) + " (read-only)"
        : "Node – Edit " + _resourceNameVer(nodeData),
  );
  showPanel("node-edit");
  if (!_uiConfig) {
    showToast(
      "Configuration not yet loaded – please wait a moment and try again.",
      "info",
    );
    return;
  }
  renderDynamicForm(
    document.getElementById("node-edit-form-container"),
    "node",
    nodeData || null,
  );
  if (_nodeEditFromWorkflow) _setNodeFormReadOnly();
  _markNodeFormSaved();
}

// Disables all fields and buttons of the node form (except the tooltip buttons)
function _setNodeFormReadOnly() {
  var container = document.getElementById("node-edit-form-container");
  if (!container) return;
  container.querySelectorAll("input, select, textarea, button").forEach(function (el) {
    if (!el.classList.contains("df-tooltip-btn")) el.disabled = true;
  });
}

// Button Back of the node form: back to the workflow editor (opened from there, read-only) or to the
// node list (unsaved changes must be confirmed to be discarded)
function backFromNodeEdit() {
  if (_nodeEditFromList) {
    if (_isNodeFormDirty() && !window.confirm("The node has unsaved changes. Discard them?")) return;
    _markNodeFormSaved();
    _nodeEditFromList = false;
    openNodeList();
    return;
  }
  _markNodeFormSaved();
  _nodeEditFromWorkflow = false;
  showPanel("workflow-edit");
  requestAnimationFrame(_lgResizeCanvas);
}

// -- Dirty state of the node form ---------------------------------------------
// The form is dirty, if the data entered differs from the data after opening or the last save.
// Save is enabled only, if the form is dirty.
var _nodeFormSavedSnapshot = null;

function _nodeFormSnapshot() {
  var container = document.getElementById("node-edit-form-container");
  var wrapper = container && container.querySelector(".df-form");
  if (!wrapper || !_uiConfig || !_uiConfig.node) return null;
  return JSON.stringify(_dfCollectData(wrapper, _uiConfig.node));
}

function _markNodeFormSaved(snapshot) {
  _nodeFormSavedSnapshot = snapshot !== undefined ? snapshot : _nodeFormSnapshot();
  _updateNodeFormButtons();
}

function _isNodeFormDirty() {
  var snapshot = _nodeFormSnapshot();
  return snapshot !== null && snapshot !== _nodeFormSavedSnapshot;
}

function _updateNodeFormButtons() {
  var saveBtn = document.getElementById("node-edit-save");
  if (!saveBtn) return;
  var dirty = _isNodeFormDirty();
  saveBtn.disabled = !dirty;
  saveBtn.title = dirty ? "" : "No changes to save";
}

// -- Form data collection -----------------------------------------------------
//
// _dfCollectData(containerEl, fieldDefs)
//   Reads the rendered form DOM back into a plain JS object.
//
//   Dropdowns (type: [...]):
//     The selected value becomes a KEY in the result whose value is
//     the collected sub-object of the matching conditional block.
//     This keeps top-level fields with the same name (e.g. "name") separate.
//     Example: type=image selected → result.image = {name, version}
//
//   Lists (type: "list"):
//     Returns an array of collected item objects.  A caller may later convert
//     the array to a named dict (see _nodeFormDataToApi).
// -----------------------------------------------------------------------------

function _dfFindDirectInput(containerEl, dfKey) {
  var children = containerEl.children;
  for (var i = 0; i < children.length; i++) {
    var child = children[i];
    if (child.classList.contains("df-row")) {
      var el = child.querySelector('[data-df-key="' + dfKey + '"]');
      if (el) return el;
    }
  }
  return null;
}

function _dfFindConditionalDiv(containerEl, ifVal) {
  var children = containerEl.children;
  for (var i = 0; i < children.length; i++) {
    var child = children[i];
    if (
      child.classList.contains("df-conditional") &&
      child.getAttribute("data-if") === ifVal
    ) {
      return child;
    }
  }
  return null;
}

function _dfFindListSection(containerEl, fieldName) {
  var children = containerEl.children;
  for (var i = 0; i < children.length; i++) {
    var child = children[i];
    if (
      child.classList.contains("df-list-section") &&
      child.dataset.dfListField === fieldName
    ) {
      return child;
    }
  }
  return null;
}

function _dfCollectData(containerEl, fieldDefs) {
  var result = {};
  _dfProcessDefs(fieldDefs).forEach(function (item) {
    var field = item.field;
    if (!field.name) return;

    if (Array.isArray(field.type)) {
      var select = _dfFindDirectInput(containerEl, field.name);
      if (!select) return;
      var val = select.value;
      if (!val) return;
      // Find the matching conditional definition
      var matchedCond = null;
      item.conditionals.forEach(function (cond) {
        if (_dfGetIfValue(cond) === val) matchedCond = cond;
      });
      if (matchedCond) {
        var condDiv = _dfFindConditionalDiv(containerEl, val);
        result[val] = condDiv
          ? _dfCollectData(condDiv, matchedCond.items || [])
          : {};
      } else {
        // No conditional defined – store value directly
        result[field.name] = val;
      }
    } else if (field.type === "list") {
      var section = _dfFindListSection(containerEl, field.name);
      if (!section) return;
      var listItemsEl = section.querySelector(".df-list-items");
      if (!listItemsEl) return;
      var items = [];
      Array.prototype.forEach.call(listItemsEl.children, function (listItem) {
        if (!listItem.classList.contains("df-list-item")) return;
        var content = listItem.querySelector(".df-list-item-content");
        if (!content) return;
        items.push(_dfCollectData(content, field.items || []));
      });
      result[field.name] = items;
    } else {
      var input = _dfFindDirectInput(containerEl, field.name);
      if (!input) return;
      if (field.type === "bool") {
        result[field.name] = input.checked;
      } else if (field.type === "number") {
        result[field.name] = input.value !== "" ? Number(input.value) : null;
      } else {
        result[field.name] = input.value;
      }
    }
  });
  return result;
}

// Converts the generic collected object into the node JSON the API expects:
//   input/output arrays → named dict; channel type sub-object flattened with
//   a "type" field added.
function _nodeFormDataToApi(raw) {
  var api = {};
  Object.keys(raw).forEach(function (key) {
    if (key === "input" || key === "output") return;
    api[key] = raw[key];
  });
  ["input", "output"].forEach(function (channelKey) {
    if (!Array.isArray(raw[channelKey])) return;
    var dict = {};
    raw[channelKey].forEach(function (item) {
      var name = item.name;
      if (!name) return;
      var val = {};
      Object.keys(item).forEach(function (k) {
        if (k === "name") return;
        var v = item[k];
        if (
          v !== null &&
          v !== undefined &&
          typeof v === "object" &&
          !Array.isArray(v)
        ) {
          // sub-object from a dropdown conditional → flatten it with type key.
          // Empty fields are dropped (e.g. the unused one of env var / command line parameter)
          val.type = k;
          Object.keys(v).forEach(function (subKey) {
            var subVal = v[subKey];
            if (subVal !== "" && subVal !== null && subVal !== undefined) {
              val[subKey] = subVal;
            }
          });
        } else if (v !== "" && v !== null && v !== undefined) {
          val[k] = v;
        }
      });
      dict[name] = val;
    });
    api[channelKey] = dict;
  });
  return api;
}

function handleNodeFormSave() {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (!_uiConfig || !_uiConfig.node) {
    showToast("Configuration not loaded", "error");
    return;
  }
  var container = document.getElementById("node-edit-form-container");
  var wrapper = container && container.querySelector(".df-form");
  if (!wrapper) {
    showToast("No form loaded", "error");
    return;
  }
  var raw = _dfCollectData(wrapper, _uiConfig.node);
  var sentSnapshot = JSON.stringify(raw);
  var nodeData = _nodeFormDataToApi(raw);
  apiCall("POST", "/node/upload", { content: JSON.stringify(nodeData) })
    .then(function (result) {
      if (result.success) {
        showToast(nodeData.name ? "Node '" + nodeData.name + "' saved" : "Node saved", "success");
        _markNodeFormSaved(sentSnapshot);
      } else {
        showToast(_resultError(result, "Error saving"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- Icon buttons of the lists ---------------------------------------------------
// The actions of the lists are shown as icons (to save space). The name of the action is the
// tooltip and the accessible label. A tooltip set later (e.g. the reason why the button is
// disabled) replaces the name. Order of the actions in a row: look at it (Metadata, Data, Content),
// change it (Edit), run it (Run), export it (Download), remove it (Delete).
var LIST_ICONS = {
  metadata: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5v.01"/>',
  data:
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>' +
    '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  content: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  edit: '<path d="M17 3l4 4L8 20H4v-4L17 3z"/><path d="M14 6l4 4"/>',
  run: '<polygon points="7 4 20 12 7 20 7 4" fill="currentColor"/>',
  download: '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>',
  delete:
    '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>',
  running: '<path class="icon-spin" d="M21 12a9 9 0 1 1-6.2-8.6"/>',
};

function _listIconSvg(icon) {
  return (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + LIST_ICONS[icon] + "</svg>"
  );
}

function _setListIcon(button, icon, label) {
  button.classList.add("btn-icon-sm");
  button.innerHTML = _listIconSvg(icon);
  button.title = label;
  button.setAttribute("aria-label", label);
}

// -- Node List ----------------------------------------------------------------

function openNodeList() {
  showPanel("node-list");
  var lv = document.getElementById("node-list-view");
  var rv = document.getElementById("node-metadata-view");
  if (lv) lv.style.display = "";
  if (rv) rv.style.display = "none";
  loadNodeList();
}

function loadNodeList() {
  if (!_loginToken) {
    document.getElementById("node-list-container").innerHTML =
      '<p class="placeholder-text">Please log in first.</p>';
    return;
  }
  document.getElementById("node-list-container").innerHTML =
    '<p class="placeholder-text">Loading\u2026</p>';
  apiCall("POST", "/node/list", {})
    .then(function (result) {
      if (result.success) {
        _renderNodeList(result.nodes || []);
      } else {
        showToast(_resultError(result, "Error loading"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function _nodeType(node) {
  return node.kind || "\u2013";
}

function _renderNodeList(nodes) {
  var container = document.getElementById("node-list-container");
  if (!nodes.length) {
    container.innerHTML = '<p class="placeholder-text">No nodes available.</p>';
    return;
  }

  var table = document.createElement("table");
  table.className = "node-list-table";

  var thead = document.createElement("thead");
  thead.innerHTML =
    "<tr><th>Name:Version</th><th>Type</th><th>Date</th><th></th></tr>";
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  nodes.forEach(function (node) {
    var tr = document.createElement("tr");

    var nameVer =
      (node.name || "") +
      ":" +
      (node._version !== undefined ? node._version : "?");
    var hash = node._hash || "";

    var tdName = document.createElement("td");
    tdName.textContent = nameVer;
    tr.appendChild(tdName);

    var tdType = document.createElement("td");
    tdType.textContent = _nodeType(node);
    tr.appendChild(tdType);

    var tdDate = document.createElement("td");
    tdDate.textContent = node._date || "-";
    tr.appendChild(tdDate);

    var tdActions = document.createElement("td");
    tdActions.className = "node-list-actions";

    var metadataBtn = document.createElement("button");
    metadataBtn.type = "button";
    metadataBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(metadataBtn, "metadata", "Metadata");
    metadataBtn.addEventListener(
      "click",
      (function (n) {
        return function () {
          openNodeMetadataView(n);
        };
      })(node),
    );
    tdActions.appendChild(metadataBtn);

    var editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-primary btn-sm";
    _setListIcon(editBtn, "edit", "Edit");
    editBtn.addEventListener(
      "click",
      (function (n) {
        return function () {
          if (!_loginToken) {
            showToast("Please log in first", "error");
            return;
          }
          _fetchEntry("node", n._hash, false)
            .then(function (result) {
              openNodeEdit(result.entry, false, true);
            })
            .catch(function (e) {
              showToast("Error: " + e.message, "error");
            });
        };
      })(node),
    );
    tdActions.appendChild(editBtn);

    var dlBtn = document.createElement("button");
    dlBtn.type = "button";
    dlBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(dlBtn, "download", "Download");
    dlBtn.addEventListener(
      "click",
      (function (n, nv) {
        return function () {
          handleNodeDownloadDirect(n, nv);
        };
      })(node, nameVer),
    );
    tdActions.appendChild(dlBtn);

    var delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn btn-danger btn-sm df-list-item-delete";
    _setListIcon(delBtn, "delete", "Delete");
    delBtn.addEventListener(
      "click",
      (function (h, nv) {
        return function () {
          handleNodeDelete(h, nv);
        };
      })(hash, nameVer),
    );
    tdActions.appendChild(delBtn);

    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  _enhanceListTable(table, container.id);
  container.innerHTML = "";
  container.appendChild(table);
}

// Lists contain only a summary of each entry (hash, name, version, date). The complete entry is
// fetched from the backend when it is needed (Metadata, Download, Edit): kind "node", "workflow", "run".
// exportText false: result.entry is the stored entry. exportText true: result.content is the
// upload text without internal fields ('node { ... };') and result.filename a proposed file name.
// "hash" is a hash or a referer object { name, version }.
function _fetchEntry(kind, hash, exportText) {
  var body = typeof hash === "object" ? Object.assign({}, hash) : { hash: hash };
  body.export = !!exportText;
  return apiCall("POST", "/" + kind + "/get", body).then(
    function (result) {
      if (!result.success) {
        throw new Error(_resultError(result, "Error loading the " + kind));
      }
      return result;
    },
  );
}

// Lets the browser save a text as file
function _saveTextFile(filename, text, mimeType) {
  var blob = new Blob([text], { type: mimeType || "text/plain" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

// Shows the complete entry (fetched from the backend) in a metadata view of a list panel
function _showMetadataView(kind, label, summary) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  _fetchEntry(kind, summary._hash, false)
    .then(function (result) {
      var lv = document.getElementById(kind + "-list-view");
      var rv = document.getElementById(kind + "-metadata-view");
      if (lv) lv.style.display = "none";
      if (rv) rv.style.display = "";
      var h = document.getElementById(kind + "-metadata-title");
      if (h) h.textContent = label + " \u2013 Metadata " + _resourceNameVer(result.entry);
      var pre = document.getElementById(kind + "-metadata-pre");
      if (pre) pre.textContent = JSON.stringify(result.entry, null, 2);
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// Downloads a node or workflow in the upload format (can be uploaded again)
function _downloadExport(kind, summary, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  _fetchEntry(kind, summary._hash, true)
    .then(function (result) {
      _saveTextFile(result.filename, result.content, "text/plain");
      showToast(nameVer + " downloaded as " + result.filename, "success");
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// "name:version" of a stored resource (node, workflow, run, data), used in titles
function _resourceNameVer(entry) {
  var version = entry._version !== undefined ? entry._version : "?";
  return (entry.name || "") + ":" + version;
}

function openNodeMetadataView(node) {
  _showMetadataView("node", "Node", node);
}

// Back from a metadata view to the list
function _closeMetadataView(kind) {
  var rv = document.getElementById(kind + "-metadata-view");
  var lv = document.getElementById(kind + "-list-view");
  if (rv) rv.style.display = "none";
  if (lv) lv.style.display = "";
}

function closeNodeMetadataView() {
  _closeMetadataView("node");
}

function handleNodeDownloadDirect(node, nameVer) {
  _downloadExport("node", node, nameVer);
}

function handleNodeDelete(hash, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  apiCall("POST", "/node/delete", { hash: hash })
    .then(function (result) {
      if (result.success) {
        showToast("Node deleted", "success");
        loadNodeList();
      } else {
        showToast(_resultError(result, "Error deleting"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- Data List / Upload --------------------------------------------------------

function dataUploadFileSelected(input) {
  _onFileSelected(input, _dataUploadState, "data-upload-filename");
}

// Uploads the selected plain file. The backend generates the data definition (name: file name
// with '.' replaced by '_' and a leading '_' if it starts with a digit, type "file", storage "platform", hash "true", format "any").
function handleDataUpload() {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  var file = _dataUploadState.file;
  if (!file) {
    showToast("Please select a file first", "error");
    return;
  }
  var formData = new FormData();
  formData.append("file", file, file.name);
  _guardedCall("/data/upload-file", function () {
    return fetch("/data/upload-file", {
      method: "POST",
      headers: { "X-Auth-Token": _loginToken },
      body: formData,
    }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (t) {
          throw new Error("HTTP " + res.status + ": " + t);
        });
      }
      return res.json();
    });
  })
    .then(function (result) {
      if (result.success) {
        showToast(
          "Data '" + result.name + "' uploaded",
          "success",
        );
        _clearFileSelection(
          _dataUploadState,
          "data-upload-file-input",
          "data-upload-filename",
        );
      } else {
        showToast(_resultError(result, "Error uploading"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function dataMetadataUploadFileSelected(input) {
  _onFileSelected(
    input,
    _dataMetadataUploadState,
    "data-metadata-upload-filename",
  );
}

// Uploads a file with one or more data definitions ('data { ... };' blocks or JSON)
function handleDataMetadataUpload() {
  _uploadFromFile({
    state: _dataMetadataUploadState,
    endpoint: "/data/upload",
    noun: ["data entry", "data entries"],
    fileInputId: "data-metadata-upload-file-input",
    filenameInputId: "data-metadata-upload-filename",
  });
}

// The data list panel shows all data (menu Data -> List) or the data of one run (button "Data" in
// the run list). _dataListRun is null, or { hash, nameVer } of the run whose data is shown.
var _dataListRun = null;

function openDataList() {
  _dataListRun = null;
  showPanel("data-list");
  closeDataView();
  loadDataList();
}

// Shows the data of a run: the entries referenced in its metadata under "_channel_bindings"
function openRunData(runEntry, nameVer) {
  _dataListRun = { hash: runEntry._hash, nameVer: nameVer };
  showPanel("data-list");
  closeDataView();
  loadDataList();
}

function _updateDataListHeader() {
  var title = document.getElementById("data-list-title");
  var back = document.getElementById("data-list-back");
  if (title) {
    title.textContent = _dataListRun
      ? "Run \u2013 Data " + _dataListRun.nameVer
      : "Data \u2013 List";
  }
  if (back) back.style.display = _dataListRun ? "" : "none";
}

function loadDataList() {
  var container = document.getElementById("data-list-container");
  _updateDataListHeader();
  if (!_loginToken) {
    container.innerHTML = '<p class="placeholder-text">Please log in first.</p>';
    return;
  }
  container.innerHTML = '<p class="placeholder-text">Loading\u2026</p>';
  var request = _dataListRun
    ? apiCall("POST", "/run/data", { hash: _dataListRun.hash })
    : apiCall("POST", "/data/list", {});
  request
    .then(function (result) {
      if (result.success) {
        _renderDataList(result.data || [], !!_dataListRun);
      } else {
        showToast(_resultError(result, "Error loading"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// showChannel: data of a run, the first column shows the channel of the run
function _renderDataList(dataEntries, showChannel) {
  var container = document.getElementById("data-list-container");
  if (!dataEntries.length) {
    container.innerHTML = showChannel
      ? '<p class="placeholder-text">The run has no data.</p>'
      : '<p class="placeholder-text">No data available.</p>';
    return;
  }

  var table = document.createElement("table");
  table.className = "node-list-table";

  var thead = document.createElement("thead");
  thead.innerHTML =
    "<tr>" + (showChannel ? "<th>Channel</th>" : "") +
    "<th>Name</th><th>Version</th><th>Date</th><th></th></tr>";
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  dataEntries.forEach(function (dataEntry) {
    var tr = document.createElement("tr");
    var version = dataEntry._version !== undefined ? dataEntry._version : "?";
    var nameVer = (dataEntry.name || "") + ":" + version;
    var missing = !!dataEntry._missing;

    var cells = missing
      ? ["(data deleted)", "-", "-"]
      : [dataEntry.name || "", String(version), dataEntry._date || "-"];
    if (showChannel) cells.unshift(dataEntry._channel || "");
    cells.forEach(function (text) {
      var td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });

    if (missing) {
      var tdMissing = document.createElement("td");
      tdMissing.className = "node-list-actions";
      tdMissing.title = "The data entry " + dataEntry._hash + " doesn't exist anymore";
      tr.appendChild(tdMissing);
      tbody.appendChild(tr);
      return;
    }

    var tdActions = document.createElement("td");
    tdActions.className = "node-list-actions";

    var metadataBtn = document.createElement("button");
    metadataBtn.type = "button";
    metadataBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(metadataBtn, "metadata", "Metadata");
    metadataBtn.addEventListener("click", function () {
      openDataMetadataView(dataEntry);
    });
    tdActions.appendChild(metadataBtn);

    var contentBtn = document.createElement("button");
    contentBtn.type = "button";
    contentBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(contentBtn, "content", "Content");
    if (dataEntry.type !== "file") {
      contentBtn.disabled = true;
      contentBtn.title = "Only the content of files can be shown";
    }
    contentBtn.addEventListener("click", function () {
      openDataContentView(dataEntry, nameVer);
    });
    tdActions.appendChild(contentBtn);

    var dlBtn = document.createElement("button");
    dlBtn.type = "button";
    dlBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(dlBtn, "download", "Download");
    if (dataEntry.type !== "file") {
      dlBtn.disabled = true;
      dlBtn.title = "Only files can be downloaded";
    }
    dlBtn.addEventListener("click", function () {
      handleDataDownload(dataEntry, nameVer);
    });
    tdActions.appendChild(dlBtn);

    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  // own sort/filter state for the data of runs: the columns differ
  _enhanceListTable(table, container.id + (showChannel ? "-run" : ""));
  container.innerHTML = "";
  container.appendChild(table);
}

function _showDataView(title, text) {
  var lv = document.getElementById("data-list-view");
  var rv = document.getElementById("data-view");
  if (lv) lv.style.display = "none";
  if (rv) rv.style.display = "";
  var h = document.getElementById("data-view-title");
  if (h) h.textContent = title;
  var pre = document.getElementById("data-view-pre");
  if (pre) pre.textContent = text;
}

// Shows the definition of a data entry
function openDataMetadataView(dataEntry) {
  _showDataView("Data \u2013 Metadata", JSON.stringify(dataEntry, null, 2));
}

// Maximal number of bytes shown by "Content"; larger files are truncated (Download shows all)
var DATA_CONTENT_MAX_BYTES = 1024 * 1024;

// Shows the content of the file of a data entry
function openDataContentView(dataEntry, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  _fetchDataContent(dataEntry)
    .then(function (blob) {
      var shown = blob.size > DATA_CONTENT_MAX_BYTES ? blob.slice(0, DATA_CONTENT_MAX_BYTES) : blob;
      return shown.arrayBuffer().then(function (buffer) {
        var bytes = new Uint8Array(buffer);
        var title = "Data \u2013 Content " + nameVer;
        if (bytes.indexOf(0) >= 0) {
          _showDataView(
            title,
            "(binary content, " + blob.size + " bytes. Use \u00abDownload\u00bb to get the file)",
          );
          return;
        }
        var text = new TextDecoder("utf-8").decode(bytes);
        if (blob.size > DATA_CONTENT_MAX_BYTES) {
          text +=
            "\n\n\u2026 (truncated: first " + DATA_CONTENT_MAX_BYTES + " of " + blob.size +
            " bytes shown. Use \u00abDownload\u00bb to get the file)";
        }
        _showDataView(title, text);
      });
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// Fetches the content of the file of a data entry. Errors are returned by the backend as JSON
function _fetchDataContent(dataEntry) {
  return _guardedCall("/data/content", function () {
    return fetch("/data/content", {
      method: "POST",
      headers: { "X-Auth-Token": _loginToken, "Content-Type": "application/json" },
      body: JSON.stringify({ hash: dataEntry._hash }),
    }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (t) {
          throw new Error("HTTP " + res.status + ": " + t);
        });
      }
      var contentType = res.headers.get("Content-Type") || "";
      if (contentType.indexOf("application/json") === 0) {
        return res.json().then(function (result) {
          throw new Error(_resultError(result, "Error loading the data"));
        });
      }
      return res.blob();
    });
  });
}

function closeDataView() {
  var rv = document.getElementById("data-view");
  var lv = document.getElementById("data-list-view");
  if (rv) rv.style.display = "none";
  if (lv) lv.style.display = "";
}

// Downloads the content of a data entry (type file). Errors are returned by the backend as JSON
function handleDataDownload(dataEntry, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  _fetchDataContent(dataEntry)
    .then(function (blob) {
      var userPath = dataEntry.user_path || "";
      var filename = userPath.split(/[\\/]/).pop() || dataEntry.name || "data";
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
      showToast("Data " + nameVer + " downloaded", "success");
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- List tables: sorting and filtering ----------------------------------------

// State per list (key: id of the container), so that a refresh keeps sorting and filter
var _listTableState = {};

// Makes a list table sortable (click on a column header, click again to reverse) and adds a
// filter row in the table head. The filter is a regular expression (case insensitive), matched
// against the text of all data columns of a row. Columns with an empty header (actions) are ignored.
function _enhanceListTable(table, key) {
  var state = _listTableState[key] || (_listTableState[key] = { col: -1, asc: true, filter: "" });
  var thead = table.tHead;
  var tbody = table.tBodies[0];
  var headerCells = Array.prototype.slice.call(thead.rows[0].cells);
  var dataCols = [];
  headerCells.forEach(function (th, i) {
    if (th.textContent.trim()) dataCols.push(i);
  });
  var allRows = Array.prototype.slice.call(tbody.rows);

  function cellText(row, col) {
    return row.cells[col] ? row.cells[col].textContent.trim() : "";
  }

  // sorting
  function sortRows() {
    headerCells.forEach(function (th, i) {
      th.classList.toggle("sorted-asc", i === state.col && state.asc);
      th.classList.toggle("sorted-desc", i === state.col && !state.asc);
    });
    if (state.col < 0) return;
    var sorted = allRows.slice().sort(function (a, b) {
      var cmp = cellText(a, state.col).localeCompare(cellText(b, state.col), undefined, {
        numeric: true,
        sensitivity: "base",
      });
      return state.asc ? cmp : -cmp;
    });
    sorted.forEach(function (row) {
      tbody.appendChild(row);
    });
  }
  dataCols.forEach(function (col) {
    var th = headerCells[col];
    th.classList.add("sortable");
    th.title = "Click to sort";
    th.addEventListener("click", function () {
      if (state.col === col) {
        state.asc = !state.asc;
      } else {
        state.col = col;
        state.asc = true;
      }
      sortRows();
    });
  });

  // filter row
  var filterRow = thead.insertRow(-1);
  filterRow.className = "list-filter-row";
  var filterCell = document.createElement("th");
  filterCell.colSpan = headerCells.length;
  var input = document.createElement("input");
  input.type = "text";
  input.className = "df-input list-filter-input";
  input.placeholder = "Filter (regular expression)";
  input.value = state.filter;
  var counter = document.createElement("span");
  counter.className = "list-filter-count";
  filterCell.appendChild(input);
  filterCell.appendChild(counter);
  filterRow.appendChild(filterCell);

  function applyFilter() {
    state.filter = input.value;
    var regex = null;
    input.classList.remove("invalid");
    if (state.filter) {
      try {
        regex = new RegExp(state.filter, "i");
      } catch (e) {
        input.classList.add("invalid");
        input.title = e.message;
      }
    }
    if (!input.classList.contains("invalid")) input.title = "";
    var visible = 0;
    allRows.forEach(function (row) {
      var text = dataCols
        .map(function (col) {
          return cellText(row, col);
        })
        .join(" ");
      var show = !regex || regex.test(text);
      row.style.display = show ? "" : "none";
      if (show) visible++;
    });
    counter.textContent = visible + " / " + allRows.length;
  }
  input.addEventListener("input", applyFilter);

  sortRows();
  applyFilter();
}

// -- Workflow List ------------------------------------------------------------

function openWorkflowList() {
  showPanel("workflow-list");
  var lv = document.getElementById("workflow-list-view");
  var rv = document.getElementById("workflow-metadata-view");
  if (lv) lv.style.display = "";
  if (rv) rv.style.display = "none";
  loadWorkflowList();
}

function loadWorkflowList() {
  if (!_loginToken) {
    document.getElementById("workflow-list-container").innerHTML =
      '<p class="placeholder-text">Please log in first.</p>';
    return;
  }
  document.getElementById("workflow-list-container").innerHTML =
    '<p class="placeholder-text">Loading\u2026</p>';
  apiCall("POST", "/workflow/list", {})
    .then(function (result) {
      if (result.success) {
        _renderWorkflowList(result.workflows || []);
      } else {
        showToast(_resultError(result, "Error loading"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function _renderWorkflowList(workflows) {
  var container = document.getElementById("workflow-list-container");
  if (!workflows.length) {
    container.innerHTML =
      '<p class="placeholder-text">No workflows available.</p>';
    return;
  }

  var table = document.createElement("table");
  table.className = "node-list-table";

  var thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Name:Version</th><th>Date</th><th></th></tr>";
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  workflows.forEach(function (workflow) {
    var tr = document.createElement("tr");

    var nameVer =
      (workflow.name || "") +
      ":" +
      (workflow._version !== undefined ? workflow._version : "?");
    var hash = workflow._hash || "";

    var tdName = document.createElement("td");
    tdName.textContent = nameVer;
    tr.appendChild(tdName);

    var tdDate = document.createElement("td");
    tdDate.textContent = workflow._date || "-";
    tr.appendChild(tdDate);

    var tdActions = document.createElement("td");
    tdActions.className = "node-list-actions";

    var metadataBtn = document.createElement("button");
    metadataBtn.type = "button";
    metadataBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(metadataBtn, "metadata", "Metadata");
    metadataBtn.addEventListener(
      "click",
      (function (wfl) {
        return function () {
          openWorkflowMetadataView(wfl);
        };
      })(workflow),
    );
    tdActions.appendChild(metadataBtn);

    var runBtn = document.createElement("button");
    runBtn.type = "button";
    runBtn.className = "btn btn-success btn-sm";
    _setListIcon(runBtn, "run", "Run");
    // a workflow with inputs is a sub workflow: its inputs are bound by the workflow using it
    if (workflow.inputs && workflow.inputs.length > 0) {
      runBtn.disabled = true;
      runBtn.title =
        "This workflow has inputs (" + workflow.inputs.join(", ") +
        "). It can only run as sub workflow of another workflow";
    }
    runBtn.addEventListener(
      "click",
      (function (h, nv) {
        return function () {
          handleWorkflowRun(h, nv, this);
        };
      })(hash, nameVer),
    );

    var editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(editBtn, "edit", "Edit");
    editBtn.addEventListener(
      "click",
      (function (h, nv) {
        return function () {
          openWorkflowEditFor(h, nv);
        };
      })(hash, nameVer),
    );
    tdActions.appendChild(editBtn);
    tdActions.appendChild(runBtn); // order: Metadata, Edit, Run, Download, Delete

    var dlBtn = document.createElement("button");
    dlBtn.type = "button";
    dlBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(dlBtn, "download", "Download");
    dlBtn.addEventListener(
      "click",
      (function (wfl, nv) {
        return function () {
          handleWorkflowDownloadDirect(wfl, nv);
        };
      })(workflow, nameVer),
    );
    tdActions.appendChild(dlBtn);

    var delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn btn-danger btn-sm df-list-item-delete";
    _setListIcon(delBtn, "delete", "Delete");
    delBtn.addEventListener(
      "click",
      (function (h, nv) {
        return function () {
          handleWorkflowDelete(h, nv);
        };
      })(hash, nameVer),
    );
    tdActions.appendChild(delBtn);

    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  _enhanceListTable(table, container.id);
  container.innerHTML = "";
  container.appendChild(table);
}

// Starts a run of the workflow in the backend. The request returns when the run has finished
function handleWorkflowRun(hash, nameVer, button) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (_apiBusyToast()) return;
  button.disabled = true;
  button.dataset.running = "1";
  // the button is an icon (lists) or a text (workflow editor): its content is restored after the run
  var content = button.innerHTML;
  var title = button.title;
  if (button.classList.contains("btn-icon-sm")) {
    button.innerHTML = _listIconSvg("running");
    button.title = "Running…";
  } else {
    button.textContent = "Running…";
  }
  // the toast shows the seconds since the start, updated every second while the run is active
  var owner = "run-" + hash + "-" + Date.now();
  var start = Date.now();
  var seconds = function () {
    return Math.floor((Date.now() - start) / 1000);
  };
  _showOwnedToast(owner, "Run of " + nameVer + " running: 0 s", "info");
  var timer = setInterval(function () {
    _updateOwnedToast(owner, "Run of " + nameVer + " running: " + seconds() + " s");
  }, 1000);
  apiCall("POST", "/workflow/run", { hash: hash })
    .then(function (result) {
      if (result.success) {
        showToast(
          "Run " + result.name + ":" + result.version + " finished successfully after " + seconds() + " s",
          "success",
        );
      } else {
        showToast(
          _resultError(result, "Run of " + nameVer + " failed") + " (after " + seconds() + " s)",
          "error",
        );
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message + " (after " + seconds() + " s)", "error");
    })
    .then(function () {
      clearInterval(timer);
      delete button.dataset.running;
      button.disabled = false;
      button.innerHTML = content;
      button.title = title;
    });
}

function openWorkflowMetadataView(workflow) {
  _showMetadataView("workflow", "Workflow", workflow);
}

function closeWorkflowMetadataView() {
  _closeMetadataView("workflow");
}

function handleWorkflowDownloadDirect(workflow, nameVer) {
  _downloadExport("workflow", workflow, nameVer);
}

function handleWorkflowDelete(hash, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  apiCall("POST", "/workflow/delete", { hash: hash })
    .then(function (result) {
      if (result.success) {
        showToast("Workflow deleted", "success");
        loadWorkflowList();
      } else {
        showToast(_resultError(result, "Error deleting"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- Run List -----------------------------------------------------------------

function openRunList() {
  showPanel("run-list");
  closeRunMetadataView();
  loadRunList();
}

function loadRunList() {
  var container = document.getElementById("run-list-container");
  if (!_loginToken) {
    container.innerHTML = '<p class="placeholder-text">Please log in first.</p>';
    return;
  }
  container.innerHTML = '<p class="placeholder-text">Loading\u2026</p>';
  apiCall("POST", "/run/list", {})
    .then(function (result) {
      if (result.success) {
        _renderRunList(result.runs || []);
      } else {
        showToast(_resultError(result, "Error loading"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

function _renderRunList(runs) {
  var container = document.getElementById("run-list-container");
  if (!runs.length) {
    container.innerHTML = '<p class="placeholder-text">No runs available.</p>';
    return;
  }

  var table = document.createElement("table");
  table.className = "node-list-table";

  var thead = document.createElement("thead");
  thead.innerHTML =
    "<tr><th>Name</th><th>Version</th><th>Date</th><th></th></tr>";
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  runs.forEach(function (runEntry) {
    var tr = document.createElement("tr");
    var version = runEntry._version !== undefined ? runEntry._version : "?";
    var nameVer = (runEntry.name || "") + ":" + version;

    [runEntry.name || "", String(version), runEntry._date || "-"].forEach(
      function (text) {
        var td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      },
    );

    var tdActions = document.createElement("td");
    tdActions.className = "node-list-actions";

    var metadataBtn = document.createElement("button");
    metadataBtn.type = "button";
    metadataBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(metadataBtn, "metadata", "Metadata");
    metadataBtn.addEventListener("click", function () {
      openRunMetadataView(runEntry);
    });
    tdActions.appendChild(metadataBtn);

    var dataBtn = document.createElement("button");
    dataBtn.type = "button";
    dataBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(dataBtn, "data", "Data");
    dataBtn.title = "Show the data of the run (inputs and outputs saved in the data store)";
    dataBtn.addEventListener("click", function () {
      openRunData(runEntry, nameVer);
    });
    tdActions.appendChild(dataBtn);

    var dlBtn = document.createElement("button");
    dlBtn.type = "button";
    dlBtn.className = "btn btn-secondary btn-sm";
    _setListIcon(dlBtn, "download", "Download");
    dlBtn.addEventListener("click", function () {
      handleRunDownload(runEntry, nameVer);
    });
    tdActions.appendChild(dlBtn);

    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  _enhanceListTable(table, container.id);
  container.innerHTML = "";
  container.appendChild(table);
}

function openRunMetadataView(runEntry) {
  _showMetadataView("run", "Run", runEntry);
}

function closeRunMetadataView() {
  var rv = document.getElementById("run-metadata-view");
  var lv = document.getElementById("run-list-view");
  if (rv) rv.style.display = "none";
  if (lv) lv.style.display = "";
}

// Runs can't be uploaded: the complete entry is downloaded as JSON (fetched from the backend)
function handleRunDownload(runEntry, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  _fetchEntry("run", runEntry._hash, false)
    .then(function (result) {
      var entry = result.entry;
      var filename = "run_" + (entry.name || "run") + "_" + (entry._version || "1") + ".json";
      _saveTextFile(filename, JSON.stringify(entry, null, 2), "application/json");
      showToast("Run " + nameVer + " downloaded as " + filename, "success");
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// -- LiteGraph / Workflow Editor -----------------------------------------------

// Constant types: widget used to edit a value of that type, its default and the property type
var PARMA_CONSTANT_TYPES = {
  str:   { title: "StrConstant",   widget: "text",   value: "",    propType: "string" },
  int:   { title: "IntConstant",   widget: "number", value: 0,     propType: "number", options: { precision: 0, step: 10 } },
  float: { title: "FloatConstant", widget: "number", value: 0.0,   propType: "number", options: { precision: 3 } },
  bool:  { title: "BoolConstant",  widget: "toggle", value: false, propType: "boolean" },
  json:  { title: "JsonConstant",  widget: "text",   value: "",    propType: "string" },
};

(function registerParmaNodeTypes() {
  if (typeof LiteGraph === "undefined") return;

  // EnvVarValue: provides an environment variable value to a node
  function EnvVarValue() {
    this.addOutput("value", "environment_var");
    this.addProperty("value", "", "string");
    this.widget = this.addWidget("text", "value", "", "value");
    this.widgets_start_y = LiteGraph.NODE_SLOT_HEIGHT+5;
  }
  EnvVarValue.title = "EnvVarValue";
  EnvVarValue.desc = "Defines the value of an environment variable";
  EnvVarValue.prototype.onExecute = function () {
    this.setOutputData(0, this.properties["value"]);
  };
  EnvVarValue.prototype.getTitle = function () {
    return this.flags.collapsed ? this.properties.value : this.title;
  };
  EnvVarValue.prototype.onDrawBackground = function () {
    value = this.properties["value"];
    this.outputs[0].label = value ? this.properties["value"] : null;
  };
  LiteGraph.registerNodeType("core/env_var_value", EnvVarValue);

  // InputFile: references data from the data store as input
  function InputFile() {
    this.addOutput("data", "file");
    this.addProperty("name", "", "string");
    this.addProperty("version", "", "string");
    this.widget = this.addWidget("text", "name", "", "name");
    this.widget = this.addWidget("text", "version", "", "version");
    this.widgets_start_y = LiteGraph.NODE_SLOT_HEIGHT+5;
  }
  InputFile.title = "InputFile";
  InputFile.desc =
    "Defines data by its name and version in the data store, which will be resolved to a file to be read by a node";
  InputFile.prototype.getTitle = function () {
    return this.flags.collapsed
      ? this.properties.name + ":" + this.properties.version
      : this.title;
  };
  InputFile.prototype.onDrawBackground = function () {
    var n = this.properties["name"];
    var v = this.properties["version"];
    this.outputs[0].label = n || v ? n + ":" + v : null;
  };
  LiteGraph.registerNodeType("core/infile", InputFile);

  // OutputFile: names the output file to be saved in the data store
  function OutputFile() {
    this.addInput("data", "file");
    this.addProperty("name", "", "string");
    this.widget = this.addWidget("text", "name", "", "name");
    this.widgets_start_y = LiteGraph.NODE_SLOT_HEIGHT+5;
  }
  OutputFile.title = "OutputFile";
  OutputFile.desc =
    "Defines the name used to save output as a file in the data store";
  OutputFile.prototype.getTitle = function () {
    return this.flags.collapsed ? this.properties.name : this.title;
  };
  OutputFile.prototype.onDrawBackground = function () {
    if (this.inputs && this.inputs[0]) {
      this.inputs[0].label = this.properties["name"] || null;
    }
  };
  LiteGraph.registerNodeType("core/outfile", OutputFile);

  // WfInput: an input channel of the workflow. A workflow with inputs is used as sub workflow.
  // The output accepts any type ("*") until it is connected. Then it gets the type of the
  // connected input, thus further links must have the same type. Type and format of the workflow
  // input are taken from the connected node inputs when the workflow is saved.
  function WfInput() {
    this.addOutput("value", "*");
    this.addProperty("name", "", "string");
    this.widget = this.addWidget("text", "name", "", "name");
    this.widgets_start_y = LiteGraph.NODE_SLOT_HEIGHT + 5;
  }
  WfInput.title = "WfInput";
  WfInput.desc =
    "Defines an input of the workflow. Type and format are taken from the connected node inputs";
  WfInput.prototype.getTitle = function () {
    return this.flags.collapsed ? this.properties.name : this.title;
  };
  WfInput.prototype.onDrawBackground = function () {
    var output = this.outputs[0];
    var name = this.properties["name"];
    var typeText = output.type && output.type !== "*" ? " (" + output.type + ")" : "";
    output.label = name ? name + typeText : null;
  };
  WfInput.prototype.onConnectionsChange = function (kind, slot, connected, linkInfo) {
    if (kind !== LiteGraph.OUTPUT || !this.graph) return;
    var output = this.outputs[0];
    var links = (output.links || [])
      .map(function (id) { return this.graph.links[id]; }, this)
      .filter(function (link) { return link; });
    if (links.length === 0) {
      output.type = "*";
    } else if (output.type === "*" || !output.type) {
      var target = this.graph.getNodeById(links[0].target_id);
      var input = target && target.inputs && target.inputs[links[0].target_slot];
      if (input) output.type = input.type;
    }
    links.forEach(function (link) {
      link.type = output.type;
    });
    this.setDirtyCanvas(true, true);
  };
  LiteGraph.registerNodeType("core/wf_input", WfInput);

  // If: a functional if. Input "condition" (bool) selects which branch is executed. A branch ("then",
  // "else") is a node definition or a workflow, selected in the context menu of the node. The inputs
  // of the branches become inputs "then.<name>" and "else.<name>". Both branches must have outputs of
  // the same types (names may differ): each output of the if node is a pair of a then output and an
  // else output. See _ifSetBranch and the description in litegraph.py
  function IfNode() {
    this.addInput("condition", "bool");
    this.addProperty("then", "", "string");
    this.addProperty("else", "", "string");
    this.addProperty("out_pairs", [], "array");
    this.addProperty("condition", false, "boolean");
    _parmaUpdateConstantWidgets(this);
    _ifDecorate(this);
  }
  IfNode.title = "If";
  IfNode.desc =
    "Executes the then branch or the else branch depending on the condition. Select the branches in the context menu";
  IfNode.prototype.onConnectionsChange = function (kind) {
    if (kind === LiteGraph.INPUT) _parmaUpdateConstantWidgets(this);
  };
  IfNode.prototype.onConfigure = function () {
    _parmaUpdateConstantWidgets(this);
    _ifDecorate(this);
  };
  IfNode.prototype.getExtraMenuOptions = function (canvas) {
    return _ifMenuOptions(this, canvas);
  };
  LiteGraph.registerNodeType("core/if", IfNode);

  // Constants: no input, one output of the given type, a 'value' property
  function registerConstant(type) {
    var def = PARMA_CONSTANT_TYPES[type];
    function Constant() {
      this.addOutput("value", type);
      this.addProperty("value", def.value, def.propType);
      this.widget = this.addWidget(def.widget, "value", def.value, "value", Object.assign({}, def.options));
      this.widgets_start_y = LiteGraph.NODE_SLOT_HEIGHT + 5;
    }
    Constant.title = def.title;
    Constant.desc = "Defines a constant of type " + type;
    Constant.prototype.onExecute = function () {
      this.setOutputData(0, this.properties["value"]);
    };
    Constant.prototype.getTitle = function () {
      return this.flags.collapsed ? String(this.properties.value) : this.title;
    };
    Constant.prototype.onDrawBackground = function () {
      var v = this.properties["value"];
      this.outputs[0].label = v === "" || v === null || v === undefined ? null : String(v);
    };
    LiteGraph.registerNodeType("core/" + type, Constant);
  }
  Object.keys(PARMA_CONSTANT_TYPES).forEach(registerConstant);
})();

// Parma nodes: every unconnected input of a constant type gets a widget to enter its value.
// The value is stored in the property named like the input. Connecting the input hides the
// widget, disconnecting shows it again (the value entered before is kept).
function _parmaCreateConstantInputs() {
  this.widgets_start_y = null;
  (this.inputs || []).forEach(function (input) {
    var def = PARMA_CONSTANT_TYPES[input.type];
    if (def && !(this.properties && input.name in this.properties)) {
      this.addProperty(input.name, def.value, def.propType);
    }
  }, this);
  _parmaUpdateConstantWidgets(this);
}

function _parmaUpdateConstantWidgets(node) {
  var width = node.size ? node.size[0] : 0;
  node.widgets = [];
  (node.inputs || []).forEach(function (input) {
    var def = PARMA_CONSTANT_TYPES[input.type];
    if (!def || input.link != null) return;
    // copy the options: addWidget stores the property name in the options object
    var options = Object.assign({}, def.options);
    var w = node.addWidget(def.widget, input.name, node.properties[input.name], input.name, options);
    w.label = input.name + " (" + input.type + ")";
  });
  var size = node.computeSize();
  node.setSize([Math.max(width, size[0]), size[1]]);
  if (node.graph) node.setDirtyCanvas(true, true);
}

// Registers a dynamic Parma node type built from a node definition object
function register_parma_node(title, hierarchy, description, inputs, outputs) {
  if (typeof LiteGraph === "undefined") return;
  var node_def_object = {
    title: title,
    type: hierarchy,
    desc: description,
    inputs: inputs || [],
    outputs: outputs || [],
    onCreate: _parmaCreateConstantInputs,
    onConnectionsChange: function (kind) {
      if (kind === LiteGraph.INPUT) _parmaUpdateConstantWidgets(this);
    },
    onConfigure: function () {
      _parmaUpdateConstantWidgets(this);
    },
    onMouseEnter: function (e) {
      var tooltip = document.getElementById("lg-tooltip");
      if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "lg-tooltip";
        tooltip.style.cssText =
          "position:fixed;background:#333;color:#fff;padding:4px 8px;" +
          "border-radius:4px;font-size:14px;font-family:sans-serif;" +
          "pointer-events:none;z-index:9999;";
        document.body.appendChild(tooltip);
      }
      tooltip.textContent = this.desc;
      tooltip.style.left = e.clientX + 12 + "px";
      tooltip.style.top = e.clientY + 12 + "px";
      tooltip.style.display = "block";
    },
    onMouseLeave: function () {
      var tooltip = document.getElementById("lg-tooltip");
      if (tooltip) tooltip.style.display = "none";
    },
  };
  LiteGraph.buildNodeClassFromObject(hierarchy, node_def_object);
}

var _lgGraph = null;
var _lgCanvas = null;
var _lgResizeObserver = null;
var litegraph_nodes = [];
// slots of the registered node definitions and workflows: hierarchy -> { inputs, outputs }, each a
// list of [name, type]. Used for the branches of if nodes
var _parmaTypeSlots = {};

function _lgResizeCanvas() {
  var wrap = document.getElementById("lg-canvas-wrap");
  var canvas = document.getElementById("workflow-litegraph");
  if (!wrap || !canvas) return;
  var w = wrap.clientWidth;
  var h = wrap.clientHeight;
  if (w > 0 && h > 0 && (canvas.width !== w || canvas.height !== h)) {
    canvas.width = w;
    canvas.height = h;
    if (_lgCanvas) _lgCanvas.resize(w, h);
  }
}

function _refreshLitegraphNodes() {
  if (typeof LiteGraph === "undefined") return Promise.resolve(false);
  return apiCall("POST", "/nodes/litegraph", {})
    .then(function (result) {
      if (!result.success) {
        showToast(_resultError(result, "Error loading node types"), "error");
        return false;
      }
      // replace the registered node types by the current ones
      litegraph_nodes.forEach(function (hierarchy) {
        LiteGraph.unregisterNodeType(hierarchy);
      });
      litegraph_nodes = [];
      _parmaTypeSlots = {};
      // node definitions ("parma/...") and workflows usable as sub workflows ("wf/...")
      (result.nodes || []).concat(result.workflows || []).forEach(function (node) {
        register_parma_node(
          node.title,
          node.hierarchy,
          node.description,
          node.inputs,
          node.outputs,
        );
        litegraph_nodes.push(node.hierarchy);
        _parmaTypeSlots[node.hierarchy] = { inputs: node.inputs || [], outputs: node.outputs || [] };
      });
      return true;
    })
    .catch(function (e) {
      showToast("Error loading node types: " + e.message, "error");
      return false;
    });
}

// Opens the editor with an empty workflow (menu Workflow -> Edit)
function openWorkflowEdit() {
  if (_apiBusyToast()) return;
  if (!_initWorkflowEditor()) return;
  _wfEditFromList = false;
  _setWorkflowEditorStack([]);
  _lgGraph.clear();
  _setWorkflowEditorTitle(null);
  _markWorkflowEditorSaved(null, null);
  _refreshLitegraphNodes();
}

// Opens the editor with a stored workflow (button "Edit" in the workflow list)
function openWorkflowEditFor(hash, nameVer) {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (_apiBusyToast()) return;
  if (!_initWorkflowEditor()) return;
  _wfEditFromList = true;
  _setWorkflowEditorStack([]);
  _loadWorkflowIntoEditor({ hash: hash }, nameVer);
}

// Loads a stored workflow (referer: { hash } or { name, version }) into the editor.
// Returns a promise of true (loaded) or false (error, shown as toast; the editor is empty)
function _loadWorkflowIntoEditor(referer, nameVer) {
  _lgGraph.clear();
  _setWorkflowEditorTitle(null);
  _markWorkflowEditorSaved(null, null);
  // node types must be registered before the graph can be configured
  return _refreshLitegraphNodes()
    .then(function (ok) {
      if (!ok) return null;
      return apiCall("POST", "/workflow/litegraph", referer);
    })
    .then(function (result) {
      if (!result) return false;
      if (!result.success) {
        showToast(_resultError(result, "Error loading workflow " + nameVer), "error");
        return false;
      }
      _lgGraph.configure(result.graph);
      _setWorkflowEditorTitle(result.name, result.version);
      _markWorkflowEditorSaved(result.hash, result.name + ":" + result.version);
      _lgCanvas.setDirty(true, true);
      return true;
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
      return false;
    });
}

// -- Sub workflows in the editor --------------------------------------------------
// A double click on a sub workflow opens it in the editor. The workflow left is pushed on a stack
// (with its unsaved changes, if any). The button Back pops it and shows it again.
// A sub workflow can't be saved (Save hidden, name read-only): changes are lost on Back and don't
// count as unsaved changes. Only the workflow at the bottom of the stack can have unsaved changes.
// The editor opened from the workflow list (button "Edit") shows Back to the list, too (when no sub
// workflow is shown). Unsaved changes must be confirmed to be discarded.
var _wfEditorStack = [];
var _wfEditFromList = false;

function _setWorkflowEditorStack(stack) {
  _wfEditorStack = stack;
  var isSub = stack.length > 0;
  var backBtn = document.getElementById("workflow-edit-back");
  if (backBtn) {
    var parent = stack[stack.length - 1];
    backBtn.style.display = parent || _wfEditFromList ? "" : "none";
    backBtn.title = parent
      ? "Back to " + (parent.nameVer || "the workflow left")
      : _wfEditFromList
        ? "Back to the workflow list"
        : "";
  }
  var saveBtn = document.getElementById("workflow-edit-save");
  if (saveBtn) saveBtn.style.display = isSub ? "none" : "";
  var nameInput = document.getElementById("workflow-edit-name");
  if (nameInput) nameInput.readOnly = isSub;
}

// true, if a workflow left for a sub workflow has unsaved changes
function _isWorkflowEditorStackDirty() {
  return _wfEditorStack.some(function (state) {
    return state.dirty;
  });
}

function _openSubWorkflow(name, version) {
  if (_apiBusyToast()) return;
  var nameInput = document.getElementById("workflow-edit-name");
  var title = document.getElementById("workflow-edit-title");
  var state = {
    graph: _lgGraph.serialize(),
    name: nameInput ? nameInput.value : "",
    title: title ? title.textContent : "",
    saved: _wfEditorSaved,
    dirty: _isWorkflowEditorDirty(),
    nameVer: _wfEditorSaved.nameVer || (nameInput && nameInput.value.trim()),
  };
  _setWorkflowEditorStack(_wfEditorStack.concat([state]));
  _loadWorkflowIntoEditor({ name: name, version: version }, name + ":" + version).then(
    function (ok) {
      if (!ok) {
        _popWorkflowEditorStack();
        return;
      }
      showToast(
        "Sub workflow " + name + ":" + version +
          " can't be saved here: changes are lost when going back",
        "info",
      );
    },
  );
}

// Shows the workflow left for the sub workflow shown now again
function _popWorkflowEditorStack() {
  var state = _wfEditorStack[_wfEditorStack.length - 1];
  if (!state) return;
  _setWorkflowEditorStack(_wfEditorStack.slice(0, -1));
  _lgGraph.clear();
  _lgGraph.configure(state.graph);
  var nameInput = document.getElementById("workflow-edit-name");
  var title = document.getElementById("workflow-edit-title");
  if (nameInput) nameInput.value = state.name;
  if (title) title.textContent = state.title;
  _wfEditorSaved = state.saved;
  _updateWorkflowEditorButtons();
  _lgCanvas.setDirty(true, true);
}

// Button Back of the editor: from a sub workflow back to the workflow left (changes of the sub
// workflow are discarded), otherwise back to the workflow list (if opened from there)
function backFromSubWorkflow() {
  if (_apiBusyToast()) return;
  if (_wfEditorStack.length > 0) {
    _popWorkflowEditorStack();
    return;
  }
  if (!_wfEditFromList) return;
  if (_isWorkflowEditorDirty() && !window.confirm("The workflow has unsaved changes. Discard them?")) return;
  _wfEditorSaved.snapshot = _workflowEditorSnapshot(); // discarded: no longer unsaved (e.g. on closing the page)
  openWorkflowList();
}

function _setWorkflowEditorTitle(name, version) {
  var title = document.getElementById("workflow-edit-title");
  var nameInput = document.getElementById("workflow-edit-name");
  if (title) {
    title.textContent = name
      ? "Workflow – Edit " + name + ":" + version
      : "Workflow – Edit";
  }
  if (nameInput) nameInput.value = name || "";
}

// -- Dirty state of the workflow editor ------------------------------------------
// The editor is dirty, if its content differs from the state last loaded or saved. Content are the
// workflow name, the nodes (type, position, collapsed state, properties) and the links. Size, zoom and
// panning are not stored in the workflow, thus they don't count. The state is compared periodically
// while the editor is shown: LiteGraph doesn't report all changes (e.g. of widget values).
//   Save is enabled, if the editor is dirty.
//   Run is enabled, if the editor is not dirty and shows a stored workflow without inputs.
var _wfEditorSaved = { snapshot: null, hash: null, nameVer: null };

function _workflowEditorSnapshot() {
  if (!_lgGraph) return "";
  var data = _lgGraph.serialize();
  var nameInput = document.getElementById("workflow-edit-name");
  var nodes = (data.nodes || [])
    .map(function (n) {
      var pos = n.pos || [0, 0];
      return {
        id: n.id,
        type: n.type,
        pos: [Math.round(pos[0]), Math.round(pos[1])],
        collapsed: !!(n.flags && n.flags.collapsed),
        properties: n.properties || {},
      };
    })
    .sort(function (a, b) {
      return a.id - b.id;
    });
  var links = (data.links || [])
    .map(function (l) {
      return Array.isArray(l)
        ? [l[0], l[1], l[2], l[3], l[4]]
        : [l.id, l.origin_id, l.origin_slot, l.target_id, l.target_slot];
    })
    .sort(function (a, b) {
      return a[0] - b[0];
    });
  return JSON.stringify({
    name: nameInput ? nameInput.value.trim() : "",
    nodes: nodes,
    links: links,
  });
}

// Remembers the current content (or "snapshot") as saved state of the stored workflow "hash"
// (null: the content isn't stored, e.g. an empty editor)
function _markWorkflowEditorSaved(hash, nameVer, snapshot) {
  _wfEditorSaved = {
    snapshot: snapshot !== undefined ? snapshot : _workflowEditorSnapshot(),
    hash: hash,
    nameVer: nameVer,
  };
  _updateWorkflowEditorButtons();
}

// A sub workflow (opened from another workflow) can't be saved, thus it is never dirty
function _isWorkflowEditorDirty() {
  if (_wfEditorStack.length > 0) return false;
  return _workflowEditorSnapshot() !== _wfEditorSaved.snapshot;
}

function _updateWorkflowEditorButtons() {
  var saveBtn = document.getElementById("workflow-edit-save");
  var runBtn = document.getElementById("workflow-edit-run");
  if (!saveBtn || !runBtn || !_lgGraph) return;
  var dirty = _isWorkflowEditorDirty();
  saveBtn.disabled = !dirty;
  saveBtn.title = dirty ? "" : "No changes to save";
  if (runBtn.dataset.running) return; // handleWorkflowRun controls the button during the run
  var hasInputs = (_lgGraph.serialize().nodes || []).some(function (n) {
    return n.type === "core/wf_input";
  });
  var reason = dirty
    ? "Save the changes first"
    : !_wfEditorSaved.hash
      ? "The workflow isn't stored yet"
      : hasInputs
        ? "This workflow has inputs. It can only run as sub workflow of another workflow"
        : "";
  runBtn.disabled = !!reason;
  runBtn.title = reason;
}

setInterval(function () {
  if (_isPanelActive("workflow-edit")) _updateWorkflowEditorButtons();
  if (_isPanelActive("node-edit")) _updateNodeFormButtons();
}, 300);

function _isPanelActive(panelId) {
  var panel = document.getElementById("panel-" + panelId);
  return !!panel && panel.classList.contains("active");
}

// Names of the editors shown with unsaved changes. The workflow editor counts as shown, too, if the
// node form was opened from it. Its unsaved changes include those of workflows left for sub workflows.
function _dirtyEditorsShown() {
  var dirty = [];
  if (_isPanelActive("node-edit") && _isNodeFormDirty()) dirty.push("node-edit");
  var workflowShown =
    _isPanelActive("workflow-edit") || (_isPanelActive("node-edit") && _nodeEditFromWorkflow);
  if (workflowShown && _lgGraph && (_isWorkflowEditorDirty() || _isWorkflowEditorStackDirty())) {
    dirty.push("workflow-edit");
  }
  return dirty;
}

// Leaving a dirty editor (by the menu, or by a button that discards its content, marked with
// data-discards-changes) must be confirmed. The listener runs in the capture phase: if the user
// cancels, the click never reaches the menu item or button.
document.addEventListener(
  "click",
  function (e) {
    var target = e.target.closest && e.target.closest(".menu-item, [data-discards-changes]");
    if (!target) return;
    var discards = target.getAttribute("data-discards-changes");
    var dirtyEditors = _dirtyEditorsShown().filter(function (editor) {
      return !discards || discards === editor;
    });
    if (!dirtyEditors.length) return;
    var what =
      dirtyEditors.length > 1
        ? "The node and the workflow have"
        : dirtyEditors[0] === "workflow-edit"
          ? "The workflow has"
          : "The node has";
    if (!window.confirm(what + " unsaved changes. Discard them?")) {
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    // discarded: the content is not shown again (the menu entries reload the editors), thus it
    // must not count as unsaved anymore (e.g. when the page is closed later)
    if (dirtyEditors.indexOf("node-edit") >= 0) _markNodeFormSaved();
    if (dirtyEditors.indexOf("workflow-edit") >= 0) {
      _wfEditorSaved.snapshot = _workflowEditorSnapshot();
      _setWorkflowEditorStack([]);
    }
  },
  true,
);

// Closing or reloading the page with unsaved changes in an editor (shown or not) asks, too
window.addEventListener("beforeunload", function (e) {
  var dirty =
    (_lgGraph && _wfEditorSaved.snapshot !== null && _isWorkflowEditorDirty()) ||
    _isWorkflowEditorStackDirty() ||
    _isNodeFormDirty();
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// Runs the workflow shown in the editor (only enabled, if it is stored and not changed)
function runWorkflowFromEditor() {
  if (_isWorkflowEditorDirty() || !_wfEditorSaved.hash) return;
  handleWorkflowRun(
    _wfEditorSaved.hash,
    _wfEditorSaved.nameVer,
    document.getElementById("workflow-edit-run"),
  );
}

// Sends the graph to the backend. It is converted to the workflow format and stored (new version if the name exists)
function saveWorkflowGraph() {
  if (!_loginToken) {
    showToast("Please log in first", "error");
    return;
  }
  if (!_lgGraph || _wfEditorStack.length > 0) return; // a sub workflow can't be saved
  var nameInput = document.getElementById("workflow-edit-name");
  var name = nameInput ? nameInput.value.trim() : "";
  if (!name) {
    showToast("Please enter a workflow name", "error");
    if (nameInput) nameInput.focus();
    return;
  }
  // the state sent is the saved state: changes made while saving keep the editor dirty
  var sentSnapshot = _workflowEditorSnapshot();
  apiCall("POST", "/workflow/save", { name: name, graph: _lgGraph.serialize() })
    .then(function (result) {
      if (result.success) {
        showToast("Workflow " + name + ":" + result.version + " saved", "success");
        _setWorkflowEditorTitle(name, result.version);
        _markWorkflowEditorSaved(result.hash, name + ":" + result.version, sentSnapshot);
      } else {
        showToast(_resultError(result, "Error saving workflow"), "error");
      }
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
}

// Shows the editor panel and creates graph and canvas once. Returns false if LiteGraph is missing
// -- Canvas context menu ----------------------------------------------------------
// Replaces LiteGraph's "Add Node" (a category tree) by flat lists:
//   Add Core   core node types that are no constants (input file, output file, env var value,
//              workflow input)
//   Add Const  the constants (str, int, float, bool, json)
//   Add Nodes  the node definitions of the backend ("parma/<name>:<version>")
//   Add WF     the workflows of the backend, used as sub workflow ("wf/<name>:<version>")
// Nodes and WFs have two submenu levels: first the names, then the versions of the selected name,
// starting with "latest" (the highest version), followed by all versions, highest first.
// "Add Group" of LiteGraph is not offered.
function _lgCanvasMenuOptions() {
  var options = [
    { content: "Add Core", has_submenu: true, callback: _lgAddMenu(_lgIsCoreType) },
    { content: "Add Const", has_submenu: true, callback: _lgAddMenu(_lgIsConstantType) },
    { content: "Add Nodes", has_submenu: true, callback: _lgAddVersionedMenu("parma/") },
    { content: "Add WF", has_submenu: true, callback: _lgAddVersionedMenu("wf/") },
  ];
  if (Object.keys(this.selected_nodes || {}).length > 1) {
    options.push({ content: "Align", has_submenu: true, callback: LGraphCanvas.onGroupAlign });
  }
  return options;
}

function _lgIsConstantType(type) {
  return type.indexOf("core/") === 0 && type.slice(5) in PARMA_CONSTANT_TYPES;
}

function _lgIsCoreType(type) {
  return type.indexOf("core/") === 0 && !_lgIsConstantType(type);
}

function _lgHasPrefix(prefix) {
  return function (type) {
    return type.indexOf(prefix) === 0;
  };
}

// Returns a menu callback, that shows all registered node types accepted by "filter", sorted by
// title. Selecting an entry adds a node of that type where the context menu was opened.
function _lgAddMenu(filter) {
  return function (value, options, e, prevMenu) {
    var canvas = LGraphCanvas.active_canvas || _lgCanvas;
    var types = Object.keys(LiteGraph.registered_node_types).filter(filter);
    var entries = types
      .map(function (type) {
        var nodeClass = LiteGraph.registered_node_types[type];
        return { value: type, content: nodeClass.title || type };
      })
      .sort(function (a, b) {
        return a.content.localeCompare(b.content, undefined, { numeric: true });
      });
    if (entries.length === 0) {
      entries = [{ content: "(none)", disabled: true }];
    }
    entries.forEach(function (entry) {
      if (!entry.disabled) entry.callback = _lgAddNodeCallback(canvas);
    });
    new LiteGraph.ContextMenu(entries, { event: e, parentMenu: prevMenu }, canvas.getCanvasWindow());
    return false;
  };
}

// Returns a menu entry callback, that adds a node of the type "value" of the selected entry where
// the (first) context menu was opened.
function _lgAddNodeCallback(canvas) {
  return function (v, ev, mouseEvent, contextMenu) {
    var firstEvent = contextMenu.getFirstEvent();
    canvas.graph.beforeChange();
    var node = LiteGraph.createNode(v.value);
    if (node) {
      node.pos = canvas.convertEventToCanvasOffset(firstEvent);
      canvas.graph.add(node);
    }
    canvas.graph.afterChange();
  };
}

// Returns a menu callback for the node types "<prefix><name>:<version>". The submenu shows the
// names (sorted), the submenu of a name its versions: "latest" (the highest version) first, then all
// versions, highest first. Selecting a version adds a node of that type, or, if "onSelect" is given,
// calls onSelect(type) (used for the branches of if nodes).
function _lgAddVersionedMenu(prefix, onSelect) {
  return function (value, options, e, prevMenu) {
    var canvas = LGraphCanvas.active_canvas || _lgCanvas;
    var versionsByName = {};
    Object.keys(LiteGraph.registered_node_types).forEach(function (type) {
      if (type.indexOf(prefix) !== 0) return;
      var nameVersion = type.slice(prefix.length);
      var sep = nameVersion.lastIndexOf(":");
      if (sep < 0) return;
      var name = nameVersion.slice(0, sep);
      (versionsByName[name] = versionsByName[name] || []).push({
        version: nameVersion.slice(sep + 1),
        type: type,
      });
    });
    var names = Object.keys(versionsByName).sort(function (a, b) {
      return a.localeCompare(b, undefined, { numeric: true });
    });
    var nameEntries = names.map(function (name) {
      return {
        content: name,
        has_submenu: true,
        callback: function (v, opts, ev, nameMenu) {
          var versions = versionsByName[name].slice().sort(function (a, b) {
            return b.version.localeCompare(a.version, undefined, { numeric: true });
          });
          var addNode = onSelect
            ? function (v) {
                onSelect(v.value);
              }
            : _lgAddNodeCallback(canvas);
          var versionEntries = [{ content: "latest", value: versions[0].type, callback: addNode }].concat(
            versions.map(function (v) {
              return { content: v.version, value: v.type, callback: addNode };
            }),
          );
          new LiteGraph.ContextMenu(versionEntries, { event: ev, parentMenu: nameMenu }, canvas.getCanvasWindow());
          return false;
        },
      };
    });
    if (nameEntries.length === 0) {
      nameEntries = [{ content: "(none)", disabled: true }];
    }
    new LiteGraph.ContextMenu(nameEntries, { event: e, parentMenu: prevMenu }, canvas.getCanvasWindow());
    return false;
  };
}

// -- If nodes in the editor --------------------------------------------------------
// The context menu of an if node selects the branches ("Then", "Else": a node definition or a
// workflow), swaps them and changes the pairing of the outputs. Slots are rebuilt when a branch
// changes: links of inputs with the same name and of outputs with the same position are kept.
// Each output of the if node is a pair [then output, else output] (property "out_pairs"). Selecting a
// branch whose outputs can't be paired with the outputs of the other branch (same number, same types)
// clears the other branch (after a confirmation).
var IF_BRANCHES = ["then", "else"];
var IF_SLOT_COLORS = { then: ["#7c7", "#3a5a3a"], else: ["#e93", "#6a4a1a"] }; // [connected, unconnected]
var _lgLastPointer = null; // a double click has no event: the menu of an if node is shown at the last pointer position

document.addEventListener(
  "pointerdown",
  function (e) {
    _lgLastPointer = { clientX: e.clientX, clientY: e.clientY };
  },
  true,
);

function _ifShortName(type) {
  return type ? type.substring(type.indexOf("/") + 1) : "?";
}

// type of the input or output (kind "inputs" | "outputs") "name" of the node definition or workflow "hierarchy"
function _slotType(hierarchy, kind, name) {
  var slots = (_parmaTypeSlots[hierarchy] || {})[kind] || [];
  for (var i = 0; i < slots.length; i++) {
    if (slots[i][0] === name) return slots[i][1];
  }
  return null;
}

// title, slot colors (then green, else orange) and output labels ("then name | else name" if they differ)
function _ifDecorate(node) {
  var p = node.properties || {};
  node.title = p.then || p.else ? "If: " + _ifShortName(p.then) + " | " + _ifShortName(p.else) : "If";
  (node.inputs || []).forEach(function (input) {
    var colors = IF_SLOT_COLORS[input.name.split(".")[0]];
    if (colors && input.name.indexOf(".") > 0) {
      input.color_on = colors[0];
      input.color_off = colors[1];
    }
  });
  var pairs = p.out_pairs || [];
  (node.outputs || []).forEach(function (output, i) {
    var pair = pairs[i] || [];
    output.label = pair[0] && pair[1] && pair[0] !== pair[1] ? pair[0] + " | " + pair[1] : null;
  });
  var size = node.computeSize();
  node.setSize([Math.max(node.size ? node.size[0] : 0, size[0]), size[1]]);
  if (node.graph) node.setDirtyCanvas(true, true);
}

function _ifMenuOptions(node, canvas) {
  var p = node.properties;
  var options = IF_BRANCHES.map(function (branch) {
    return {
      content: (branch === "then" ? "Then: " : "Else: ") + (p[branch] ? _ifShortName(p[branch]) : "(select)"),
      has_submenu: true,
      callback: function (v, opts, e, prevMenu) {
        var select = function (type) {
          _ifSetBranch(node, branch, type);
        };
        new LiteGraph.ContextMenu(
          [
            { content: "Node", has_submenu: true, callback: _lgAddVersionedMenu("parma/", select) },
            { content: "Workflow", has_submenu: true, callback: _lgAddVersionedMenu("wf/", select) },
          ],
          { event: e, parentMenu: prevMenu },
          canvas.getCanvasWindow(),
        );
        return false;
      },
    };
  });
  if (p.then && p.else) {
    options.push({ content: "Swap Then/Else", callback: function () { _ifSwapBranches(node); } });
    if ((p.out_pairs || []).length > 1) {
      options.push({ content: "Pair Outputs", has_submenu: true, callback: _ifPairMenu(node, canvas) });
    }
  }
  IF_BRANCHES.forEach(function (branch) {
    if (p[branch]) {
      options.push({
        content: "Open " + branch + ": " + _ifShortName(p[branch]),
        callback: function () { _lgOpenDefinition(p[branch]); },
      });
    }
  });
  return options;
}

function _ifSetBranch(node, branch, type) {
  var slots = _parmaTypeSlots[type];
  if (!slots) {
    showToast("Unknown node type " + type, "error");
    return;
  }
  var p = node.properties;
  var other = branch === "then" ? "else" : "then";
  var k = branch === "then" ? 0 : 1; // index of this branch in a pair
  var pairs = null;
  if (p[other]) {
    pairs = _ifPairOutputs(p.out_pairs || [], k, slots.outputs, p[other]);
    if (!pairs) {
      var question =
        "The outputs of " + _ifShortName(type) + " can't be paired with the outputs of the " + other +
        " branch " + _ifShortName(p[other]) + " (same number and types needed).\nClear the " + other + " branch?";
      if (!window.confirm(question)) return;
    }
  }
  if (!pairs) {
    pairs = slots.outputs.map(function (output) {
      return k === 0 ? [output[0], null] : [null, output[0]];
    });
  }
  if (node.graph) node.graph.beforeChange();
  if (pairs.some(function (pair) { return pair[1 - k] === null; })) p[other] = "";
  p[branch] = type;
  p.out_pairs = pairs;
  _ifRebuildSlots(node, null);
  if (node.graph) node.graph.afterChange();
}

// The pairs after replacing the outputs of branch k (0: then, 1: else) by "newOutputs" ([name, type]).
// The outputs of the other branch keep their order. An output of the new branch is paired with the same
// name (as the replaced output or the output of the other branch) and type, otherwise with the first
// unused output of the same type. Returns null, if that's impossible.
function _ifPairOutputs(oldPairs, k, newOutputs, otherType) {
  var o = 1 - k;
  if (oldPairs.length !== newOutputs.length) return null;
  var unused = newOutputs.slice();
  var result = oldPairs.map(function () { return null; });
  var take = function (i, accept) {
    var type = _slotType(otherType, "outputs", oldPairs[i][o]);
    var index = unused.findIndex(function (output) { return output[1] === type && accept(output[0]); });
    if (index < 0) return;
    var pair = [null, null];
    pair[o] = oldPairs[i][o];
    pair[k] = unused[index][0];
    result[i] = pair;
    unused.splice(index, 1);
  };
  oldPairs.forEach(function (pair, i) {
    take(i, function (name) { return name === pair[k] || name === pair[o]; });
  });
  oldPairs.forEach(function (pair, i) {
    if (!result[i]) take(i, function () { return true; });
  });
  return result.every(function (pair) { return pair; }) ? result : null;
}

// Rebuilds the slots of an if node from its properties. Links are restored: inputs by name (after
// "renameInput", if given), outputs by position. LiteGraph rejects links of incompatible types.
function _ifRebuildSlots(node, renameInput) {
  var graph = node.graph;
  var p = node.properties;
  var inLinks = [];
  var outLinks = [];
  if (graph) {
    (node.inputs || []).forEach(function (input) {
      var link = input.link != null ? graph.links[input.link] : null;
      if (link) {
        inLinks.push({
          name: renameInput ? renameInput(input.name) : input.name,
          origin_id: link.origin_id,
          origin_slot: link.origin_slot,
        });
      }
    });
    outLinks = (node.outputs || []).map(function (output) {
      return (output.links || [])
        .map(function (id) { return graph.links[id]; })
        .filter(function (link) { return link; })
        .map(function (link) { return { target_id: link.target_id, target_slot: link.target_slot }; });
    });
  }
  for (var i = (node.inputs || []).length - 1; i >= 0; i--) node.removeInput(i);
  for (var j = (node.outputs || []).length - 1; j >= 0; j--) node.removeOutput(j);
  node.addInput("condition", "bool");
  IF_BRANCHES.forEach(function (branch) {
    ((_parmaTypeSlots[p[branch]] || {}).inputs || []).forEach(function (input) {
      node.addInput(branch + "." + input[0], input[1]);
    });
  });
  (p.out_pairs || []).forEach(function (pair) {
    var type = pair[0] ? _slotType(p.then, "outputs", pair[0]) : _slotType(p.else, "outputs", pair[1]);
    node.addOutput(pair[0] || pair[1], type);
  });
  // values of unconnected constant inputs: defaults for new inputs, values of removed inputs are dropped
  var inputNames = {};
  node.inputs.forEach(function (input) {
    inputNames[input.name] = true;
    var def = PARMA_CONSTANT_TYPES[input.type];
    if (def && !(input.name in p)) node.addProperty(input.name, def.value, def.propType);
  });
  Object.keys(p).forEach(function (key) {
    if (key.indexOf(".") > 0 && !inputNames[key]) delete p[key];
  });
  if (graph) {
    inLinks.forEach(function (l) {
      var slot = node.findInputSlot(l.name);
      var origin = graph.getNodeById(l.origin_id);
      if (slot >= 0 && origin) origin.connect(l.origin_slot, node, slot);
    });
    outLinks.forEach(function (targets, j) {
      if (j >= node.outputs.length) return;
      targets.forEach(function (t) {
        var target = graph.getNodeById(t.target_id);
        if (target) node.connect(j, target, t.target_slot);
      });
    });
  }
  _parmaUpdateConstantWidgets(node);
  _ifDecorate(node);
}

// Swaps then and else: branches, inputs (with their links and widget values) and the output pairs
function _ifSwapBranches(node) {
  var p = node.properties;
  var swapName = function (name) {
    if (name.indexOf("then.") === 0) return "else." + name.slice(5);
    if (name.indexOf("else.") === 0) return "then." + name.slice(5);
    return name;
  };
  if (node.graph) node.graph.beforeChange();
  var then = p.then;
  p.then = p.else;
  p.else = then;
  p.out_pairs = (p.out_pairs || []).map(function (pair) { return [pair[1], pair[0]]; });
  var values = {};
  Object.keys(p).forEach(function (key) {
    if (swapName(key) !== key) {
      values[swapName(key)] = p[key];
      delete p[key];
    }
  });
  Object.assign(p, values);
  _ifRebuildSlots(node, swapName);
  if (node.graph) node.graph.afterChange();
}

// Submenu "Pair Outputs": select a pair, then the else output it should get. The else outputs of
// the two pairs are exchanged (only offered, if the types fit).
function _ifPairMenu(node, canvas) {
  return function (v, opts, e, prevMenu) {
    var p = node.properties;
    var pairs = p.out_pairs || [];
    var thenType = function (pair) { return _slotType(p.then, "outputs", pair[0]); };
    var elseType = function (pair) { return _slotType(p.else, "outputs", pair[1]); };
    var entries = pairs.map(function (pair, i) {
      return {
        content: pair[0] + "  ⇄  " + pair[1],
        has_submenu: true,
        callback: function (v2, opts2, e2, pairMenu) {
          var choices = [];
          pairs.forEach(function (other, j) {
            if (j === i || elseType(other) !== thenType(pair) || elseType(pair) !== thenType(other)) return;
            choices.push({
              content: "else: " + other[1],
              callback: function () {
                if (node.graph) node.graph.beforeChange();
                var elseName = pair[1];
                pair[1] = other[1];
                other[1] = elseName;
                _ifDecorate(node);
                if (node.graph) node.graph.afterChange();
              },
            });
          });
          if (!choices.length) choices = [{ content: "(no other else output of this type)", disabled: true }];
          new LiteGraph.ContextMenu(choices, { event: e2, parentMenu: pairMenu }, canvas.getCanvasWindow());
          return false;
        },
      };
    });
    new LiteGraph.ContextMenu(entries, { event: e, parentMenu: prevMenu }, canvas.getCanvasWindow());
    return false;
  };
}

// Double click on an if node: a menu to open one of its branches
function _ifShowOpenMenu(node) {
  var p = node.properties;
  var entries = IF_BRANCHES.filter(function (branch) { return p[branch]; }).map(function (branch) {
    return {
      content: "Open " + branch + ": " + _ifShortName(p[branch]),
      callback: function () { _lgOpenDefinition(p[branch]); },
    };
  });
  if (!entries.length) {
    showToast("Select the branches in the context menu of the if node", "info");
    return;
  }
  var pos = _lgLastPointer || { clientX: 100, clientY: 100 };
  new LiteGraph.ContextMenu(entries, { left: pos.clientX - 10, top: pos.clientY - 10 }, _lgCanvas.getCanvasWindow());
}

// Double click on a node in the editor: a node definition ("parma/<name>:<version>") is opened in the
// node form, a sub workflow ("wf/<name>:<version>") in the workflow editor. Back returns to the
// workflow left (its graph is kept, with unsaved changes). An if node shows a menu to open one of its
// branches. Other nodes (core, constants) get the default LiteGraph node panel.
function _lgShowNodeDefinition(lgNode) {
  var type = lgNode.type || "";
  if (type === "core/if") {
    _ifShowOpenMenu(lgNode);
    return;
  }
  if (!_lgOpenDefinition(type)) this.showShowNodePanel(lgNode);
}

// Opens the node definition or workflow of the litegraph type "parma/..." or "wf/...". Returns false
// for other types
function _lgOpenDefinition(type) {
  var kind = type.indexOf("parma/") === 0 ? "node" : type.indexOf("wf/") === 0 ? "workflow" : null;
  if (!kind) return false;
  var nameVer = type.substring(type.indexOf("/") + 1);
  var sep = nameVer.lastIndexOf(":");
  if (sep < 0) {
    showToast("No version in node type " + type, "error");
    return true;
  }
  var name = nameVer.substring(0, sep);
  var version = nameVer.substring(sep + 1);
  if (kind === "workflow") {
    _openSubWorkflow(name, version);
    return true;
  }
  _fetchEntry("node", { name: name, version: version }, false)
    .then(function (result) {
      openNodeEdit(result.entry, true);
    })
    .catch(function (e) {
      showToast("Error: " + e.message, "error");
    });
  return true;
}

function _initWorkflowEditor() {
  showPanel("workflow-edit");
  if (typeof LiteGraph === "undefined") {
    showToast("LiteGraph not loaded", "error");
    return false;
  }
  if (!_lgGraph) {
    _lgGraph = new LGraph();
    _lgCanvas = new LGraphCanvas("#workflow-litegraph", _lgGraph);
    _lgCanvas.getMenuOptions = _lgCanvasMenuOptions;
    _lgCanvas.onShowNodePanel = _lgShowNodeDefinition;
    _lgGraph.start();
    // Apply stored canvas theme now that the canvas exists
    var storedCanvasTheme = null;
    try {
      storedCanvasTheme = localStorage.getItem("parma-canvas-theme");
    } catch (_) {}
    applyCanvasTheme(storedCanvasTheme || "dark", null);
    if (typeof ResizeObserver !== "undefined") {
      var wrap = document.getElementById("lg-canvas-wrap");
      if (wrap) {
        _lgResizeObserver = new ResizeObserver(_lgResizeCanvas);
        _lgResizeObserver.observe(wrap);
      }
    }
  }
  requestAnimationFrame(_lgResizeCanvas);
  return true;
}
