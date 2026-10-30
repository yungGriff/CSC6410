import requests
import ipaddress
import re

#Calls the API
API = "https://stat.ripe.net/data/{}/data.json"

#stores previous api results to not duplicate reqs
saved = {}

def lookup(endpoint, resource):
    # saves by using endpoint and the resource
    key = (endpoint, resource)

    # uses ripestat for non repeats
    if key not in saved:
        response = requests.get(
            API.format(endpoint),
            params={"resource": resource},
            timeout = 20
        )
        response.raise_for_status()
        # converts json response into a python dictionary
        saved[key] = response.json()["data"]

    #return the saved result
    return saved[key]

print("Paste Tracert Results")
lines = []

while (line := input ()) != "END":
    lines.append(line)

# Record the ASNs in order
as_path = []
# Record org names to not repeat looking up ASNs
names = {}
# iterate through the pasted tracert
for line in lines:
    # take the addresses of the current line
    for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line):
        try:
            # convert text to ip address
            address = ipaddress.ip_address(ip)

            # skip private addresses
            if not address.is_global:
                continue

            # ripestat prefixes and ASNs
            info = lookup("network-info", ip)
            print(f"IP={ip}, Prefix={info.get('prefix')}, ASNs={info.get('asns')}")
            # An IP can have more than one announcing ASN.
            for asn in info.get("asns", []):

                if not as_path or as_path[-1] != asn:
                    as_path.append(asn)

                # checj Orgs name
                if asn not in names:
                    # ripestat for more information
                    try:
                        overview = lookup("as-overview", f"AS{asn}")
                        names[asn] = overview.get("holder") or "unknown"
                        print(f"AS{asn} = {names[asn]}")
                    except Exception as error:
                        names[asn] = "Lookup failed"
                        print(f"error AS{asn}: {error}")

            # Handle API Failure
        except (ValueError, requests.RequestException, KeyError) as error:
            print(f"ERROR: IP={ip}, reason={error}")
            continue
# write results with AS and org name
print("\nAS Path:")
print(" -> ".join(
    f"AS{asn} ({names.get(asn, 'Unknown')})"
    for asn in as_path
))
# writes the number of recorded ASes
print("AS Count:", len(as_path))
