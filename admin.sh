#!/bin/bash

function init {
    PARMA_DIR="$1"
    if [[ $PARMA_DIR == '' ]]
    then
        PARMA_DIR='datastore_parma'
        if [[ -d $PARMA_DIR/entity_store && -d $PARMA_DIR/data_dir && -d $PARMA_DIR/temp_dir ]]
        then
            echo "datastore_parma seems to be a test directory and will be emptied"
            rm -rf $PARMA_DIR
        fi
    fi
    
    if [[ -d $PARMA_DIR ]]
    then
        echo "parma datastore '$PARMA_DIR' exists. Init is ignored"
        exit 12
    else
        mkdir $PARMA_DIR
    fi
    cd $PARMA_DIR
    # git init
    mkdir ./entity_store ./data_dir ./temp_dir
    cp -r $BASE_DIR/initdata/* ./entity_store
    echo "parma initialized in directory $PARMA_DIR."
    cd $BASE_DIR
}

function make_image {
    domain=$1
    name=$2
    version=$3

    tag="${domain}_${name}:${version}"

    echo "building docker image $tag"

    if [[ -z "$domain" ]]; then
        echo "Error: domain name missing. Exit 12"
        exit 12
    fi
    if [[ -z "$name" ]]; then
        echo "Error: docker image name missing. Exit 12"
        exit 12
    fi
    if [[ -z "$version" ]]; then
        echo "Error: version missing. Exit 12"
        exit 12
    fi

    cd $BASE_DIR/test/container/$domain/$name
    docker build . -t $tag
}

function run_assess {
    uv sync
    uv lock
    uv run pip-audit -f json | python -m json.tool >audit.json
    uv run pip-licenses --from=mixed --format=json | python -m json.tool >licenses.json
    uv run pip-licenses --from=mixed --format=markdown --output-file=licenses.md
}

function getOS {
    OS=${OSTYPE//[0-9.-]*/}
    case "$OS" in
      linux)  echo "linux" ;;
      darwin) echo "macos" ;;
      msys)   echo "win" ;;
      *)      echo "UNKNOWN" ;;
    esac
}

function isWin {
    [ $(getOS) == 'win' ]
}

function isLinux {
    [ $(getOS) == 'linux' ]
}

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" == '-q' ]];
then
    shift
else
    echo "run '$0 help' to see available commands of this bash script"
fi

while [[ $# -gt 0 ]]; do
    cmd="$1"; shift

    case "$cmd" in
    ''|'-h'|'--help') cat admin-help.txt ;;

    --backend)        python src/parma/backend.py ;;

    --frontend)       python src/parma/frontend_cli.py ;;

    --init)           dir="$1"
                      case "$dir" in
                      --*) init '' ;;
                      '')  init '' ;;
                      *)   shift
                           init "$dir" ;;
                      esac ;;
    --image)          domain=$1; shift
                      name="$1"; shift
                      version="$1"; shift
                      make_image $domain $name $version ;;

    --images)         domain=$1; shift
                      cd $BASE_DIR/test/container/$domain
                      for dir in */; do
                          dir_name="${dir%/}"
                          $BASE_DIR/admin.sh -q --image "$domain" "$dir_name" "1"
                      done ;;

    # for demonstration, not for real use
    --dind-build)     docker build --no-cache -f docker/Dockerfile -t parma_light . ;;
    --dind-run)       if $(isLinux)
                      then
                          SOCKET_MOUNT='/var/run/docker.sock:/var/run/docker.sock'
                      fi
                      if $(isWin)
                      then
                          SOCKET_MOUNT='//var/run/docker.sock:/var/run/docker.sock'
                      fi
                      docker run -p 8080:8080 -v $SOCKET_MOUNT -ti parma_light ;;

    --assess)         run_assess ;;

    --source)         # this is an command used in a prelinary demonstrator, that runs Parma Light a container
                      # it will be removed when a final demonstrator is implemented
                      if $(isLinux)
                      then
                          source .venv/bin/activate
                      fi
                      if $(isWin)
                      then
                          source .venv/Scripts/activate
                      fi ;;

    *)              echo "invalid command: $cmd - exit 4"
                    exit 4 ;;
    esac
done

exit 0
