#!/usr/bin/env python3
"""
Python Network Monitor
A cross-platform command-line network monitoring tool.
Uses only Python's standard library and the system ping command.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


APP_NAME = "Python Network Monitor"
DEFAULT_TARGET = "1.1.1.1"
DEFAULT_INTERVAL = 2.0
DEFAULT_TIMEOUT = 1.0
DEFAULT_LOG_DIR = Path("reports")


# ---------- Terminal helpers ----------

class Colors:
    """ANSI terminal colors. Disabled automatically when output is redirected."""
    enabled = sys.stdout.isatty() and platform.system() != "Windows"

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"

    @classmethod
    def paint(cls, text: str, color: str) -> str:
        if not cls.enabled:
            return text
        return f"{color}{text}{cls.RESET}"


def clear_screen() -> None:
    """Clear the terminal before drawing the live dashboard."""
    if sys.stdout.isatty():
        os_name = platform.system()
        os_command = "cls" if os_name == "Windows" else "clear"
        subprocess.run(os_command, shell=True, check=False)


# ---------- Data model ----------

@dataclass
class PingResult:
    timestamp: str
    target: str
    success: bool
    latency_ms: Optional[float]
    error: str = ""


# ---------- Network information ----------

def get_local_ip() -> str:
    """Find the local IPv4 address used for outbound traffic."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect does not send application data; it asks the OS
        # which local interface would be used for this destination.
        sock.connect((DEFAULT_TARGET, 80))
        return sock.getsockname()[0]
    except OSError:
        return "Unavailable"
    finally:
        sock.close()


def get_hostname() -> str:
    """Return this computer's network hostname."""
    return socket.gethostname()


def resolve_target(target: str) -> list[str]:
    """Resolve a hostname or IP address to IPv4 addresses."""
    try:
        records = socket.getaddrinfo(target, None, socket.AF_INET, socket.SOCK_STREAM)
        return sorted({record[4][0] for record in records})
    except socket.gaierror:
        return []


# ---------- Ping engine ----------

def build_ping_command(target: str, timeout: float) -> list[str]:
    """Build the correct one-packet ping command for this operating system."""
    os_name = platform.system().lower()

    if os_name == "windows":
        timeout_ms = max(1, int(timeout * 1000))
        return ["ping", "-n", "1", "-w", str(timeout_ms), target]

    if os_name == "darwin":
        timeout_ms = max(1, int(timeout * 1000))
        return ["ping", "-c", "1", "-W", str(timeout_ms), target]

    # Linux and most other Unix-like systems use seconds for -W.
    timeout_seconds = max(1, int(timeout + 0.999))
    return ["ping", "-c", "1", "-W", str(timeout_seconds), target]


def parse_latency(output: str) -> Optional[float]:
    """Extract latency from common Windows, Linux and macOS ping output."""
    patterns = [
        r"time[=<]\s*([\d.,]+)\s*ms",
        r"time\s*=\s*([\d.,]+)\s*ms",
    ]

    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", ".")
            try:
                return float(value)
            except ValueError:
                pass

    return None


def ping_once(target: str, timeout: float) -> PingResult:
    """Send one ping and return a structured result."""
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if shutil.which("ping") is None:
        return PingResult(timestamp, target, False, None, "The ping command was not found.")

    command = build_ping_command(target, timeout)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout + 3,
            check=False,
        )
        output = completed.stdout + "\n" + completed.stderr

        if completed.returncode == 0:
            latency = parse_latency(output)
            if latency is not None:
                return PingResult(timestamp, target, True, latency)
            # Some systems report success without a parseable time.
            return PingResult(timestamp, target, True, None, "Reply received; latency unavailable.")

        error = output.strip().splitlines()
        message = error[-1][:180] if error else "No reply."
        return PingResult(timestamp, target, False, None, message)

    except subprocess.TimeoutExpired:
        return PingResult(timestamp, target, False, None, "Ping process timed out.")
    except OSError as exc:
        return PingResult(timestamp, target, False, None, str(exc))


# ---------- Statistics ----------

