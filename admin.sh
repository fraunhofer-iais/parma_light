#!/bin/bash

function init {
    PARMA_DIR="$1"
    if [[ $PARMA_DIR == '' ]]
    then
        PARMA_DIR='datastore_parma'
    fi
    if [[ $PARMA_DIR == 'datastore_parma' && -d $PARMA_DIR/data_dir ]]
    then
        echo "parma datastore is a test directory and will be emptied"
        rm -rf $PARMA_DIR/*
    elif [[ -d $PARMA_DIR ]]
    then
        echo "parma datastore '$PARMA_DIR' exists. Init is ignored"
    else
        mkdir $PARMA_DIR
    fi
    cd $PARMA_DIR
    # git init
    mkdir data_dir temp_dir
    cp -r $BASE_DIR/initdata/* .
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
    ''|help)        cat admin-help.txt ;;

    backend)        python src/parma/backend.py ;;

    frontend)       python src/parma/frontend_cli.py ;;

    init)           init ;;
    
    image)          domain=$1; shift
                    name="$1"; shift
                    version="$1"; shift
                    make_image $domain $name $version ;;

    images)         domain=$1; shift
                    cd $BASE_DIR/test/container/$domain
                    for dir in */; do
                        dir_name="${dir%/}"
                        $BASE_DIR/admin.sh -q image "$domain" "$dir_name" "1"
                    done ;;

    dind-build)     docker build --no-cache -f docker/Dockerfile -t parma_light . ;;
    dind-run)       docker run -p 8080:8080 -v /var/run/docker.sock:/var/run/docker.sock -ti parma_light ;;

    assess)         run_assess ;;

    *)              echo "invalid command: $cmd - exit 4"
                    exit 4 ;;
    esac
done

exit 0
