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
        """Return a list of available .ovpn files in the directory."""
        try:
            return [file.name for file in directory.iterdir() if file.is_file()]
        except FileNotFoundError:
            print(f"❌ Error: Directory not found: {directory}")
            return None

    def get_random_file(self, file_list):
        return random.choice(file_list) if file_list else None

    def connect_vpn(self, config_type, file_name=None):
        """Connect to a VPN using a random or specific .ovpn config."""
        directory = self.tcp_dir if config_type == "tcp" else self.udp_dir
        file_list = self.get_file_list(directory)

        if not file_list:
            print(f"❌ No configuration files found in {directory}")
            sys.exit(1)

        selected_file = None

        if file_name:
            file_path = Path(file_name).expanduser().resolve()

            # If user provided a full/relative path that exists
            if file_path.exists() and file_path.suffix == ".ovpn":
                selected_file = file_path.name
                directory = file_path.parent
            else:
                # Try to match just by filename inside tcp/udp directory
                base_name = Path(file_name).name
                if base_name in file_list:
                    selected_file = base_name
                else:
                    print(f"\n❌ Error: '{file_name}' not found in {directory}")
                    print("\nAvailable configuration files:\n")
                    preview = sorted(file_list)[:3]
                    for f in preview:
                        print(f"  {f}")
                    if len(file_list) > 3:
                        print(f"  ... and {len(file_list) - 3} more")
                    print("\n💡 Example usage:")
                    print(f"  python main.py -t -f '{preview[0]}'")
                    sys.exit(1)
        else:
            selected_file = self.get_random_file(file_list)

        print(f"🔌 Connecting to {selected_file} ({config_type.upper()})...")
        config_path = directory / selected_file

        if not config_path.exists():
            print(f"❌ Config file not found: {config_path}")
            sys.exit(1)

        if not self.creds.exists():
            print("\n⚠️  Credentials file not found!")
            print("Please create a 'credentials.txt' file with your FastVPN username and password.")
            print("Otherwise, you will be prompted each time.\n")
            cmd = f"sudo openvpn --config '{config_path}'"
            subprocess.run(cmd, shell=True)
            return

        cmd = f"sudo openvpn --config '{config_path}' --auth-user-pass '{self.creds}'"
        subprocess.run(cmd, shell=True)

    def print_help(self):
        print("""
Usage:
  python main.py [OPTIONS]

Description:
  Connect to a random or specific FastVPN server using OpenVPN.

Options:
  -t, --tcp               Connect to a random TCP server
  -u, --udp               Connect to a random UDP server
  -f, --file <filename>   Connect to a specific .ovpn file in tcp/ or udp/
  -h, --help              Show this help message and exit

Examples:
  Connect to a random TCP server:
    python main.py -t

  Connect to a random UDP server:
    python main.py -u

  Connect to a specific TCP file (by name):
    python main.py -t -f "NCVPN-AE-Paris-TCP.ovpn"

  Connect using a full or relative path:
    python main.py -t -f "./tcp/NCVPN-AE-Paris-TCP.ovpn"
    python main.py -u -f "/home/user/FastVPN/udp/NCVPN-US-NewYork-UDP.ovpn"

Notes:
  - Place all your .ovpn config files in 'tcp/' or 'udp/' directories.
  - Optionally create a 'credentials.txt' file with your username and password.
""")

    def main(self):
        parser = argparse.ArgumentParser(
            description="Fast VPN",
            add_help=False  # Disable default help to use our custom version
        )
        parser.add_argument("-t", "--tcp", action="store_true", help="Connect to a random TCP server")
        parser.add_argument("-u", "--udp", action="store_true", help="Connect to a random UDP server")
        parser.add_argument("-f", "--file", type=str, help="Specify a particular .ovpn file to connect to")
        parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")

        args = parser.parse_args()

        if args.help:
            self.print_help()
            sys.exit(0)

        if args.file:
            if args.tcp:
                self.connect_vpn("tcp", args.file)
            elif args.udp:
                self.connect_vpn("udp", args.file)
            else:
                print("\n❌ Error: You must specify whether it's TCP or UDP when using --file.")
                print("\n💡 Example:")
                print("  python main.py -t -f 'NCVPN-AE-Paris-TCP.ovpn'")
                print("  python main.py -u -f 'NCVPN-US-NewYork-UDP.ovpn'")
                sys.exit(1)
        elif args.tcp:
            self.connect_vpn("tcp")
        elif args.udp:
            self.connect_vpn("udp")
        else:
            print("\n⚠️  No option provided. Connecting to a random TCP server by default.")
            print("💡 You can specify UDP with '-u' or a specific file with '-f <filename>'.\n")
            self.connect_vpn("tcp")


if __name__ == "__main__":
    fast_vpn = FastVPN()
    fast_vpn.main()
