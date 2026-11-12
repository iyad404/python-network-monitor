# Python Network Monitor

A cross-platform command-line network monitoring tool written in Python. It measures latency, packet loss and jitter, displays a live terminal dashboard, and exports CSV and JSON reports.

## Features

- Live network monitoring
- IPv4 hostname resolution
- Local IPv4 address and hostname
- Ping latency measurement
- Packet loss calculation
- Average, minimum and maximum latency
- Jitter estimate (mean absolute change between consecutive successful samples)
- Online, degraded, unstable and offline status
- Recent sample history
- CSV and JSON report export
- File-based application logging
- Custom target, interval, timeout, sample count, duration and output directory
- Windows, Linux and macOS support (requires the system `ping` command)
- No third-party Python packages required

## Requirements

- Python 3.10 or newer
- A working `ping` command available in PATH
- Network access for meaningful results

## Installation

Clone the repository:

```bash
git clone https://github.com/iyad404/python-network-monitor.git
cd python-network-monitor
```

Run the monitor:

```bash
python network_monitor.py
```

On some systems, use `python3` instead of `python`.

## Usage

Monitor the default Cloudflare DNS target:

```bash
python network_monitor.py
```

Monitor another IP or hostname:

```bash
python network_monitor.py --target 8.8.8.8
```

Monitor a hostname:

```bash
python network_monitor.py --target example.com
```

Change the interval to five seconds:

```bash
python network_monitor.py --interval 5
```

Use a two-second ping timeout:

```bash
python network_monitor.py --timeout 2
```

Stop automatically after 30 samples:

```bash
python network_monitor.py --count 30
```

Stop automatically after five minutes:

```bash
python network_monitor.py --duration 300
```

Save reports to a custom directory:

```bash
python network_monitor.py --output my_reports
```

Combine options:

```bash
python network_monitor.py --target 8.8.8.8 --interval 2 --timeout 1 --count 50
```

Stop at any time with `Ctrl+C`.

## Reports

When monitoring stops, the program creates:

- `reports/network_report_TIMESTAMP.csv` — one row per ping sample
- `reports/network_report_TIMESTAMP.json` — metadata, summary statistics and samples
- `reports/network_monitor.log` — application events and errors

The `reports/` directory is created automatically.

## How the metrics work

- **Latency:** round-trip time reported by the operating system's ping utility.
- **Packet loss:** failed ping attempts divided by all attempts, multiplied by 100.
- **Jitter estimate:** average absolute difference between consecutive successful latency samples. Failed samples are skipped.
- **Status:** a simple interpretation of the current collected samples. It is not a guarantee of overall internet health.

Ping can be blocked or rate-limited by firewalls and networks. A failed ping does not always mean that the internet connection is down.

## Project structure

```text
python-network-monitor/
├── network_monitor.py
├── README.md
├── requirements.txt
├── .gitignore
└── LICENSE
```

## Troubleshooting

### `ping` command not found

Make sure the system ping utility is installed and available in your PATH.

### Hostname cannot be resolved

Check the spelling of the hostname and verify DNS connectivity.

### All requests fail

The target may block ICMP, the network may be offline, or a firewall may filter ping traffic. Try another permitted target.

### No colored output

Colors are enabled only in supported interactive terminals.

## Responsible use

This tool sends ordinary ICMP echo requests to the target you specify. Only monitor systems and networks you own or have permission to test. Avoid aggressive intervals or excessive traffic.

## Author

**Iyad Zitouni**

GitHub: https://github.com/iyad404

---

Made with Python.
