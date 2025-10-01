#!/usr/bin/env python3
import argparse, os, signal, sys, time, tempfile, subprocess
from pathlib import Path

# --- Paste your CELLULAR_TRACES_90S dict here ---
# CELLULAR_TRACES_90S = { 'good': {...}, 'median': {...}, 'poor': {...}, 'noloss': {...} }

CELLULAR_TRACES_90S = {
    'good': {
        'gaps': [0.07, 0.63, 1.54, 3.36, 0.56, 1.19, 2.94, 0.315, 1.19, 2.1, 0.28, 1.12, 2.03, 0.21, 0.91, 1.96, 5.425, 1.05, 1.855, 0.175, 0.77, 1.785, 4.2, 0.98, 1.68, 0.07, 0.98, 1.61, 0.07, 0.63, 1.54, 3.36, 0.56, 1.19, 2.94, 0.49, 1.4, 2.8, 0.455, 1.12, 2.59, 0.42, 1.085, 2.38, 0.175, 1.05, 1.855, 0.14, 0.77, 1.785, 4.2, 0.735, 1.365, 3.885, 0.63, 1.61, 0.07, 0.63, 1.54, 3.22, 0.56, 1.19, 0.575000000000017],
        'loss': [0.703122, 7.1429, 50.0, 60.0, 5.8824, 33.3333, 50.0, 2.5641, 33.3333, 50.0, 2.381, 26.6667, 50.0, 1.8519, 14.2857, 50.0, 75.0, 25.0, 50.0, 1.4085, 11.1111, 50.0, 66.6667, 16.6667, 50.0, 0.9174, 16.6667, 50.0, 0.5556, 7.1429, 50.0, 60.0, 5.8824, 33.3333, 50.0, 5.2632, 50.0, 50.0, 4.5455, 26.6667, 50.0, 3.8462, 25.0, 50.0, 1.5385, 25.0, 50.0, 1.2821, 11.1111, 50.0, 66.6667, 9.0909, 50.0, 66.6667, 7.6923, 50.0, 0.5556, 7.1429, 50.0, 50.0, 5.8824, 33.3333, 50.0]
    },
    'median': {
        'gaps': [0.07, 0.245, 0.49, 0.98, 0.21, 0.385, 0.91, 0.14, 0.375, 0.63, 0.105, 0.35, 0.595, 0.07, 0.28, 0.56, 3.5, 0.35, 0.56, 0.07, 0.28, 0.525, 1.89, 0.315, 0.49, 0.07, 0.29, 0.49, 0.07, 0.245, 0.49, 0.98, 0.21, 0.385, 0.91, 0.21, 0.42, 0.84, 0.21, 0.35, 0.805, 0.175, 0.35, 0.7, 0.07, 0.35, 0.56, 0.07, 0.28, 0.525, 1.89, 0.28, 0.42, 1.19, 0.28, 0.49, 0.07, 0.245, 0.49, 0.945, 0.21, 0.385, 0.91, 0.14, 0.35, 0.63, 0.07, 0.315, 0.595, 0.07, 0.28, 0.56, 3.5, 0.35, 0.56, 0.07, 0.28, 0.525, 1.61, 0.28, 0.42, 1.19, 0.175, 0.42, 0.735, 0.14, 0.385, 0.7, 0.14, 0.315, 0.665, 0.07, 0.35, 0.63, 0.07, 0.29, 0.595, 0.07, 0.28, 0.49, 0.21, 0.385, 0.945, 0.14, 0.375, 0.64, 0.105, 0.315, 0.63, 0.07, 0.35, 0.56, 0.07, 0.28, 0.56, 0.07, 0.28, 0.525, 1.89, 0.28, 0.42, 1.4, 0.175, 0.42, 0.77, 0.175, 0.35, 0.735, 0.07, 0.385, 0.91, 0.14, 0.375, 0.64, 0.105, 0.315, 0.595, 0.07, 0.28, 0.49, 0.07, 0.21, 0.455, 0.945, 0.21, 0.455, 0.91, 0.28, 0.42, 1.4, 0.175, 0.42, 0.77, 0.175, 0.35, 0.7, 0.07, 0.315, 0.56, 0.07, 0.315, 0.49, 0.07, 0.28, 0.49, 1.05, 0.28, 0.49, 0.07, 0.21, 0.455, 0.945, 0.21, 0.375, 0.91, 0.21, 0.35, 0.84, 0.07, 0.35, 0.572, 0.07, 0.28, 0.56, 2.59, 0.315, 0.14300000000010016],
        'loss': [0.9434, 16.6667, 50.0, 66.6667, 14.2857, 50.0, 66.6667, 4.7619, 50.0, 60.0, 4.3478, 44.23392, 55.5556, 3.125, 25.0, 50.0, 80.0, 33.3333, 50.0, 2.2727, 25.0, 50.0, 75.0, 28.5714, 50.0, 1.3514, 27.2727, 50.0, 0.7042, 16.6667, 50.0, 66.6667, 14.2857, 50.0, 66.6667, 11.7647, 50.0, 66.6667, 10.0, 44.23392, 66.6667, 7.6923, 33.3333, 66.6667, 2.5, 33.3333, 50.0, 2.0408, 25.0, 50.0, 75.0, 20.0, 50.0, 66.6667, 16.6667, 50.0, 0.7042, 16.6667, 50.0, 66.6667, 14.2857, 50.0, 66.6667, 4.7619, 50.0, 57.1429, 4.0, 28.5714, 55.5556, 0.9434, 25.0, 50.0, 80.0, 33.3333, 50.0, 2.0408, 25.0, 50.0, 71.4286, 20.0, 50.0, 66.6667, 9.0909, 50.0, 66.6667, 6.6667, 50.0, 66.6667, 5.8824, 33.3333, 62.5, 1.8182, 50.0, 57.1429, 4.0, 27.2727, 55.5556, 0.9434, 25.0, 50.0, 14.2857, 50.0, 66.6667, 4.7619, 50.0, 60.0, 4.3478, 33.3333, 57.1429, 1.1364, 33.3333, 50.0, 2.8571, 25.0, 50.0, 2.2727, 25.0, 50.0, 75.0, 20.0, 50.0, 66.6667, 9.0909, 50.0, 66.6667, 7.6923, 33.3333, 66.6667, 2.5, 50.0, 66.6667, 4.7619, 50.0, 60.0, 4.3478, 28.5714, 55.5556, 1.1364, 25.0, 50.0, 0.7042, 16.6667, 50.0, 66.6667, 12.5, 50.0, 66.6667, 20.0, 50.0, 66.6667, 9.0909, 50.0, 66.6667, 7.6923, 33.3333, 66.6667, 2.5, 33.3333, 50.0, 2.0408, 33.3333, 50.0, 1.3514, 20.0, 50.0, 66.6667, 25.0, 50.0, 0.7042, 16.6667, 50.0, 66.6667, 12.5, 50.0, 66.6667, 11.1111, 50.0, 66.6667, 4.0, 40.0, 50.0, 2.8571, 25.0, 50.0, 75.0, 33.3333, 50.0]
    },
    'poor': {
        'gaps': [0.07, 0.28, 0.49, 1.82, 0.21, 0.42, 1.33, 0.21, 0.42, 0.77, 0.14, 0.35, 0.7, 0.14, 0.28, 0.7, 6.9167, 0.35, 0.63, 0.14, 0.28, 0.63, 3.22, 0.28, 0.56, 0.07, 0.28, 0.56, 0.07, 0.28, 0.49, 1.82, 0.21, 0.42, 1.33, 0.21, 0.49, 1.26, 0.21, 0.35, 1.12, 0.21, 0.35, 0.98, 0.14, 0.35, 0.63, 0.14, 0.28, 0.63, 3.22, 0.28, 0.42, 2.3569, 0.28, 0.56, 0.07, 0.28, 0.49, 1.6737, 0.21, 0.42, 1.33, 0.21, 0.42, 0.77, 0.14, 0.28, 0.7, 0.07, 0.28, 0.7, 6.9167, 0.35, 0.63, 0.14, 0.28, 0.63, 2.87, 0.28, 0.42, 2.3569, 0.21, 0.42, 0.98, 0.21, 0.42, 0.98, 0.21, 0.35, 0.84, 0.14, 0.42, 0.77, 0.14, 0.28, 0.7, 0.07, 0.28, 0.5332, 0.21, 0.42, 1.6737, 0.21, 0.42, 0.84, 0.14, 0.35, 0.77, 0.07, 0.35, 0.7, 0.14, 0.28, 0.63, 0.14, 0.28, 0.63, 3.22, 0.28, 0.49, 2.5802, 0.21, 0.42, 1.05, 0.21, 0.35, 0.7320000000000277],
        'loss': [3.4483, 25.0, 50.0, 83.3333, 20.0, 50.0, 81.51371, 12.5, 50.0, 71.4286, 12.5, 50.0, 66.6667, 9.208416, 33.3333, 66.6667, 85.7143, 50.0, 66.6667, 7.6923, 33.3333, 66.6667, 83.3333, 33.3333, 66.6667, 4.709964, 33.3333, 59.33332, 2.735744, 25.0, 50.0, 83.3333, 20.0, 50.0, 81.51371, 20.0, 50.0, 80.0, 16.6667, 50.0, 80.0, 16.6667, 50.0, 75.0, 8.3333, 50.0, 66.6667, 6.704796, 33.3333, 66.6667, 83.3333, 25.0, 50.0, 83.3333, 25.0, 59.33332, 2.735744, 25.0, 50.0, 83.3333, 20.0, 50.0, 81.51371, 12.5, 50.0, 71.4286, 11.1111, 33.3333, 66.6667, 3.4483, 33.3333, 66.6667, 85.7143, 50.0, 66.6667, 6.704796, 33.3333, 66.6667, 83.3333, 25.0, 50.0, 83.3333, 16.6667, 50.0, 75.0, 14.2857, 50.0, 75.0, 14.2857, 33.3333, 75.0, 6.117664, 50.0, 71.4286, 11.1111, 33.3333, 66.6667, 3.4483, 33.3333, 50.0, 20.0, 50.0, 83.3333, 12.5, 50.0, 75.0, 12.5, 33.3333, 71.4286, 4.287916, 50.0, 66.6667, 9.0909, 33.3333, 66.6667, 7.6923, 33.3333, 66.6667, 83.3333, 25.0, 50.0, 83.3333, 16.6667, 50.0, 80.0, 16.6667, 50.0, 75.0]
    },
    'noloss': { 'gaps': [1e9], 'loss': [0.0] },
}



