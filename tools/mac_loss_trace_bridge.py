#!/usr/bin/env python3
"""
Enhanced network condition script that works with bridge filtering.
Maintains fixed RTT while allowing dynamic packet loss changes.
"""

import argparse
import subprocess
import time
import os
import sys
import signal
from pathlib import Path

from trace import TRACES


DNCTL = "dnctl"

class BridgeShaper:
    def __init__(self, rtt_ms=0, bw_kbps=None, stabilize_s=0.0):
        self.rtt_ms = rtt_ms
        self.bw_kbps = bw_kbps  # Bandwidth shaping
        self.stabilize_s = stabilize_s  # Time for system to reach max BW before loss
        self.up_pipe = 950
        self.down_pipe = 901
        self.enabled = False
        
        # Calculate delay per direction (RTT/2)
        self.delay_ms = rtt_ms // 2 if rtt_ms > 0 else 0
        
    def setup(self):
        """Setup pipes and PF rules for bridge100 traffic"""
        print(f"Setting up RTT={self.rtt_ms}ms (delay={self.delay_ms}ms each way)")
        
        # Create pipes with delay
        self._create_pipes()
        
        # Setup PF rules for bridge100
        self._setup_pf_rules()
        
        self.enabled = True
        bw_str = f"BW={self.bw_kbps}Kbit/s" if self.bw_kbps else "BW=unlimited"
        print(f"Bridge shaping ready: RTT={self.rtt_ms}ms, {bw_str}, PLR=0%")
        
    def _create_pipes(self):
        """Create dummynet pipes with delay and bandwidth"""
        for pipe_id in [self.up_pipe, self.down_pipe]:
            cmd = ["sudo", DNCTL, "pipe", str(pipe_id), "config", "plr", "0"]
            
            # Add bandwidth if specified
            if self.bw_kbps:
                cmd.extend(["bw", f"{self.bw_kbps}Kbit/s"])
                
            # Add delay if specified
            if self.delay_ms > 0:
                cmd.extend(["delay", f"{self.delay_ms}ms"])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: Failed to create pipe {pipe_id}: {result.stderr}")
                
    def _setup_pf_rules(self):
        """Setup PF rules to route bridge100 traffic through our pipes"""
        
        # Create anchor rules file
        anchor_file = "/tmp/bridge_delay_anchor.conf"
        rules = [
            "no dummynet quick on lo0 all",
            f"dummynet in  quick on bridge100 inet  from any to any pipe {self.up_pipe}",
            f"dummynet out quick on bridge100 inet  from any to any pipe {self.down_pipe}",
            f"dummynet in  quick on bridge100 inet6 from any to any pipe {self.up_pipe}",
            f"dummynet out quick on bridge100 inet6 from any to any pipe {self.down_pipe}",
        ]
        
        with open(anchor_file, 'w') as f:
            f.write('\n'.join(rules) + '\n')
            
        # Setup main PF ruleset with anchor
        main_pf = "/tmp/pf_main.conf"
        subprocess.run([
            "sudo", "sh", "-c", 
            f'cat /etc/pf.conf; echo "dummynet-anchor \\"com.cell.trace\\""; echo "anchor \\"com.cell.trace\\"";'
        ], stdout=open(main_pf, 'w'), check=True)
        
        subprocess.run(["sudo", "pfctl", "-f", main_pf], 
                      capture_output=True, check=True)
        
        # Load anchor rules
        subprocess.run(["sudo", "pfctl", "-a", "com.cell.trace", "-f", anchor_file],
                      capture_output=True, check=True)
        
        # Enable PF
        subprocess.run(["sudo", "pfctl", "-e"], capture_output=True)
        
    def update_loss(self, loss_percent):
        """Update packet loss while maintaining RTT and bandwidth"""
        if not self.enabled:
            print("Shaper not enabled")
            return
            
        plr = max(0.0, float(loss_percent) / 100.0)
        
        for pipe_id in [self.up_pipe, self.down_pipe]:
            cmd = ["sudo", DNCTL, "pipe", str(pipe_id), "config", "plr", f"{plr:.6f}"]
            
            # Preserve bandwidth if set
            if self.bw_kbps:
                cmd.extend(["bw", f"{self.bw_kbps}Kbit/s"])
                
            # Preserve delay if set
            if self.delay_ms > 0:
                cmd.extend(["delay", f"{self.delay_ms}ms"])
                
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Failed to update pipe {pipe_id}: {result.stderr}")
            else:
                bw_str = f"{self.bw_kbps}K" if self.bw_kbps else "∞"
                print(f"📡 Pipe {pipe_id}: RTT={self.delay_ms}ms, BW={bw_str}, PLR={loss_percent}%")
                
    def show_status(self):
        """Show current pipe status"""
        result = subprocess.run(["sudo", DNCTL, "list"], 
                              capture_output=True, text=True, check=True)
        
        print("=== Current Pipes ===")
        for line in result.stdout.splitlines():
            if f"{self.up_pipe:05d}:" in line or f"{self.down_pipe:05d}:" in line:
                print(line)
                
        # Show traffic counters
        lines = result.stdout.splitlines()
        in_traffic = False
        for line in lines:
            if "BKT Prot" in line:
                in_traffic = True
                continue
            if in_traffic and line.strip():
                print(f"Traffic: {line}")
                
    def teardown(self):
        """Clean up PF rules (keep pipes for stability)"""
        if self.enabled:
            print("🧹 Cleaning up PF rules...")
            subprocess.run(["sudo", "pfctl", "-a", "com.cell.trace", "-F", "all"],
                          capture_output=True)
            print("PF rules cleared (pipes preserved)")
            self.enabled = False





