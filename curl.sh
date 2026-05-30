#!/bin/bash
# Calls the upload routes of the Parma Light backend from the command line, as the frontend does.
# Every upload sends the content of a file (one or more definitions, JSON or blocks like 'node { ... };'),
# except --data-file, that sends a plain file without metadata (the backend generates the data definition).
#
# The file content is never put on the command line: the JSON request body is written to a temporary
# file and sent with "curl --data-binary @file", a plain file is sent as multipart form ("curl -F file=@...").
# Thus the size of the file can't break the curl command.

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )"

function usage {
    cat <<EOF
usage: $(basename "$0") [options] <command> <file>

commands (exactly one):
  --user <file>       add all users defined in <file>          (route /user/upload, admin only)
  --data <file>       add all data defined in <file>           (route /data/upload)
  --data-file <file>  add the plain <file> as data             (route /data/upload-file)
                      name: file name with '.' replaced by '_', e.g. my.data.csv -> my_data_csv.
                      A name starting with a digit gets a leading '_', e.g. 1.csv -> _1_csv.
                      type "file", storage "platform", hash "true", format "any", user_path: file name
  --node <file>       add all nodes defined in <file>          (route /node/upload)
  --workflow <file>   add all workflows (and refines) in <file> (route /workflow/upload)
  --run <file>        execute all runs defined in <file>       (route /run/upload)
                      returns when the last run has finished, stops at the first failing run

options:
  --host <url>        backend url, default: \$PARMA_HOST or http://localhost:8080
  --login <name>      user name for login, default: \$PARMA_USER
  --password <pw>     password for login, default: \$PARMA_PASSWORD (asked for, if not set)
  --help              this help

The command logs in, uploads the file and logs out. Exit code 0 on success, 12 otherwise.
example: $(basename "$0") --login admin --node test/test_cmds/sklearn/node.txt
EOF
}

host="http://localhost:8080"
login_name=""
login_password=""
route=""
file=""

function set_command {
    if [[ -n "$route" ]]; then
        echo "Error: only one command allowed. Exit 12"
        exit 12
    fi
    if [[ -z "$2" ]]; then
        echo "Error: file missing for command $1. Exit 12"
        exit 12
    fi
    route="$1"
    file="$2"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)       set_command "/user/upload" "$2"; shift 2 ;;
        --data)       set_command "/data/upload" "$2"; shift 2 ;;
        --data-file)  set_command "/data/upload-file" "$2"; shift 2 ;;
        --node)       set_command "/node/upload" "$2"; shift 2 ;;
        --workflow)   set_command "/workflow/upload" "$2"; shift 2 ;;
        --run)        set_command "/run/upload" "$2"; shift 2 ;;
        --host)       host="$2"; shift 2 ;;
        --login)      login_name="$2"; shift 2 ;;
        --password)   login_password="$2"; shift 2 ;;
        --help)       usage; exit 0 ;;
        *)            echo "Error: unknown parameter '$1'. Exit 12"; usage; exit 12 ;;
    esac
done

if [[ -z "$route" ]]; then
    echo "Error: a command (--user, --data, --data-file, --node, --workflow or --run) is required. Exit 12"
    usage
    exit 12
fi
if [[ ! -f "$file" ]]; then
    echo "Error: file '$file' not found. Exit 12"
    exit 12
fi
if [[ -z "$login_name" ]]; then
    echo "Error: login name missing (use --login). Exit 12"
    exit 12
fi
if [[ -z "$login_password" ]]; then
    echo "Error: password missing (use --password). Exit 12"
    exit 12
fi

# -- JSON helper: jq if available, otherwise Python ----------------------------
python_cmd=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
        python_cmd="$candidate"
        break
    fi
done
if ! command -v jq >/dev/null 2>&1 && [[ -z "$python_cmd" ]]; then
    echo "Error: neither jq nor python found. One of them is needed to build JSON. Exit 12"
    exit 12
fi

