#!/bin/bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )"

# ask a question. If the user answers 'y', everything is fine. Otherwise exit 12
function question {
	echo -n "$1 ('y' if ok) "
	local ANSWER
	read ANSWER
	case "${ANSWER}" in
        y) : ;;
        *) exit 12 ;;
	esac
}

# return the name of the branch we are in. Get it with: local B = $(getBranchName)
function getBranchName {
	local BRANCH="$(git rev-parse --abbrev-ref HEAD)"
	echo "${BRANCH}"
	return 0
}
	
# check whether the branch checked out is clean. If not exit 12
function checkBranchClean {
	if [ -z "$(git status --porcelain)" ];
	then
		:
	else
		echo 'please commit your changes. Exit 12'
		exit 12
	fi
}

# get the name of the underlying os and store it in HOST_OS
function get_os {
    OS="${OSTYPE//[0-9.-]*/}"
    case "$OS" in
        linux)  echo linux ;;
        darwin) echo macos ;;
        msys)   echo windows ;;
        *)      echo UNKNOWN ;;
    esac
}

HOST_OS="$(get_os)"

function get_toml_val() {
  python - "$1" "$property_file" <<'PY'
import sys, pathlib, json
key, file = sys.argv[1], sys.argv[2]
p = pathlib.Path(file)
try:
    import tomllib as tl
    data = tl.loads(p.read_text())
except Exception:
    import toml as tl
    data = tl.load(p)
cur = data
for part in key.split('.'):
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        print('', end='')
        sys.exit(0)
if isinstance(cur, (dict, list)):
    print(json.dumps(cur))
else:
    print(cur)
PY
}