def find_latest_experiment_folder():
    """Find the latest experiment folder for logging"""
    import glob
    import os
    
    # Look for any experiment folder (gcc, reno, cubic, etc.)
    pattern = "experiments/*"
    matches = [m for m in glob.glob(pattern) if os.path.isdir(m)]
    if matches:
        return max(matches, key=os.path.getctime)
    return None

def run_trace(shaper, profile_name, duration_s, recovery_s=0.0):
    """Run a loss trace with the given profile"""
    
    if profile_name not in TRACES:
        print(f"Unknown profile: {profile_name}")
        print(f"Available profiles: {list(TRACES.keys())}")
        return
    
    if TRACES[profile_name] is None:
        print(f"Profile '{profile_name}' is not available (missing trace data)")
        return
        
    # Use built-in trace
    trace = TRACES[profile_name]
    gaps = list(trace.get("gaps", []))
    losses = list(trace.get("loss", []))
    
    print(f"Running cellular trace: {profile_name}")
    print(f"Trace segments: {len(gaps)}, Duration: {duration_s}s")
    
    # Find experiment folder for logging
    import json
    import os
    
    experiment_folder = find_latest_experiment_folder()
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
        'profile': profile_name,
        'rtt_ms': shaper.rtt_ms,
        'bw_kbps': shaper.bw_kbps,
        'stabilize_s': shaper.stabilize_s,
        'duration_s': duration_s,
        'recovery_s': recovery_s,
        'timestamp_start': time.time()
    }
    with open(loss_config_path, "w") as f:
        json.dump(loss_config, f, indent=2)
    
    # Stabilization period (RTT + BW already set, 0% loss)
    if shaper.stabilize_s > 0:
        print(f"Stabilization: RTT + BW stable, 0% loss for {shaper.stabilize_s}s")
        print("   (Allowing system to reach maximum bandwidth)")
        
        # Log stabilization start
        stabilization_start = time.time()
        with open(timing_log_path, "w") as f:
            f.write(f"stabilization_start: {json.dumps({'timestamp_ms': int(stabilization_start * 1000), 'duration_s': shaper.stabilize_s})}\n")
        
        shaper.update_loss(0)
        time.sleep(shaper.stabilize_s)
    
    # Loss trace period (keep RTT + BW, vary loss)
    print(f"Starting loss trace (RTT={shaper.rtt_ms}ms, BW preserved)")
    
    # Log loss period start
    loss_start = time.time()
    with open(timing_log_path, "a") as f:
        f.write(f"loss_start: {json.dumps({'timestamp_ms': int(loss_start * 1000), 'profile': profile_name, 'duration_s': duration_s})}\n")
    
    start_time = time.monotonic()
    elapsed = 0.0
    
    for i, (gap, loss) in enumerate(zip(gaps, losses)):
        if elapsed >= duration_s:
            break
            
        # Calculate hold time for this segment
        hold = min(float(gap), max(0.0, duration_s - elapsed))
        
        # Log each loss segment
        segment_start = time.time()
        with open(timing_log_path, "a") as f:
            f.write(f"loss_segment: {json.dumps({'segment': i, 'timestamp_ms': int(segment_start * 1000), 'loss_percent': loss, 'duration_s': hold})}\n")
        
        print(f"Segment {i+1}: {loss:.2f}% loss for {hold:.3f}s (t={elapsed:.1f}s)")
        shaper.update_loss(loss)
        time.sleep(hold)
        
        elapsed = time.monotonic() - start_time
    
    # Log loss period end
    loss_end = time.time()
    with open(timing_log_path, "a") as f:
        f.write(f"loss_end: {json.dumps({'timestamp_ms': int(loss_end * 1000), 'total_duration_s': elapsed})}\n")
    
    # Recovery - clear loss but keep RTT + BW
    if recovery_s > 0:
        print(f"Recovery: 0% loss (RTT + BW preserved) for {recovery_s}s")
        
        # Log recovery start
        recovery_start = time.time()
        with open(timing_log_path, "a") as f:
            f.write(f"recovery_start: {json.dumps({'timestamp_ms': int(recovery_start * 1000), 'duration_s': recovery_s})}\n")
        
        shaper.update_loss(0)
        time.sleep(recovery_s)
        
        # Log recovery end
        recovery_end = time.time()
        with open(timing_log_path, "a") as f:
            f.write(f"recovery_end: {json.dumps({'timestamp_ms': int(recovery_end * 1000), 'total_duration_s': recovery_s})}\n")
    else:
        print("Recovery: 0% loss (RTT + BW preserved)")
        shaper.update_loss(0)
        
    print("Trace complete")
    print(f"Timing log saved to: {timing_log_path}")

