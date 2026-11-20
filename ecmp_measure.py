
#!/usr/bin/env python3

"""
ECMP measurement script for CSC 6410 Experiment 3.

Reads transmit byte counters from the four core-facing
ports in pod 0, runs UDP traffic, and calculates the
share of bytes carried by each path.

Run from the Mininet CLI using:
    py exec(open('/work/ecmp_measure.py').read())
    py run_experiment(net, 4)
"""

import subprocess
import re
import json
import csv
import time

LINKS = [
    ("a00", 3, "a00-eth3 -> c00"),
    ("a00", 4, "a00-eth4 -> c01"),
    ("a01", 3, "a01-eth3 -> c10"),
    ("a01", 4, "a01-eth4 -> c11"),
]

def read_counters():
    """Read cumulative TX byte counters for the four links."""
    counters = {}

    for switch, port, label in LINKS:
        output = subprocess.check_output(
            ["ovs-ofctl", "-O", "OpenFlow13",
             "dump-ports", switch, str(port)],
            text=True
        )

        match = re.search(r"tx pkts=\d+, bytes=(\d+)", output)

        if not match:
            raise RuntimeError(
                f"Could not read counter for {label}: {output}"
            )

        counters[label] = int(match.group(1))

    return counters


def run_experiment(net, flow_count, duration=20):
    """Run one UDP test and calculate the four link shares."""

    source = net.get("h000")
    destination = net.get("h300")

    print(f"\nStarting {flow_count}-flow experiment")

    # Start the iperf3 server on the destination host.
    destination.cmd("iperf3 -s -D")
    time.sleep(1)

    # Read counters immediately before the traffic test.
    before = read_counters()

    command = (
        f"iperf3 -c {destination.IP()} -u "
        f"-b 1M -P {flow_count} -t {duration} --json"
    )

    print("\nClient command:")
    print(command)

    result = source.cmd(command)

    try:
        iperf_data = json.loads(result)
    except json.JSONDecodeError:
        raise RuntimeError(
            "Could not read iperf3 JSON output:\n" + result
        )

    if "error" in iperf_data:
        raise RuntimeError(iperf_data["error"])

    # Read counters immediately after the traffic test.
    after = read_counters()

    print("\niperf3 summary:")
    print("Sent UDP traffic. JSON result follows:")
    print(json.dumps(iperf_data.get("end", {}), indent=2))

    print("\nCore link measurements:")

    deltas = {}

    for label in before:
        deltas[label] = after[label] - before[label]

    total_bytes = sum(deltas.values())

    if total_bytes == 0:
        raise RuntimeError("No transmitted bytes were measured.")

    for label, byte_count in deltas.items():
        share = byte_count / total_bytes * 100
        print(
            f"{label}: {byte_count:,} bytes "
            f"({share:.2f}%)"
        )

    mean_bytes = total_bytes / len(LINKS)
    busiest_bytes = max(deltas.values())
    max_mean = busiest_bytes / mean_bytes

    print(f"\nTotal measured bytes: {total_bytes:,}")
    print(f"Busiest link share: {busiest_bytes / total_bytes * 100:.2f}%")
    print(f"Max/mean ratio: {max_mean:.3f}")

    # Append the results to a CSV file.
    with open("/work/ecmp_results.csv", "a", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            flow_count,
            duration,
            *[deltas[label] for label in deltas],
            total_bytes,
            busiest_bytes / total_bytes,
            max_mean
        ])

    # Save the raw counter readings.
    with open("/work/ecmp_raw.txt", "a") as file:
        file.write(f"\nFlow count: {flow_count}\n")
        file.write(f"Before: {before}\n")
        file.write(f"After: {after}\n")
        file.write(f"Byte differences: {deltas}\n")
        file.write(f"iperf3 output:\n{result}\n")

    return deltas