def calculate_stats(results: list[PingResult]) -> dict:
    """Calculate useful statistics from all recorded ping results."""
    total = len(results)
    successful = [r for r in results if r.success]
    latencies = [r.latency_ms for r in successful if r.latency_ms is not None]
    failed = total - len(successful)

    if total == 0:
        loss = 0.0
    else:
        loss = failed / total * 100

    if len(latencies) > 1:
        jitter = statistics.mean(
            abs(latencies[index] - latencies[index - 1])
            for index in range(1, len(latencies))
        )
    else:
        jitter = 0.0

    return {
        "total": total,
        "successful": len(successful),
        "failed": failed,
        "packet_loss_percent": round(loss, 2),
        "min_ms": round(min(latencies), 2) if latencies else None,
        "max_ms": round(max(latencies), 2) if latencies else None,
        "average_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "jitter_ms": round(jitter, 2),
    }


def connection_status(stats: dict) -> tuple[str, str]:
    """Return a simple human-readable status and terminal color."""
    if stats["total"] == 0 or stats["successful"] == 0:
        return "OFFLINE", Colors.RED
    if stats["packet_loss_percent"] > 10:
        return "UNSTABLE", Colors.YELLOW
    if stats["packet_loss_percent"] > 0:
        return "DEGRADED", Colors.YELLOW
    return "ONLINE", Colors.GREEN


# ---------- Reports ----------

def ensure_report_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def export_csv(results: list[PingResult], output_path: Path) -> None:
    """Save every ping sample to a CSV file."""
    ensure_report_dir(output_path.parent)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "target", "success", "latency_ms", "error"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def export_json(results: list[PingResult], target: str, output_path: Path) -> None:
    """Save samples and summary statistics to a JSON report."""
    ensure_report_dir(output_path.parent)
    report = {
        "application": APP_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": target,
        "host": get_hostname(),
        "local_ip": get_local_ip(),
        "statistics": calculate_stats(results),
        "samples": [asdict(result) for result in results],
    }
    output_path.write_text(json.dumps(report, indent=4), encoding="utf-8")


def setup_logging(log_dir: Path) -> None:
    ensure_report_dir(log_dir)
    logging.basicConfig(
        filename=log_dir / "network_monitor.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
    )


# ---------- Dashboard ----------

def format_latency(value: Optional[float]) -> str:
    return f"{value:.2f} ms" if value is not None else "N/A"


def draw_dashboard(
    target: str,
    results: list[PingResult],
    interval: float,
    started_at: datetime,
    latest: Optional[PingResult],
) -> None:
    """Render the live terminal dashboard."""
    stats = calculate_stats(results)
    status, color = connection_status(stats)
    elapsed = datetime.now() - started_at

    clear_screen()
    print(Colors.paint("=" * 64, Colors.CYAN))
    print(Colors.paint(f"  {APP_NAME}", Colors.BOLD + Colors.CYAN))
    print(Colors.paint("=" * 64, Colors.CYAN))
    print(f"  Host       : {get_hostname()}")
    print(f"  Local IPv4 : {get_local_ip()}")
    print(f"  Target     : {target}")
    print(f"  Resolved   : {', '.join(resolve_target(target)) or 'Unresolved'}")
    print(f"  Interval   : {interval:g} second(s)")
    print(f"  Runtime    : {str(elapsed).split('.')[0]}")
    print("-" * 64)

    print(f"  STATUS     : {Colors.paint(status, color)}")
    if latest:
        if latest.success:
            print(f"  Latest     : Reply - {format_latency(latest.latency_ms)}")
        else:
            print(f"  Latest     : {Colors.paint('No reply', Colors.RED)} ({latest.error})")
    else:
        print("  Latest     : Waiting for first sample")

    print("-" * 64)
    print(f"  Sent       : {stats['total']}")
    print(f"  Received   : {stats['successful']}")
    print(f"  Failed     : {stats['failed']}")
    print(f"  Packet loss: {stats['packet_loss_percent']:.2f}%")
    print(f"  Minimum    : {format_latency(stats['min_ms'])}")
    print(f"  Average    : {format_latency(stats['average_ms'])}")
    print(f"  Maximum    : {format_latency(stats['max_ms'])}")
    print(f"  Jitter     : {stats['jitter_ms']:.2f} ms")
    print("-" * 64)

    print("  Recent samples:")
    for result in results[-8:]:
        clock = result.timestamp.split("T")[-1].replace("+00:00", "")
        if result.success:
            line = f"  {clock}  OK       {format_latency(result.latency_ms)}"
            print(Colors.paint(line, Colors.GREEN))
        else:
            line = f"  {clock}  TIMEOUT  {result.error[:45]}"
            print(Colors.paint(line, Colors.RED))

    print("-" * 64)
    print("  Press Ctrl+C to stop and generate reports.")
    print(Colors.paint("=" * 64, Colors.CYAN))


