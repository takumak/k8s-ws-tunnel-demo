import sys
import os
import argparse
import logging
import re
import random
import string
import subprocess
import time
import json
import tempfile


log = logging.getLogger('mktunnel')
log.setLevel(logging.INFO)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
handler_format = logging.Formatter('%(asctime)s [%(filename)s:%(lineno)s] %(message)s')
stream_handler.setFormatter(handler_format)
log.addHandler(stream_handler)


kptunnel_bin = os.path.join(os.path.dirname(__file__), 'kptunnel')
if not os.path.exists(kptunnel_bin):
    log.error('kptunnel command not found')
    sys.exit(1)


def kubectl(args, stdin=None, json_output=False):
    p = subprocess.run(
        [
            'kubectl',
            *args,
            *(['-o', 'json'] if json_output else []),
        ],
        capture_output=True,
        check=True,
        input=stdin,
        encoding='utf-8',
        errors='ignore',
    )
    if json_output:
        return json.loads(p.stdout)


def get_control_plane_ip():
    nodes = kubectl(['get', 'node', '-l', 'node-role.kubernetes.io/control-plane='], json_output=True)
    node = nodes['items'][0]
    for a in node['status']['addresses']:
        if a['type'] == 'InternalIP':
            return a['address']
    raise RuntimeError('Failed to get control plane ip')


class Tunnel:
    def __init__(self, bind_address, listen_port, forward_to_host, forward_to_port):
        self.bind_address = bind_address
        self.listen_port = listen_port
        self.forward_to_host = forward_to_host
        self.forward_to_port = forward_to_port
        self.tunnel_id = ''.join(random.choices(string.ascii_lowercase, k=16))
        self.ws_service_name = f'ws-{self.tunnel_id}'
        self.tun_service_name = f'tun-{self.tunnel_id}'

    def format(self, fmt):
        return fmt.format(
            bind_address = self.bind_address,
            listen_port = self.listen_port,
            forward_to_host = self.forward_to_host,
            forward_to_port = self.forward_to_port,
            tunnel_id = self.tunnel_id,
            ws_service_name = self.ws_service_name,
            tun_service_name = self.tun_service_name,
        )

    def start_server(self):
        with open(self.yaml_filename) as f:
            yaml_template = f.read()
        yaml_src = self.format(yaml_template)

        log.info('starting tunnel server')
        kubectl(['create', '-f', '-'], yaml_src)
        log.info('waiting for tunnel server ready')
        kubectl(['wait', 'pod', '-l', f'tunnel={self.tunnel_id}', '--for=condition=Ready'])

    def stop_server(self):
        kubectl(['delete', 'all', '-l', f'tunnel={self.tunnel_id}'])

    def start_client(self, logfile):
        cmd = [
            kptunnel_bin,
            self.kptunnel_client_mode,
            '-wspath', f'/{self.ws_service_name}',
            'localhost:80',
            f'{self.bind_address}:{self.listen_port},{self.forward_to_host}:{self.forward_to_port}'
        ]
        subprocess.run(cmd, check=True, stdout=logfile, stderr=logfile)

    @property
    def ws_url(self):
        return f'ws://localhost/{self.ws_service_name}'


class ForwardTunnel(Tunnel):
    yaml_filename = 'forward.yaml'
    kptunnel_client_mode = 'wsclient'

    def __init__(self, spec):
        m = re.match(r'^([a-zA-Z0-9\-\.]*):(\d+):([a-zA-Z0-9\-\.]+):(\d+)$', spec)
        if not m:
            raise ValueError(
                f'Invalid tunnel spec: {repr(spec)}'
                + ' (should be <bind-address>:<listen-port>:<forward-host>:<forward-port>)')
        super().__init__(
            bind_address = m.group(1),
            listen_port = int(m.group(2), 10),
            forward_to_host = m.group(3),
            forward_to_port = int(m.group(4), 10),
        )

    def listening_on(self):
        return self.bind_address, self.listen_port


class ReverseTunnel(Tunnel):
    yaml_filename = 'reverse.yaml'
    kptunnel_client_mode = 'r-wsclient'

    def __init__(self, spec):
        m = re.match(r'^([a-zA-Z0-9\-\.]+):(\d+)$', spec)
        if not m:
            raise ValueError(
                f'Invalid tunnel spec: {repr(spec)}'
                + ' (should be <forward-host>:<forward-port>)')
        super().__init__(
            bind_address = '',
            listen_port = 8888,
            forward_to_host = m.group(1),
            forward_to_port = int(m.group(2), 10),
        )

    def listening_on(self):
        host = get_control_plane_ip()
        svc = kubectl(['get', 'svc', self.tun_service_name], json_output=True)
        port = svc['spec']['ports'][0]['nodePort']
        return host, port


class Subcommand:
    subcommands = None

    def __init__(self, subparsers):
        self.parser = subparsers.add_parser(self.command_name)
        self.add_args(self.parser)
        self.parser.set_defaults(run=self.run)
        if self.subcommands:
            self.subparsers = self.parser.add_subparsers(title='commands', required=True)
            for subcommand_class in self.subcommands:
                subcommand = subcommand_class(self.subparsers)
                setattr(self, subcommand.command_name, subcommand)

    def add_args(self, parser):
        pass

    def run(self, args):
        print(self.command_name)


class TunnelCommand(Subcommand):
    command_name = 'tunnel'

    def add_args(self, parser):
        parser.add_argument('-L', type=ForwardTunnel)
        parser.add_argument('-R', type=ReverseTunnel)
        pass

    def run(self, args):
        if args.L and args.R:
            log.error('Argument -L and -R cannot be used together')
            sys.exit(1)

        if args.L:
            tunnel = args.L
        elif args.R:
            tunnel = args.R
        else:
            log.error('Either -L or -R must be specified')
            sys.exit(1)

        try:
            tunnel.start_server()
            log.info(f'ws url: {tunnel.ws_url}')

            host, port = tunnel.listening_on()
            log.info(f'listening on {host}:{port}')
            with tempfile.NamedTemporaryFile(prefix='kptunnel-', suffix='.log') as logfile:
                log.info(f'kptunnel log -> {logfile.name}')
                log.info('Press [Ctrl+C] to stop tunneling')
                while True:
                    tunnel.start_client(logfile)
                    time.sleep(1)

        except KeyboardInterrupt:
            pass
        finally:
            log.info('cleanup')
            tunnel.stop_server()

class ArgumentParser:
    subcommands = [
        TunnelCommand,
    ]

    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.subparsers = self.parser.add_subparsers(title='commands', required=True)
        for subcommand_class in self.subcommands:
            subcommand = subcommand_class(self.subparsers)
            setattr(self, subcommand.command_name, subcommand)

    def parse_args(self):
        return self.parser.parse_args()


def main():
    parser = ArgumentParser()
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
