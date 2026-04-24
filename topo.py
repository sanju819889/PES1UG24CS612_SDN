from mininet.topo import Topo

class MyTopo(Topo):
    def build(self):
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')

        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')  # NEW SWITCH

        # host connections
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s2)

        # multiple paths
        self.addLink(s1, s2)
        self.addLink(s1, s3)
        self.addLink(s3, s2)

topos = {'mytopo': MyTopo}