# ---------- Main monitoring loop ----------

def run_monitor(args: argparse.Namespace) -> int:
    target = args.target
    interval = args.interval
    timeout = args.timeout
    results: list[PingResult] = []
    started_at = datetime.now()
    start_clock = time.monotonic()
    latest: Optional[PingResult] = None
    sequence = 0

    setup_logging(args.output)
    logging.info("Monitor started for target %s", target)

    resolved = resolve_target(target)
    if not resolved:
        print(f"Error: could not resolve target '{target}'. Check the hostname or DNS.")
        logging.error("Could not resolve target %s", target)
        return 2

    print(f"Monitoring {target} ({', '.join(resolved)})...")
    print("Press Ctrl+C to stop.")
    time.sleep(1)

    try:
        while True:
            cycle_start = time.monotonic()
            latest = ping_once(target, timeout)
            results.append(latest)
            sequence += 1

            if latest.success:
                logging.info("Ping success: %s ms", latest.latency_ms)
            else:
                logging.warning("Ping failed: %s", latest.error)

            draw_dashboard(target, results, interval, started_at, latest)

            if args.count and sequence >= args.count:
                break
            if args.duration and (time.monotonic() - start_clock) >= args.duration:
                break

            spent = time.monotonic() - cycle_start
            time.sleep(max(0.0, interval - spent))

    except KeyboardInterrupt:
        print("\nStopping monitor...")

    finally:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = args.output / f"network_report_{timestamp}.csv"
        json_path = args.output / f"network_report_{timestamp}.json"

        export_csv(results, csv_path)
        export_json(results, target, json_path)
        logging.info("Monitor stopped; reports saved.")

        stats = calculate_stats(results)
        status, color = connection_status(stats)

        print("\n========== FINAL REPORT ==========")
        print(f"Target: {target}")
        print(f"Status: {Colors.paint(status, color)}")
        print(f"Samples: {stats['total']}")
        print(f"Packet loss: {stats['packet_loss_percent']:.2f}%")
        print(f"Average ping: {format_latency(stats['average_ms'])}")
        print(f"Jitter: {stats['jitter_ms']:.2f} ms")
        print(f"CSV report: {csv_path}")
        print(f"JSON report: {json_path}")
        print(f"Log file: {args.output / 'network_monitor.log'}")

    return 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor network latency, packet loss and jitter."
    )
    parser.add_argument(
        "-t", "--target",
        default=DEFAULT_TARGET,
        help=f"IP address or hostname to monitor (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="Seconds between ping attempts (default: 2)",
    )
    parser.add_argument(
        "-T", "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Ping timeout in seconds (default: 1)",
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        default=0,
        help="Stop after this many samples; 0 means run until Ctrl+C",
    )
    parser.add_argument(
        "-d", "--duration",
        type=float,
        default=0,
        help="Stop after this many seconds; 0 means no time limit",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help="Directory for CSV, JSON and log reports (default: reports)",
    )

    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be greater than zero.")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero.")
    if args.count < 0 or args.duration < 0:
        parser.error("--count and --duration cannot be negative.")

    return args


def main() -> int:
    args = parse_arguments()
    return run_monitor(args)


if __name__ == "__main__":
    raise SystemExit(main())
