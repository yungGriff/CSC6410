import time
import json
import pathlib
import subprocess
import socket

from datetime import datetime
from jsonschema import Draft202012Validator


# 1. Locate project files

HERE = pathlib.Path(__file__).parent

SCHEMA = json.loads((HERE / "host_schema.json").read_text())

TOP = "student-host:host"


# 2. Collect network information

def collect_network():

    command = r"""
    $adapters = Get-NetAdapter -IncludeHidden

    $interfaces = foreach ($a in $adapters) {

        $ip = Get-NetIPAddress -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue

        $mtu = Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Select-Object -First 1

        $type = "other"

        if ($a.Name -match "Wi-Fi|Wireless") {
            $type = "wifi"
        }
        elseif ($a.Name -match "Ethernet") {
            $type = "ethernet"
        }
        elseif ($a.Name -match "Virtual|vEthernet|VMware") {
            $type = "virtual"
        }

        $mac = $a.MacAddress -replace "-", ":"

        # Every interface needs a name and operating status.
        $item = [ordered]@{
            name = $a.Name
            type = $type
            "oper-status" = if ($a.Status -eq "Up") { "up" } else { "down" }
        }

        # Only add MAC addresses that match the required format.
        if ($mac -match '^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$') {
            $item["mac"] = $mac.ToLower()
        }

        # Only add MTU values that are within the schema range.
        if ($null -ne $mtu -and
            $null -ne $mtu.NlMtu -and
            [int]$mtu.NlMtu -ge 68 -and
            [int]$mtu.NlMtu -le 65536) {

            $item["mtu"] = [int]$mtu.NlMtu
        }

        # Collect IPv4 addresses and prefix lengths.
        $ipv4 = @(
            $ip | Where-Object { $_.AddressFamily -eq "IPv4" } |
            ForEach-Object {
                "$($_.IPAddress)/$($_.PrefixLength)"
            }
        )

        if ($ipv4.Count -gt 0) {
            $item["ipv4"] = $ipv4
        }

        # Collect IPv6 addresses and prefix lengths.
        $ipv6 = @(
            $ip | Where-Object { $_.AddressFamily -eq "IPv6" } |
            ForEach-Object {
                "$($_.IPAddress)/$($_.PrefixLength)"
            }
        )

        if ($ipv6.Count -gt 0) {
            $item["ipv6"] = $ipv6
        }

        [PSCustomObject]$item
    }

    # Find the default IPv4 gateway.
    $gateway = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric |
        Select-Object -First 1

    # Collect DNS server addresses.
    $dns = @(
        Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
        ForEach-Object { $_.ServerAddresses } |
        Where-Object { $_ } |
        Select-Object -Unique
    )

    # Build the network information to send back to Python.
    [PSCustomObject]@{
        interface = @($interfaces)
        gateway = if ($gateway) { $gateway.NextHop } else { $null }
        dns = $dns
    } | ConvertTo-Json -Depth 6
    """

    # Run the PowerShell network collection.
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=True
    )

    # Make sure PowerShell returned some information.
    if not result.stdout.strip():
        raise RuntimeError("PowerShell did not return any network information.")

    return json.loads(result.stdout)


# 3. Build observed configuration

def build_observed():

    # Collect the current network information.
    network = collect_network()

    # Build the host configuration.
    host = {
        "hostname": socket.gethostname(),
        "os": "windows",
        "collected-at": datetime.now().astimezone().isoformat(),
        "dns-server": network.get("dns", []),
        "interface": network.get("interface", [])
    }

    # Only add the gateway if PowerShell found one.
    if network.get("gateway"):
        host["default-gateway"] = network["gateway"]

    return {
        TOP: host
    }


# 4. Validate configuration

def schema_errors(cfg):

    # Check the observed configuration against the JSON schema.
    validator = Draft202012Validator(SCHEMA)

    return [
        f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
        for e in validator.iter_errors(cfg)
    ]


# 5. Compare intended and observed configuration

def check_drift(intended, observed):

    differences = []

    # Check each field in the intended configuration.
    for field in intended[TOP]:

        if intended[TOP][field] != observed[TOP].get(field):

            differences.append(
                f"{field}: intended = {intended[TOP][field]}, "
                f"observed = {observed[TOP].get(field, 'missing')}"
            )

    return differences


# 6. Run the audit

if __name__ == "__main__":

    observed = build_observed()

    # Save the collected information.
    (HERE / "observed.json").write_text(
        json.dumps(observed, indent=4)
    )

    print("Observed configuration saved.")

    # Validate the observed configuration.
    errors = schema_errors(observed)

    if errors:
        print("\nSchema errors:")

        for error in errors:
            print(error)

    else:
        print("\nSchema validation successful!")

    # Load the intended configuration.
    intended = json.loads((HERE / "intended.json").read_text())

    # Compare the intended and observed configurations.
    differences = check_drift(intended, observed)

    print("\nDrift report:")

    if differences:

        for difference in differences:
            print(difference)

    else:
        print("No configuration drift detected.")
