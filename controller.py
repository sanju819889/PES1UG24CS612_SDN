from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet
from ryu.topology import event
from ryu.topology.api import get_link
import networkx as nx


class PathTracker(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PathTracker, self).__init__(*args, **kwargs)
        self.net = nx.DiGraph()   # full graph: switches + hosts
        self.hosts = {}           # mac -> (dpid, port)

    # -----------------------------
    # Table-miss flow (send to controller)
    # -----------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                         ofp.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]

        dp.send_msg(parser.OFPFlowMod(datapath=dp,
                                     priority=0,
                                     match=match,
                                     instructions=inst))

    # -----------------------------
    # Topology discovery (switch graph)
    # -----------------------------
    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        links = get_link(self)

        # rebuild switch graph
        self.net.clear()
        for link in links:
            self.net.add_edge(link.src.dpid,
                              link.dst.dpid,
                              port=link.src.port_no)

        print("\n[TOPOLOGY UPDATED]")
        print(list(self.net.edges(data=True)))

    # -----------------------------
    # Packet handling (PATH BASED)
    # -----------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        dpid = dp.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        dst = eth.dst
        src = eth.src
        in_port = msg.match['in_port']

        # ignore LLDP / multicast
        if dst.startswith("33:33") or dst.startswith("01:80:c2"):
            return

        print(f"[PACKET] {src} -> {dst} at s{dpid}")

        # -----------------------------
        # LEARN SOURCE HOST (ADD TO GRAPH)
        # -----------------------------
        if src not in self.hosts:
            self.hosts[src] = (dpid, in_port)

            self.net.add_node(src)
            self.net.add_edge(dpid, src, port=in_port)
            self.net.add_edge(src, dpid)

        # -----------------------------
        # PATH COMPUTATION
        # -----------------------------
        if dst in self.hosts:
            try:
                path = nx.shortest_path(self.net, dpid, dst)
                print(f"[PATH] {path}")

                next_hop = path[1]

                if isinstance(next_hop, str):
                    # next hop is host
                    out_port = self.net[dpid][next_hop]['port']
                else:
                    # next hop is switch
                    out_port = self.net[dpid][next_hop]['port']

            except:
                out_port = ofp.OFPP_FLOOD
        else:
            out_port = ofp.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # -----------------------------
        # INSTALL FLOW
        # -----------------------------
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)

            dp.send_msg(parser.OFPFlowMod(
                datapath=dp,
                priority=1,
                match=match,
                instructions=[parser.OFPInstructionActions(
                    ofp.OFPIT_APPLY_ACTIONS, actions)]
            ))

        # -----------------------------
        # SEND PACKET
        # -----------------------------
        dp.send_msg(parser.OFPPacketOut(
            datapath=dp,
            buffer_id=ofp.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=msg.data
        ))
