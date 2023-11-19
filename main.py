#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import random
import subprocess
import sys
from pathlib import Path


class FastVPN:
    def __init__(self):
        self.current_dir = Path(__file__).parent.resolve()
        self.tcp_dir = self.current_dir / "tcp"
        self.udp_dir = self.current_dir / "udp"
        self.creds = self.current_dir / "credentials.txt"

    def get_file_list(self, directory):
        file_list = []
        try:
            for file in directory.iterdir():
                if file.is_file():
                    file_list.append(file.name)
            return file_list
        except FileNotFoundError:
            print(f"tcp / udp directory not found")
            return None

    def get_random_file(self, file_list):
        if len(file_list) == 0:
            return None
        return random.choice(file_list)

    def connect_vpn(self, config_type):
        directory = self.tcp_dir if config_type == "tcp" else self.udp_dir
        file_list = self.get_file_list(directory)

        if not file_list:
            sys.exit(1)

        selected_file = self.get_random_file(file_list)
        print(f"Connecting to {selected_file}")
        # cmd = f"sudo openvpn --config {directory}/{selected_file}"

        if not self.creds.exists():
            print(f"Credentials file not found!")
            print(
                f"Please create a credentials.txt file with your FastVPN Network Credentials, username and password"
            )
            sys.exit(1)

        cmd = f"sudo openvpn --config {directory}/{selected_file} --auth-user-pass {self.creds}"

        subprocess.run(cmd, shell=True)

    def get_help(self):
        print("Usage: fast_vpn.py [OPTIONS]")
        print("Connect to a random VPN server")
        print("")
        print("Options:")
        print("  -t, --tcp   Connect to a random TCP server")
        print("  -u, --udp   Connect to a random UDP server")
        print("  -h, --help  Show this message and exit")

    def main(self):
        parser = argparse.ArgumentParser(description="Fast VPN")
        parser.add_argument(
            "-t",
            "--tcp",
            action="store_true",
            help="Connect to a random TCP server",
        )
        parser.add_argument(
            "-u",
            "--udp",
            action="store_true",
            help="Connect to a random UDP server",
        )

        args = parser.parse_args()

        if args.tcp:
            self.connect_vpn("tcp")
        elif args.udp:
            self.connect_vpn("udp")
        else:
            self.connect_vpn("tcp")


if __name__ == "__main__":
    fast_vpn = FastVPN()
    fast_vpn.main()