def main():
    parser = argparse.ArgumentParser(description="Bridge-aware network shaping")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup pipes and rules')
    setup_parser.add_argument('--rtt', type=int, default=0, help='RTT in ms')
    setup_parser.add_argument('--bw', type=int, default=None, help='Bandwidth in Kbit/s')
    setup_parser.add_argument('--stabilize', type=float, default=0.0, help='Stabilization time before loss (seconds)')
    
    # Run command  
    run_parser = subparsers.add_parser('run', help='Run loss trace')
    run_parser.add_argument('--rtt', type=int, default=0, help='RTT in ms')
    run_parser.add_argument('--bw', type=int, default=None, help='Bandwidth in Kbit/s')
    run_parser.add_argument('--profile', choices=list(TRACES.keys()), 
                           default='median', help='Loss profile')
    run_parser.add_argument('--duration', type=int, default=90, help='Loss trace duration in seconds')
    run_parser.add_argument('--stabilize', type=float, default=40.0, help='Stabilization time before loss (seconds)')
    run_parser.add_argument('--recovery', type=float, default=0.0, help='Recovery time after loss (seconds, RTT preserved)')
    
    # Hairpin-specific arguments
    run_parser.add_argument('--hairpin', action='store_true', help='Use hairpin composite traces')
    run_parser.add_argument('--level', type=int, choices=[1, 2, 3, 4, 5], default=3, 
                           help='Hairpin loss level (1=mildest, 5=most aggressive)')
    run_parser.add_argument('--hairpin-duration', type=int, choices=[30, 60, 90], 
                           help='Hairpin trace duration (overrides --duration when using --hairpin)')
    
    # Loss command (change loss on existing setup)
    loss_parser = subparsers.add_parser('loss', help='Change loss percentage')
    loss_parser.add_argument('percentage', type=float, help='Loss percentage (0-100)')
    
    # Status command
    subparsers.add_parser('status', help='Show current status')
    
    # Clear command
    subparsers.add_parser('clear', help='Clear rules and reset loss to 0%%')
    
    # Trace info command
    subparsers.add_parser('trace-info', help='Show information about hairpin trace')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Handle commands
    if args.command == 'setup':
        shaper = BridgeShaper(rtt_ms=args.rtt, bw_kbps=args.bw, stabilize_s=args.stabilize)
        shaper.setup()
        
    elif args.command == 'run':
        shaper = BridgeShaper(rtt_ms=args.rtt, bw_kbps=args.bw, stabilize_s=args.stabilize)
        
        def cleanup_handler(signum, frame):
            print("\n🛑 Interrupted! Cleaning up...")
            shaper.teardown()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, cleanup_handler)
        
        try:
            shaper.setup()
            
            # Handle hairpin composite traces
            if args.hairpin:
                # Use hairpin-duration if specified, otherwise use duration
                hairpin_duration = args.hairpin_duration if args.hairpin_duration else args.duration
                
                # Validate hairpin duration
                if hairpin_duration not in [30, 60, 90]:
                    print(f"Error: Hairpin traces only support durations of 30, 60, or 90 seconds. Got: {hairpin_duration}s")
                    return
                
                # Build the hairpin profile name
                hairpin_profile = f"hairpin_{hairpin_duration}s_level{args.level}"
                
                if hairpin_profile not in TRACES:
                    print(f"Error: Hairpin profile '{hairpin_profile}' not found in available traces.")
                    print("Available hairpin profiles:")
                    for key in sorted(TRACES.keys()):
                        if key.startswith('hairpin_') and '_level' in key:
                            print(f"  - {key}")
                    return
                
                print(f"Using hairpin composite trace: {hairpin_profile}")
                run_trace(shaper, hairpin_profile, hairpin_duration, args.recovery)
            else:
                run_trace(shaper, args.profile, args.duration, args.recovery)
        finally:
            # Always teardown after the trace (including recovery period)
            shaper.teardown()
            
    elif args.command == 'loss':
        # Quick loss change (assumes pipes exist)
        # Read current delay and bandwidth from existing pipes
        result = subprocess.run(["sudo", DNCTL, "list"], 
                              capture_output=True, text=True, check=True)
        
        current_delay = 0
        current_bw = None
        for line in result.stdout.splitlines():
            if "00950:" in line or "00901:" in line:
                parts = line.split()
                # Parse delay
                for i, part in enumerate(parts):
                    if part == "ms" and i > 0:
                        try:
                            current_delay = int(parts[i-1])
                        except ValueError:
                            pass
                # Parse bandwidth (look for Mbit/s or Kbit/s)
                for i, part in enumerate(parts):
                    if part == "Mbit/s" and i > 0:
                        try:
                            current_bw = int(float(parts[i-1]) * 1000)  # Convert Mbit/s to Kbit/s
                        except ValueError:
                            pass
                    elif part == "Kbit/s" and i > 0:
                        try:
                            current_bw = int(parts[i-1])
                        except ValueError:
                            pass
                break
        
        rtt_ms = current_delay * 2  # delay per direction -> total RTT
        shaper = BridgeShaper(rtt_ms=rtt_ms, bw_kbps=current_bw)
        shaper.enabled = True  # Skip setup
        shaper.update_loss(args.percentage)
        print(f"Updated: RTT={rtt_ms}ms, PLR={args.percentage}%")
        
    elif args.command == 'status':
        shaper = BridgeShaper()
        shaper.enabled = True
        shaper.show_status()
        
    elif args.command == 'clear':
        shaper = BridgeShaper()
        shaper.enabled = True
        shaper.update_loss(0)  # Reset loss
        shaper.teardown()
        
    elif args.command == 'trace-info':
        # Show trace information for hairpin profile
        profile_name = 'hairpin'
        if profile_name not in TRACES or TRACES[profile_name] is None:
            print(f"Hairpin trace not available")
            return
            
        trace = TRACES[profile_name]
        gaps = trace['gaps']
        losses = trace['loss']
        
        total_time = sum(gaps)
        avg_loss = sum(losses) / len(losses) if losses else 0
        max_loss = max(losses) if losses else 0
        min_loss = min(losses) if losses else 0
        nonzero_loss = [l for l in losses if l > 0]
        loss_frames = len(nonzero_loss)
        loss_time = sum(gaps[i] for i, l in enumerate(losses) if l > 0)
        
        print(f"Hairpin Trace Information:")
        print(f"   Total frames: {len(gaps):,}")
        print(f"   Total duration: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        print(f"   Frame duration: {gaps[0]*1000:.1f}ms (average)")
        print(f"")
        print(f"📉 Loss Statistics:")
        print(f"   Average loss: {avg_loss:.2f}%")
        print(f"   Loss range: {min_loss:.2f}% - {max_loss:.2f}%")
        print(f"   Frames with loss: {loss_frames:,} ({loss_frames/len(gaps)*100:.1f}%)")
        print(f"   Time with loss: {loss_time:.1f}s ({loss_time/total_time*100:.1f}%)")

if __name__ == '__main__':
    main()