# make absolute path. Should work on both linux and windows with git bash. Path must exist
function make_absolute_path {
    local path="$1"
    if [[ ! -e "$path" ]]
    then
        echo "path '$path' not found (did you forget an --init?) - exit 12" >&2
        echo ''
        return
    fi
    # Check if already absolute (Unix or Windows style)
    if [[ "$path" = /* ]] || [[ "$path" =~ ^[a-zA-Z]: ]]; then
        # For Windows paths in Git Bash, convert to proper format
        if [ "$HOST_OS" == 'windows' ]
        then
            echo "$(cygpath -m "$path")"
        else
            echo "$path"
        fi
    else
        # Make relative path absolute
        if [ "$HOST_OS" == 'windows' ]
        then
            echo "$(cygpath -m "$(pwd)/$path")"
        else
            echo "$(pwd)/$path"
        fi
    fi
}

# make a docker image of one of the examples stored in directory 'test/container'. Structure:
# test/container
#  domain (e.g. sklearn)
#    name (e.g. train)
function make_image {
    domain="$1"
    name="$2"
    version="$3"

    tag="${domain}_${name}:${version}"

    echo "building docker image $tag"

    if [[ -z "$domain" ]]; then
        echo 'Error: domain name missing. Exit 12'
        exit 12
    fi
    if [[ -z "$name" ]]; then
        echo 'Error: docker image name missing. Exit 12'
        exit 12
    fi
    if [[ -z "$version" ]]; then
        echo 'Error: version missing. Exit 12'
        exit 12
    fi

    cd $BASE_DIR/test/container/$domain/$name
    docker build . -t $tag
}

# check the Python implementation for vulnerabilities and licences of used packages
function run_assess {
    uv sync
    uv lock
    uv run pip-audit -f json | python -m json.tool >audit.json
    uv run pip-licenses --from=mixed --format=json | python -m json.tool >licenses.json
    uv run pip-licenses --from=mixed --format=markdown --output-file=licenses.md
}

# get a path property from the toml configuration file and make it an absolute path as needed the host operating system 
function get_toml_val_and_make_mount_path {
    local path="$1"
    path=$(get_toml_val "$path")
    if [[ "$path" == '' ]]
    then
        echo ''
        return
    else
        echo "$(make_absolute_path "$path")"
    fi
}

# used by the --init command to get a value of a store key (a file or directory) and create and initilize directories
function get_toml_val_and_create {
    local key="$1"
    local test_op="$2"
    local init_entity_store="$3"
    local path=$(get_toml_val "$key")
    if [[ "$path" == '' ]]
    then
        echo "toml key '$path' not found - exit 12" >&2
        return 1
    fi
    case "$test_op" in
        -d) if [[ -d "$path" ]]
            then
                echo "directory '$path' exists - exit 12" >&2
                return 1
            fi
            mkdir -p "$path"
            if [[ ! -z "$init_entity_store" ]]
            then
                cp -r "$BASE_DIR"/initdata/* "$path"
            fi
            return 0 ;;
        -f) if [[ -f "$path" ]]
            then
                echo "file '$path' exists - exit 12" >&2
                return 1
            fi
            mkdir -p $(dirname "$path")
            touch "$path"
            return 0 ;;
        *)  echo "invalid parameter '$test_op' - exit 12" >&2
            return 1 ;;
    esac
}

if [[ "$1" == '-q' ]];
then
    shift
else
    echo "run '$0 --help' to see available commands of this bash script"
fi

while [[ $# -gt 0 ]]; do
    cmd="$1"; shift

    case "$cmd" in
    ''|-h|--help)   cat admin-help.txt ;;

    --init)         case "$1" in
                        --*|'') property_file='./parma_light.toml' ;;
                        -c)     property_file="$2"; shift; shift ;;
                        *)      echo "invalid parameter $1 for --init - exit 12" >&2
                                exit 12 ;;
                    esac
        
                    if get_toml_val_and_create 'store.entity_store' '-d' 'init'; then :; else exit 12; fi
                    if get_toml_val_and_create 'store.data_dir' '-d'; then :; else  exit 12; fi
                    if get_toml_val_and_create 'store.temp_dir' '-d'; then :; else  exit 12; fi
                    if get_toml_val_and_create 'store.log_file' '-f'; then :; else  exit 12; fi ;;

    --backend)      case "$1" in
                        --*|'') property_file='./parma_light.toml' ;;
                        -c)     property_file="$2"; shift; shift ;;
                        *)      echo "invalid parameter $1 for --backend - exit 12" >&2
                                exit 12 ;;
                    esac
                    export HOST_OPERATING_SYSTEM="$HOST_OS"
                    python src/parma/backend.py -c $property_file
                    exit 0 ;;

    --frontend)     case "$1" in
                        --*|'') property_file='./parma_light.toml' ;;
                        -c)     property_file="$2"; shift; shift ;;
                        *)      echo "invalid parameter $1 for --frontend - exit 12" >&2
                                exit 12 ;;
                    esac
                    python src/parma/frontend_cli.py -c $property_file
                    exit 0 ;;

    --image)        domain="$1"; shift
                    name="$1"; shift
                    version="$1"; shift
                    make_image "$domain" "$name" "$version" ;;

    --images)       domain="$1"; shift
                    cd "$BASE_DIR"/test/container/"$domain"
                    for dir in */; do
                        dir_name="${dir%/}"
                        "$BASE_DIR"/admin.sh -q --image "$domain" "$dir_name" '1'
                    done ;;

    # run parma-light in a container
    # 1. build the image
    # 2. run the image
    --dood-build)   docker build --no-cache -f docker/Dockerfile -t parma_light . ;;

    --backend-dood) docker_image='parma_light'
                    debugpy=''
                    property_file='./parma_light.toml'
                    while [[ 1 ]]; do
                    case "$1" in
                        --*|'') break ;;
                        -di)    docker_image="$2"; shift; shift ;;
                        -c)     property_file="$2"; shift;shift ;;
                        -debugpy) debugpy=' -p 5678:5678'; shift ;;
                        *)      echo "invalid parameter $1 for --dood-run - exit 12" >&2
                                exit 12 ;;
                    esac
                    done
                    export property_file="$(make_absolute_path $property_file)"

                    entity_store="$(get_toml_val_and_make_mount_path 'store.entity_store')"; if [[ "$entity_store" == '' ]]; then exit 12; fi
                    data_dir="$(get_toml_val_and_make_mount_path 'store.data_dir')"; if [[ "$data_dir" == '' ]]; then exit 12; fi
                    temp_dir="$(get_toml_val_and_make_mount_path 'store.temp_dir')"; if [[ "$temp_dir" == '' ]]; then exit 12; fi
                    log_file="$(get_toml_val_and_make_mount_path 'store.log_file')"; if [[ "$log_file" == '' ]]; then exit 12; fi
                    base_dir="$(get_toml_val_and_make_mount_path 'store.base_dir')"; if [[ "$base_dir" == '' ]]; then exit 12; fi

                    cmd='docker run --name parma_light --rm -it -p 8080:8080'
                    cmd+="$debugpy"
                    if [ "$HOST_OS" == 'linux' ]
                    then
                        cmd+=' -v /var/run/docker.sock:/var/run/docker.sock'
                        cmd+=' -e HOST_OPERATING_SYSTEM=linux'
                    fi
                    if [ "$HOST_OS" == 'windows' ]
                    then
                        cmd+=' -v //var/run/docker.sock:/var/run/docker.sock'
                        cmd+=' -e HOST_OPERATING_SYSTEM=windows'
                    fi
                    cmd+=" -v $property_file:/app/parma_light.toml"
                    cmd+=" -v $entity_store:/entity_store"
                    cmd+=" -v $data_dir:/data_dir -e PARMA_LIGHT_DATA_DIR_HOST=\"$data_dir\""
                    cmd+=" -v $temp_dir:/temp_dir -e PARMA_LIGHT_TEMP_DIR_HOST=\"$temp_dir\""
                    cmd+=" -v $log_file:/app/parma_light.log"
                    cmd+=" -v $base_dir:/base_dir"
                    cmd+=" \"$docker_image\""
                    if [[ "$debugpy" != '' ]]
                    then
                        cmd+=" --debugpy"
                    fi
                    echo "executing: $cmd"
                    eval "$cmd"
                    exit 0 ;;
    
    --assess)       run_assess ;;

    --publish-new-version) checkBranchClean
                    B=$(getBranchName)
                    case "$B" in
                    master) : ;;
                        *)  question "do you really want to push a tag to github from branch '$B'?" ;;
                    esac
                    version="$1"
                    case "$version" in
                        v*) : ;;
                        *)  echo 'a new version name must be given and start with 'v' - exit 12'
                            exit 12 ;;
                    esac
                    shift
                    git tag "$version"
                    git push origin "$version"
                    echo "created and pushed tag '$version'. A github action will create the image and push to docker hub" ;; 

    *)              echo "invalid command: $cmd - exit 12" >&2
                    exit 12 ;;
    esac
done
