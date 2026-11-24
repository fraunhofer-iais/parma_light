import os
from pathlib import Path
import argparse
import logging

import intern.helper as h
import intern.msg as msg
import intern.database as db
import component.run as run

from flask import Flask


_static_folder = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_url_path='', static_folder=str(_static_folder))

from routes import bp  # noqa: E402  (import after app creation so blueprint can use db/components)
app.register_blueprint(bp)


def main() -> None:
    """
    Main entry point for the parma backend.
    """
    parser = argparse.ArgumentParser(description='Parma Light Backend Server')
    parser.add_argument('-c', '--config', help='yaml configuration file path', default='./parma_light.yaml')
    parser.add_argument('-d', '--debugpy', help='activate debugpy for remote debugging', default=False, action='store_true')
    args = parser.parse_args()

    # Load yaml configuration and store the configuration in the app config for dependency injection
    yaml_config_file = Path(args.config)
    yaml_config = h.load_yaml_config(yaml_config_file)
    app.config['config'] = yaml_config
    
    # init logging
    logging_level = yaml_config.get('logging', {}).get('level', logging.INFO)
    logging_file = '/app/parma_light.log' if h.RUNNING_IN_CONTAINER else yaml_config.get('store', {}).get('log_file', './datastore_parma/parma_light.log')
    logging.basicConfig(format='%(asctime)s - %(name)-20s - %(levelname)-8s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        filename=logging_file,
                        encoding='utf-8',
                        level=logging_level)
    logger = logging.getLogger(__name__)

    # Get the store configuration
    host_os = os.environ.get("HOST_OPERATING_SYSTEM")
    if h.RUNNING_IN_CONTAINER:
        logger.info("parma light is running in a docker container based on linux")
        entity_store = '/entity_store'
        data_dir = '/data_dir'
        temp_dir = '/temp_dir'
        base_dir = '/base_dir'
        data_dir_for_mount = os.environ.get("PARMA_LIGHT_DATA_DIR_HOST")
        temp_dir_for_mount = os.environ.get("PARMA_LIGHT_TEMP_DIR_HOST")
    else:
        logger.info(f"parma light is running on a local {host_os} machine")
        entity_store = yaml_config.get('store', {}).get('entity_store')
        data_dir = yaml_config.get('store', {}).get('data_dir')
        temp_dir = yaml_config.get('store', {}).get('temp_dir')
        base_dir = yaml_config.get('store', {}).get('base_dir')
        data_dir_for_mount = None
        temp_dir_for_mount = None
    db.init(host_os, entity_store, data_dir, temp_dir, base_dir, data_dir_for_mount, temp_dir_for_mount)

    # Get host and port from config or use defaults
    host = yaml_config.get('server', {}).get('host', '0.0.0.0')
    port = yaml_config.get('server', {}).get('port', 8080)
    kind_of_server = yaml_config.get('server', {}).get('server', 'waitress')

    # get tool configuration
    bash_on_linux = yaml_config.get('tools', {}).get('bash_on_linux', '/bin/bash')
    bash_on_windows = yaml_config.get('tools', {}).get('bash_on_windows', '/bin/bash')
    nix_on_linux = yaml_config.get('tools', {}).get('nix_on_linux', '/bin/bash')
    run.init(bash_on_linux, bash_on_windows, nix_on_linux)

    try:
        if kind_of_server == 'development':
            msg_dict = {"msg": "PROD_SERVER", "wsgi": "development", "host": host, "port": port}
            msg_text = msg.get_message_text(msg_dict)
            print(msg_text)
            msg.log(logger.info, msg_dict)
            app.run(host=host, port=port)
        elif kind_of_server == 'development_debug':
            msg_dict = {"msg": "PROD_SERVER", "wsgi": "debug", "host": host, "port": port}
            msg_text = msg.get_message_text(msg_dict)
            print(msg_text)
            msg.log(logger.info, msg_dict)
            app.run(host=host, port=port, debug=True)
        elif kind_of_server == 'waitress':
            from waitress import serve
            msg_dict = {"msg": "PROD_SERVER", "wsgi": "waitress", "host": host, "port": port}
            msg_text = msg.get_message_text(msg_dict)
            print(msg_text)
            msg.log(logger.info, msg_dict)
            serve(app, host=host, port=port)
        else:
            from waitress import serve
            msg.log(logger.error, {"msg": "INVALID_PROPERTY", "property": "server", "replacement": 'waitress'})
            msg_dict = {"msg": "PROD_SERVER", "wsgi": "waitress", "host": host, "port": port}
            msg_text = msg.get_message_text(msg_dict)
            print(msg_text)
            msg.log(logger.info, msg_dict)
            serve(app, host=host, port=port)
    finally:
        db.store_tables()
        db.remove_all_temp_directories()
        print('server terminated successfully')


if __name__ == "__main__":
    main()

