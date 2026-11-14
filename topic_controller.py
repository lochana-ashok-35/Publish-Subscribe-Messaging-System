import json, time
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub

TOPIC_PORTS = {"sports": 5001, "weather": 5002, "news": 5003}
REQUEST_FILE = "/tmp/topic_paths.json"   # manual or broker reroute requests
MODE_FILE = "/tmp/sdn_mode"              # static | dynamic | app
EVENT_LOG = "/tmp/sdn_events.log"
LINK_BW_MBPS = 10.0
HIGH_UTIL, LOW_UTIL = 0.70, 0.30
POLL = 1.0
WATCHED = {(1, 4), (3, 2)}               # the two ends of the primary link s1-s3

ROUTES = {   # default routing by destination IP: path -> switch -> {ip: out_port}
    "primary": {
        1: {"10.0.0.1": 1, "10.0.0.3": 2, "10.0.0.4": 3, "10.0.0.2": 4},
        2: {"10.0.0.1": 1, "10.0.0.3": 1, "10.0.0.4": 1, "10.0.0.2": 2},
        3: {"10.0.0.2": 1, "10.0.0.1": 2, "10.0.0.3": 2, "10.0.0.4": 2},
    },
    "alt": {
        1: {"10.0.0.1": 1, "10.0.0.3": 2, "10.0.0.4": 3, "10.0.0.2": 5},
        2: {"10.0.0.1": 1, "10.0.0.3": 1, "10.0.0.4": 1, "10.0.0.2": 2},
        3: {"10.0.0.2": 1, "10.0.0.1": 3, "10.0.0.3": 3, "10.0.0.4": 3},
    },
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
        self.mode = "dynamic"
        self.requests = {}
        self.down_ports = set()
        self.congested = False
        self.util = 0.0
        self.last_tx = None
        self.eff = ("primary", {t: "primary" for t in TOPIC_PORTS})
        self.applied = {}
        hub.spawn(self._watch_files)
        hub.spawn(self._poll_stats)

    def event(self, msg):
        self.logger.info("[%s] %s", time.strftime("%H:%M:%S"), msg)
        try:
            with open(EVENT_LOG, "a") as f: f.write("%.3f %s\n" % (time.time(), msg))
        except OSError:
            pass

    # ---------- decision logic ----------
    def desired(self):
        if self.mode == "static":
            return "primary", {t: "primary" for t in TOPIC_PORTS}
        down = bool(self.down_ports)
        cong = self.congested and self.mode == "dynamic"
        topics = {t: ("alt" if (down or cong or self.requests.get(t) == "alt") else "primary")
                  for t in TOPIC_PORTS}
        return ("alt" if down else "primary"), topics

    def recompute(self):
        new = self.desired()
        if new != self.eff:
            old, self.eff = self.eff, new
            if new[0] != old[0]:
                self.event("default traffic -> %s path" % new[0])
            for t in TOPIC_PORTS:
                if new[1][t] != old[1][t]:
                    self.event("TOPIC %s -> %s path" % (t, new[1][t]))
        for dp in self.dps.values():
            if self.applied.get(dp.id) != self.eff:
                self.apply(dp)
                self.applied[dp.id] = self.eff

    # ---------- flow installation ----------
    def apply(self, dp):
        p = dp.ofproto_parser
        default, topics = self.eff
        for ip, port in ROUTES[default][dp.id].items():
            self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0800, ipv4_dst=ip), port)
        for topic, tport in TOPIC_PORTS.items():
            res = topic_out(dp.id, topics[topic])
            fwd = p.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=tport)
            rev = p.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=tport)
            if res is None:
                self.del_flow(dp, fwd); self.del_flow(dp, rev)
            else:
                self.add_flow(dp, 100, fwd, res[0]); self.add_flow(dp, 100, rev, res[1])

    def add_flow(self, dp, prio, match, out_port):
        p, o = dp.ofproto_parser, dp.ofproto
        inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, [p.OFPActionOutput(out_port)])]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=prio, match=match, instructions=inst))

    def del_flow(self, dp, match):
        p, o = dp.ofproto_parser, dp.ofproto
        dp.send_msg(p.OFPFlowMod(datapath=dp, command=o.OFPFC_DELETE, out_port=o.OFPP_ANY,
                                 out_group=o.OFPG_ANY, match=match))

    # ---------- switch events ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch(self, ev):
        dp = ev.msg.datapath
        if dp.id not in ROUTES["primary"]: return
        self.dps[dp.id] = dp
        self.applied.pop(dp.id, None)
        self.recompute()
        self.event("switch s%d configured" % dp.id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def on_port(self, ev):
        msg = ev.msg; dp = msg.datapath; o = dp.ofproto
        key = (dp.id, msg.desc.port_no)
        if key not in WATCHED: return
        down = bool(msg.desc.state & o.OFPPS_LINK_DOWN) or bool(msg.desc.config & o.OFPPC_PORT_DOWN)
        if down and key not in self.down_ports:
            self.down_ports.add(key)
            self.event("LINK FAILURE detected on s%d port %d" % key)
        elif not down and key in self.down_ports:
            self.down_ports.discard(key)
            self.event("link restored on s%d port %d" % key)
        self.recompute()

    # ---------- congestion monitoring ----------
    def _poll_stats(self):
        while True:
            hub.sleep(POLL)
            dp = self.dps.get(1)
            if dp:
                p, o = dp.ofproto_parser, dp.ofproto
                dp.send_msg(p.OFPPortStatsRequest(dp, 0, o.OFPP_ANY))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def on_stats(self, ev):
        if ev.msg.datapath.id != 1: return
        for st in ev.msg.body:
            if st.port_no != 4: continue
            now = time.time()
            if self.last_tx is not None:
                dt = now - self.last_tx[0]
                if dt > 0:
                    mbps = (st.tx_bytes - self.last_tx[1]) * 8 / dt / 1e6
                    self.util = mbps / LINK_BW_MBPS
                    self.update_congestion()
            self.last_tx = (now, st.tx_bytes)

    def update_congestion(self):
        if not self.congested and self.util > HIGH_UTIL:
            self.congested = True
            self.event("CONGESTION on s1-s3 link (%.0f%% utilised)" % (self.util * 100))
            self.recompute()
        elif self.congested and self.util < LOW_UTIL:
            self.congested = False
            self.event("congestion cleared (%.0f%% utilised)" % (self.util * 100))
            self.recompute()

    # ---------- config files ----------
    def _watch_files(self):
        while True:
            hub.sleep(1)
            try:
                with open(MODE_FILE) as f: mode = f.read().strip()
            except Exception:
                mode = "dynamic"
            if mode not in ("static", "dynamic", "app"): mode = "dynamic"
            if mode != self.mode:
                self.mode = mode
                self.event("MODE -> %s" % mode)
            try:
                with open(REQUEST_FILE) as f: cfg = json.load(f)
                if isinstance(cfg, dict): self.requests = cfg
            except FileNotFoundError:
                self.requests = {}
            except Exception:
                pass
            self.recompute()