DNCTL = "dnctl"   # rely on PATH (/sbin on macOS)
PFCTL = "pfctl"

def sh(cmd, check=True):
    # prints the exact command line for easy debugging
    print("running:", " ".join(cmd))
    return subprocess.run(cmd, text=True, check=check)

# --- add this helper somewhere near the class ---
def _install_anchor_hooks(anchor_name: str):
    """Load main ruleset with our anchor hooks appended (does NOT delete system rules)."""
    import tempfile, pathlib
    base = pathlib.Path("/etc/pf.conf").read_text()
    hook = f'\ndummynet-anchor "{anchor_name}"\nanchor "{anchor_name}"\n'
    with tempfile.NamedTemporaryFile('w', delete=False) as t:
        t.write(base + hook)
        tmp = t.name
    try:
        sh(["sudo", PFCTL, "-f", tmp])   # reload main ruleset + our hooks
    finally:
        os.unlink(tmp)


class DynShaper:
    """
    Manages two dummynet pipes + a PF anchor.
    We keep delay/bw fixed; only plr is changed during a trace.
    """
    def __init__(self, iface="en0", target="any", rtt_ms=100, bw_kbps=None, max_bw_kbps=None,
                 up_pipe=900, down_pipe=901, anchor="com.cell.trace"):
        self.iface = iface
        self.target = target
        self.rtt_ms = int(rtt_ms)
        self.half = max(0, self.rtt_ms // 2)
        self.bw_kbps = bw_kbps
        self.max_bw_kbps = max_bw_kbps
        self.up_pipe = int(up_pipe)
        self.down_pipe = int(down_pipe)
        self.anchor = anchor
        self.pf_file = None
        self.enabled = False

    def _pipe_args(self, pipe_id, plr=None):
        args = ["sudo", DNCTL, "pipe", str(pipe_id), "config"]
        # Use max_bw_kbps if set (hard cap), otherwise use bw_kbps
        bandwidth = self.max_bw_kbps or self.bw_kbps
        if bandwidth:
            args += ["bw", f"{bandwidth}Kbit/s"]
        args += ["delay", f"{self.half}ms"]
        if plr is not None:
            args += ["plr", f"{plr:.6f}"]
        return args

    def setup(self):
        # pipes at 0 loss
        sh(self._pipe_args(self.up_pipe, plr=0.0))
        sh(self._pipe_args(self.down_pipe, plr=0.0))

        # ensure the main ruleset references our anchor
        _install_anchor_hooks(self.anchor)
        
        def rule(direction, family, target_expr, pipe_id):
            base = f"dummynet {direction} quick on {self.iface} {family}"
            return f"{base} {target_expr} pipe {pipe_id}"
        
            #base = f"pass {direction} quick on {self.iface} {family}"
            #return f"{base} {target_expr} dummynet (pipe {pipe_id})"

        if self.target == "any":
            in4  = "from any to any"
            out4 = "from any to any"
            in6  = "from any to any"
            out6 = "from any to any"
        else:
            # Your target is IPv4-only (e.g. 192.168.2.0/24).
            in4  = f"from {self.target} to any"
            out4 = f"from any to {self.target}"
            # For IPv6 on the same LAN, either shape all v6 on bridge100:
            in6  = "from any to any"
            out6 = "from any to any"

        rules = [
            "no dummynet quick on lo0 all",
            rule("in",  "inet",  in4,  self.up_pipe),
            rule("out", "inet",  out4, self.down_pipe),
            rule("in",  "inet6", in6,  self.up_pipe),
            rule("out", "inet6", out6, self.down_pipe),
        ]

        
        '''
        
        # PF rules in our private anchor No proto filter → hits UDP/TCP/ICMP.
        def rule(direction, target_expr, pipe_id):
            # base = f"dummynet {direction} quick on {self.iface} inet"
            base = f"dummynet {direction} quick on {self.iface}" #for both ipv4 and ipv6
            return f"{base} {target_expr} pipe {pipe_id}"

        if self.target == "any":
            in_expr  = "from any to any"
            out_expr = "from any to any"
        else:
            in_expr  = f"from {self.target} to any"
            out_expr = f"from any to {self.target}"

        rules = [
            "no dummynet quick on lo0 all",
            rule("in",  in_expr,  self.up_pipe),
            rule("out", out_expr, self.down_pipe),
        ]
        '''
        fd, pf_path = tempfile.mkstemp(prefix="pf_anchor_", suffix=".conf")
        os.close(fd)
        Path(pf_path).write_text("\n".join(rules) + "\n")
        self.pf_file = pf_path

        # Load ONLY our anchor; do NOT reload main ruleset.
        sh(["sudo", PFCTL, "-a", self.anchor, "-f", self.pf_file])

        # Enable PF; ignore "pf already enabled"
        sh(["sudo", PFCTL, "-e"], check=False)

        self.enabled = True
        bw_str = f"{self.max_bw_kbps}Kbit/s (HARD CAP)" if self.max_bw_kbps else (f"{self.bw_kbps}Kbit/s" if self.bw_kbps else "∞")
        print("pipes+PF ready:",
            f"RTT={self.rtt_ms}ms (half={self.half}ms), BW={bw_str}, target={self.target}")


    def update_loss_both(self, loss_percent):
        """Set identical PLR on both directions (percent → probability)."""
        plr = max(0.0, float(loss_percent) / 100.0)
        sh(["sudo", DNCTL, "pipe", str(self.up_pipe),   "config", "plr", f"{plr:.6f}"])
        sh(["sudo", DNCTL, "pipe", str(self.down_pipe), "config", "plr", f"{plr:.6f}"])

    def teardown(self):
        if self.enabled:
            try:
                self.update_loss_both(0.0)
            except Exception:
                pass
            try:
                sh(["sudo", PFCTL, "-a", self.anchor, "-F", "rules"], check=False)
            finally:
                if self.pf_file and os.path.exists(self.pf_file):
                    os.unlink(self.pf_file)
        self.enabled = False
        print("cleaned up (anchor flushed, loss=0)")


def find_latest_experiment_folder(exp_folder_hint=None):
    """Find the latest experiment folder, optionally matching a hint."""
    import glob
    import os
    
    if exp_folder_hint:
        # If full path provided, use it directly
        if os.path.isabs(exp_folder_hint):
            if os.path.exists(exp_folder_hint):
                return exp_folder_hint
        else:
            # Look for specific folder pattern
            patterns = [
                f"experiments/*{exp_folder_hint}*",
                f"{exp_folder_hint}/*gcc_*",
                exp_folder_hint  # Direct path
            ]
            for pattern in patterns:
                matches = glob.glob(pattern)
                if matches:
                    return max(matches, key=os.path.getctime)
    
    # Find latest experiment folder
    pattern = "experiments/gcc_*"
    matches = glob.glob(pattern)
    if matches:
        return max(matches, key=os.path.getctime)
    
    return None

def play_trace(shaper: DynShaper, profile: str,
               baseline_s=0.0, duration_s=90.0,
               pulse_s=0.03, exp_folder=None):  # kept param for compatibility; ignored
    if profile not in CELLULAR_TRACES_90S:
        raise ValueError(f"Unknown profile '{profile}'")

    # Find experiment folder for logging
    import json
    import os
    
    experiment_folder = find_latest_experiment_folder(exp_folder)
    if experiment_folder:
        timing_log_path = os.path.join(experiment_folder, "logs", "packet_loss_timing.log")
        loss_config_path = os.path.join(experiment_folder, "logs", "loss_config.json")
        os.makedirs(os.path.dirname(timing_log_path), exist_ok=True)
        print(f"Linking loss logs to experiment: {experiment_folder}")
    else:
        timing_log_path = "/tmp/packet_loss_timing.log"
        loss_config_path = "/tmp/loss_config.json"
        print("No experiment folder found, using /tmp/ for logs")
    
    # Save loss configuration
    loss_config = {
        'profile': profile,
        'rtt_ms': shaper.rtt_ms if hasattr(shaper, 'rtt_ms') else 0,
        'baseline_s': baseline_s,
        'duration_s': duration_s,
        'timestamp_start': time.time()
    }
    with open(loss_config_path, "w") as f:
        json.dump(loss_config, f, indent=2)
    
    # Start clean
    shaper.update_loss_both(0.0)
    
    # Log baseline start
    baseline_start = time.time()
    with open(timing_log_path, "w") as f:
        f.write(f"baseline_start: {json.dumps({'timestamp_ms': int(baseline_start * 1000), 'duration_s': baseline_s})}\n")
    
    if baseline_s > 0:
        print(f"baseline 0% loss for {baseline_s}s")
        time.sleep(baseline_s)

    trace = CELLULAR_TRACES_90S[profile]
    gaps   = list(trace.get("gaps", []))
    losses = list(trace.get("loss", []))

    # Log loss period start
    loss_start = time.time()
    with open(timing_log_path, "a") as f:
        f.write(f"loss_start: {json.dumps({'timestamp_ms': int(loss_start * 1000), 'profile': profile, 'duration_s': duration_s})}\n")

    print(f"playing '{profile}' trace as steps: {len(gaps)} segments")
    start = time.monotonic()
    elapsed = 0.0

    for i, (gap, loss) in enumerate(zip(gaps, losses)):
        if elapsed >= duration_s:
            break
        hold = min(float(gap), max(0.0, duration_s - elapsed))
        
        # Log each loss segment
        segment_start = time.time()
        with open(timing_log_path, "a") as f:
            f.write(f"loss_segment: {json.dumps({'segment': i, 'timestamp_ms': int(segment_start * 1000), 'loss_percent': loss, 'duration_s': hold})}\n")
        
        print(f"hold {loss:.4g}% loss for {hold:.3f}s (t={elapsed:.2f}s)")
        shaper.update_loss_both(loss)
        time.sleep(hold)
        elapsed = time.monotonic() - start

    # Log loss period end
    loss_end = time.time()
    with open(timing_log_path, "a") as f:
        f.write(f"loss_end: {json.dumps({'timestamp_ms': int(loss_end * 1000), 'total_duration_s': elapsed})}\n")

    # Automatic recovery - clear all loss
    shaper.update_loss_both(0.0)
    print("Loss cleared - automatic recovery")
    
    print(f"Timing log saved to: {timing_log_path}")


def main():
    p = argparse.ArgumentParser(description="macOS dummynet loss RTT emulator")
    sub = p.add_subparsers(dest="cmd", required=True)

    # run subcommand
    pr = sub.add_parser("run")
    pr.add_argument("--iface", default="en0")
    pr.add_argument("--target", default="any", help='"any" or an IP/CIDR/hostname')
    pr.add_argument("--rtt", type=int, required=True, help="end-to-end RTT in ms (half each way)")
    pr.add_argument("--bw", type=int, default=None, help="bandwidth Kbit/s (optional)")
    pr.add_argument("--max-bw", type=int, default=None, help="maximum bandwidth cap in Kbit/s (hard limit)")
    pr.add_argument("--profile", choices=("noloss", "good", "median", "poor"), required=True)
    pr.add_argument("--baseline", type=float, default=0.0)
    pr.add_argument("--duration", type=float, default=90.0)
    pr.add_argument("--pulse-ms", type=float, default=30.0, help="length of each loss pulse (ms)")
    pr.add_argument("--up-pipe", type=int, default=900)
    pr.add_argument("--down-pipe", type=int, default=901)
    pr.add_argument("--anchor", default="com.cell.trace")
    pr.add_argument("--exp-folder", type=str, default=None, help="Link loss log to specific experiment folder")

    # clear subcommand
    pc = sub.add_parser("clear")
    pc.add_argument("--anchor", default="com.cell.trace")
    pc.add_argument("--up-pipe", type=int, default=900)
    pc.add_argument("--down-pipe", type=int, default=901)
    pc.add_argument("--flush", action="store_true", help="also dnctl flush")

    args = p.parse_args()

    # keep sudo alive
    sh(["sudo", "-v"])

    if args.cmd == "clear":
        for pipe in (args.up_pipe, args.down_pipe):
            try: sh(["sudo","dnctl","pipe",str(pipe),"config","plr","0"], check=False)
            except: pass
        sh(["sudo","pfctl","-a",args.anchor,"-F","rules"], check=False)
        if args.flush:
            sh(["sudo","dnctl","-q","flush"], check=False)
        print("cleared")
        return

    # run
    shaper = DynShaper(
        iface=args.iface, target=args.target,
        rtt_ms=args.rtt, bw_kbps=args.bw, max_bw_kbps=getattr(args, 'max_bw', None),
        up_pipe=args.up_pipe, down_pipe=args.down_pipe,
        anchor=args.anchor,
    )

    def _cleanup(signum=None, frame=None):
        try:
            shaper.teardown()
        finally:
            sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _cleanup)

    try:
        shaper.setup()
        play_trace(
            shaper,
            profile=args.profile,
            baseline_s=args.baseline,
            duration_s=args.duration,
            pulse_s=max(0.001, args.pulse_ms/1000.0),
            exp_folder=args.exp_folder,
        )
    finally:
        shaper.teardown()


if __name__ == "__main__":
    main()
