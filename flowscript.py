import os
from functools import partial

from mininet.net import Mininet
from mininet.topo import SingleSwitchTopo
from mininet.node import OVSSwitch
from mininet.log import setLogLevel


#Switch setting for lab environment
switch_setting = os.environ.get("MN_SWITCH", "ovsk")

if "datapath=user" in switch_setting:
    switch_type = partial(OVSSwitch, datapath="user")
else:
    switch_type = OVSSwitch


def show_flows(switch, message):
    #current rules
    print("\n---", message, "---")
    print(switch.cmd("ovs-ofctl dump-flows s1"))


def test_all_pings(network, message):
    #Reach out to hosts
    print("\n---", message, "---")
    lost_packets = network.pingAll(timeout="1")
    print("Packet loss:", lost_packets, "%")


def main():


    #add switch
    network = Mininet(
        topo=SingleSwitchTopo(k=3),
        switch=switch_type,
        controller=None,
        autoSetMacs=True
    )

    network.start()

    switch = network.get("s1")
    host1 = network.get("h1")
    host2 = network.get("h2")
    host3 = network.get("h3")

    print("Switch setting:", switch_setting)

    #check pre-rules
    show_flows(switch, "Flow table before rules")
    test_all_pings(network, "Ping test before rules")

    #Implement ARP for resloving IPs
    switch.cmd("ovs-ofctl add-flow s1 priority=100,arp,actions=flood")

    #Send IP traffic to the port connected to its dst host
    #h1  uses port=1, h2 uses port=2, h3 uses port=3

    switch.cmd(
        "ovs-ofctl add-flow s1 priority=100,ip,nw_dst=10.0.0.1,actions=output:1"
    )

    switch.cmd(
        "ovs-ofctl add-flow s1 priority=100,ip,nw_dst=10.0.0.2,actions=output:2"
    )

    switch.cmd(
        "ovs-ofctl add-flow s1 priority=100,ip,nw_dst=10.0.0.3,actions=output:3"
    )

    #Test the forwarding rules
    test_all_pings(network, "Ping test after forwarding rules")
    show_flows(switch, "Flow table after forwarding rules")

    #Block traffic from h3 to h1
    #priority=200 is higher than the forwarding rules priority=100
    switch.cmd(
        "ovs-ofctl add-flow s1 priority=200,ip,"
        "nw_src=10.0.0.3,nw_dst=10.0.0.1,actions=drop"
    )

    #Test  blocked connection and a successful connection
    print("\n--- Testing the blocking rule ---")

    blocked_result = host3.cmd("ping -c 2 -W 1 10.0.0.1")
    working_result = host2.cmd("ping -c 2 -W 1 10.0.0.1")

    print("Host 3 to Host 1 (should be blocked):")
    for line in blocked_result.splitlines():
        if "packet loss" in line:
            print(line)

    print("Host 2 to Host 1 (should work):")
    for line in working_result.splitlines():
        if "packet loss" in line:
            print(line)

    #display rules
    show_flows(switch, "Final flow table")

    network.stop()


if __name__ == "__main__":
    setLogLevel("warning")
    main()