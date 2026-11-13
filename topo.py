#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

def run():
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink,
                  autoSetMacs=True, autoStaticArp=True)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    h1 = net.addHost('h1', ip='10.0.0.1/24')   # publisher
    h2 = net.addHost('h2', ip='10.0.0.2/24')   # broker
    h3 = net.addHost('h3', ip='10.0.0.3/24')   # subscriber
    h4 = net.addHost('h4', ip='10.0.0.4/24')   # subscriber
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    s2 = net.addSwitch('s2', protocols='OpenFlow13')
    s3 = net.addSwitch('s3', protocols='OpenFlow13')
    # Link ORDER decides port numbers; the controller depends on it:
    net.addLink(h1, s1)                  # s1 port 1
    net.addLink(h3, s1)                  # s1 port 2
    net.addLink(h4, s1)                  # s1 port 3
    net.addLink(h2, s3)                  # s3 port 1
    net.addLink(s1, s3, delay='5ms')     # s1 port 4 <-> s3 port 2  (primary)
    net.addLink(s1, s2, delay='10ms')    # s1 port 5 <-> s2 port 1  (alternate)
    net.addLink(s2, s3, delay='10ms')    # s2 port 2 <-> s3 port 3  (alternate)
    net.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