# writes {"content": "<content of file $1>"} to file $2
function make_content_body {
    if command -v jq >/dev/null 2>&1; then
        jq -Rs '{content: .}' "$1" >"$2"
    else
        "$python_cmd" -c 'import json,sys; json.dump({"content": open(sys.argv[1], encoding="utf-8").read()}, open(sys.argv[2], "w", encoding="utf-8"))' "$1" "$2"
    fi
}

# writes {"name": "$1", "password": "$2"} to file $3. Values are passed by environment, not as arguments
function make_login_body {
    if command -v jq >/dev/null 2>&1; then
        PARMA_N="$1" PARMA_P="$2" jq -n '{name: env.PARMA_N, password: env.PARMA_P}' >"$3"
    else
        PARMA_N="$1" PARMA_P="$2" "$python_cmd" -c 'import json,os,sys; json.dump({"name": os.environ["PARMA_N"], "password": os.environ["PARMA_P"]}, open(sys.argv[1], "w", encoding="utf-8"))' "$3"
    fi
}

# prints the value of key $2 of the JSON in file $1 ("true"/"false" for booleans)
function json_value {
    if command -v jq >/dev/null 2>&1; then
        jq -r --arg k "$2" '.[$k] // empty' "$1"
    else
        "$python_cmd" -c 'import json,sys; v=json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]); print("" if v is None else (str(v).lower() if isinstance(v, bool) else v))' "$1" "$2"
    fi
}

# pretty prints the JSON in file $1
function json_print {
    if command -v jq >/dev/null 2>&1; then
        jq . "$1"
    else
        "$python_cmd" -m json.tool "$1"
    fi
}

# -- the requests ---------------------------------------------------------------
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

# POST the JSON in file $2 to route $1, response to file $3. Optional token in $4
function post {
    local headers=(-H "Content-Type: application/json")
    if [[ -n "$4" ]]; then
        headers+=(-H "X-Auth-Token: $4")
    fi
    if ! curl --silent --show-error --fail-with-body -X POST "${headers[@]}" \
              --data-binary "@$2" -o "$3" "$host$1"; then
        echo "Error: request to $host$1 failed. Exit 12"
        [[ -s "$3" ]] && cat "$3"
        exit 12
    fi
}

# POST the file $2 as multipart form part "file" to route $1, response to file $3, token in $4.
# curl reads the file itself (streamed), quotes in the file name are escaped for -F
function post_file {
    local quoted_file="$2"
    quoted_file="${quoted_file//\\/\\\\}"   # \ -> \\
    quoted_file="${quoted_file//\"/\\\"}"   # " -> \"
    if ! curl --silent --show-error --fail-with-body -X POST -H "X-Auth-Token: $4" \
              -F "file=@\"$quoted_file\"" -o "$3" "$host$1"; then
        echo "Error: request to $host$1 failed. Exit 12"
        [[ -s "$3" ]] && cat "$3"
        exit 12
    fi
}

make_login_body "$login_name" "$login_password" "$tmp_dir/login.json"
post "/user/login" "$tmp_dir/login.json" "$tmp_dir/login_response.json"
rm -f "$tmp_dir/login.json"
token="$(json_value "$tmp_dir/login_response.json" token)"
if [[ -z "$token" ]]; then
    echo "Error: login as '$login_name' failed. Exit 12"
    json_print "$tmp_dir/login_response.json"
    exit 12
fi

if [[ "$route" == "/data/upload-file" ]]; then
    post_file "$route" "$file" "$tmp_dir/response.json" "$token"
else
    make_content_body "$file" "$tmp_dir/body.json"
    post "$route" "$tmp_dir/body.json" "$tmp_dir/response.json" "$token"
fi
json_print "$tmp_dir/response.json"
success="$(json_value "$tmp_dir/response.json" success)"

echo '{}' >"$tmp_dir/empty.json"
post "/user/logout" "$tmp_dir/empty.json" "$tmp_dir/logout_response.json" "$token"

if [[ "$success" != "true" ]]; then
    echo "Error: upload of '$file' to $route failed. Exit 12"
    exit 12
fi
exit 0
