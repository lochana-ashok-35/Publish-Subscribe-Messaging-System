import json
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub

TOPIC_PORTS = {"sports": 5001, "weather": 5002, "news": 5003}
CONFIG_FILE = "/tmp/topic_paths.json"
# base routing by destination IP (primary path): switch -> {ip: out_port}
BASE = {
    1: {"10.0.0.1": 1, "10.0.0.3": 2, "10.0.0.4": 3, "10.0.0.2": 4},
    2: {"10.0.0.1": 1, "10.0.0.3": 1, "10.0.0.4": 1, "10.0.0.2": 2},
    3: {"10.0.0.2": 1, "10.0.0.1": 2, "10.0.0.3": 2, "10.0.0.4": 2},
}

def topic_out(dpid, path):
    """(forward_out_port, reverse_out_port) for a topic, or None if switch unused."""
    if dpid == 1: return (4 if path == "primary" else 5, 1)
    if dpid == 3: return (1, 2 if path == "primary" else 3)
    if dpid == 2: return (2, 1) if path == "alt" else None

class TopicSDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.dps = {}
        self.paths = {t: "primary" for t in TOPIC_PORTS}
        hub.spawn(self._watch)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch(self, ev):
        dp = ev.msg.datapath
        if dp.id not in BASE: return
        self.dps[dp.id] = dp
        p = dp.ofproto_parser
        for ip, port in BASE[dp.id].items():
            self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0800, ipv4_dst=ip), port)
        self.apply_topics(dp)
        self.logger.info("switch s%d configured", dp.id)

    def add_flow(self, dp, prio, match, out_port):
        p, o = dp.ofproto_parser, dp.ofproto
        inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, [p.OFPActionOutput(out_port)])]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=prio, match=match, instructions=inst))

    def del_flow(self, dp, match):
        p, o = dp.ofproto_parser, dp.ofproto
        dp.send_msg(p.OFPFlowMod(datapath=dp, command=o.OFPFC_DELETE, out_port=o.OFPP_ANY,
                                 out_group=o.OFPG_ANY, match=match))

    def apply_topics(self, dp):
        p = dp.ofproto_parser
        for topic, port in TOPIC_PORTS.items():
            res = topic_out(dp.id, self.paths[topic])
            fwd = p.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=port)
            rev = p.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=port)
            if res is None:
                self.del_flow(dp, fwd); self.del_flow(dp, rev)
            else:
                self.add_flow(dp, 100, fwd, res[0]); self.add_flow(dp, 100, rev, res[1])

    def _watch(self):
        while True:
            hub.sleep(2)
            try:
                with open(CONFIG_FILE) as f: cfg = json.load(f)
            except Exception:
                continue
            changed = False
            for t, path in cfg.items():
                if t in self.paths and path in ("primary", "alt") and self.paths[t] != path:
                    self.paths[t] = path; changed = True
                    self.logger.info("TOPIC %s -> %s path", t, path)
            if changed:
                for dp in self.dps.values(): self.apply_topics(dp)
