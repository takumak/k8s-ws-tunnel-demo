import sys
import os
import argparse
import logging
import re
import random
import string
import subprocess
import time


def main():
    kptunnel_bin = os.path.join(os.path.dirname(__file__), 'kptunnel')
    if not os.path.exists(kptunnel_bin):
        logging.error('kptunnel command not found')
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument('-L')
    parser.add_argument('-R')
    args = parser.parse_args()

    if args.L and args.R:
        logging.error('Argument -L and -R cannot be used together')
        sys.exit(1)

    if args.L:
        yaml_filename = 'forward.yaml'
        spec = args.L
    elif args.R:
        yaml_filename = 'reverse.yaml'
        spec = args.R
    else:
        logging.error('Either -L or -R must be specified')
        sys.exit(1)

    m = re.match(r'^([a-zA-Z0-9\-\.]*):(\d+):([a-zA-Z0-9\-\.]+):(\d+)$', spec)
    if not m:
        logging.error(f'Invalid tunnel spec: {repr(spec)}'
                      + ' (should be bind-address:listen-port:forward-host:forward-port)')
        sys.exit(1)

    bind_address = m.group(1)
    listen_port = int(m.group(2), 10)
    forward_to_host = m.group(3)
    forward_to_port = int(m.group(4))
    tunnel_id = ''.join(random.choices(string.ascii_lowercase, k=16))
    service_name = f'tunnel-{tunnel_id}'

    with open(yaml_filename) as f:
        yaml_template = f.read()

    yaml_src = yaml_template.format(
        bind_address = bind_address,
        listen_port = listen_port,
        forward_to_host = forward_to_host,
        forward_to_port = forward_to_port,
        tunnel_id = tunnel_id,
        service_name = service_name,
    )

    try:
        logging.info('create pod')
        subprocess.run(
            ['kubectl', 'create', '-f', '-'],
            input=yaml_src.encode('utf-8'),
            check=True,
        )

        logging.info('wait for ready')
        subprocess.run(
            ['kubectl', 'wait', 'pod', '-l', f'tunnel={tunnel_id}', '--for=condition=Ready'],
            check=True,
        )

        logging.info(f'endpoint: ws://localhost/tunnel-{tunnel_id}')

        logging.info(f'start listening on {bind_address}:{listen_port}')

        while True:
            subprocess.run(
                [
                    kptunnel_bin,
                    'wsclient',
                    '-wspath', f'/{service_name}',
                    'localhost:80',
                    f'{bind_address}:{listen_port},{forward_to_host}:{forward_to_port}'
                ],
                check=True,
            )

    except KeyboardInterrupt:
        pass
    finally:
        print('cleanup')
        subprocess.run(
            ['kubectl', 'delete', 'all', '-l', f'tunnel={tunnel_id}'],
            check=True,
        )


if __name__ == '__main__':
    main()
