# FastVPN

**FastVPN** is a simple Python script designed to streamline OpenVPN connections quickly and easily.

## Description

This Python script enables users to connect swiftly to OpenVPN servers without hassle. It randomly selects a server configuration (TCP or UDP) and initiates the connection, simplifying the process for users.

## Features

- Connects to random OpenVPN servers (TCP or UDP) effortlessly.
- Provides a quick and automated way to establish secure VPN connections.

## Requirements

- Python 3.x
- OpenVPN installed

## Installation

To use FastVPN, ensure the following dependencies are installed:

```bash
sudo apt install network-manager network-manager-openvpn-gnome openvpn

sudo systemctl restart NetworkManager
```

Additionally, download the VPN server configurations from the FastVPN website and extract the files:

```bash
wget https://vpn.ncapi.io/groupedServerList.zip

unzip groupedServerList.zip
```

This will create two directories: `tcp` and `udp`, which contain the necessary server configurations.

## Usage

1. Ensure Python and OpenVPN are installed on your system.
2. Clone or download the FastVPN repository.
3. Run the script with the following options:

   - `-t`/`--tcp`: Connects to a random TCP server.
   - `-u`/`--udp`: Connects to a random UDP server.
   - `-h`/`--help`: Displays the help message.

_Example usage:_

```bash
python main.py -t       # Connect to a random TCP server
python main.py --tcp

python main.py -u       # Connect to a random UDP server
python main.py --udp
```

## Configuration

For default username and password setup, create a `credentials.txt` file containing your credentials in the format:

```bash
your_username
your_password
```

Update the `credentials.txt` path in the script as needed.

## Contributing

Contributions are welcome! Feel free to fork the repository and submit pull requests.

## License

[GPLv3](./LICENSE)
