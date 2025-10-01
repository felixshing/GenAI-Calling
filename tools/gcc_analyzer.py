#!/usr/bin/env python3
"""
GCC Performance Analyzer

Comprehensive analysis tool for GCC congestion control performance.
Provides configurable analysis options with detailed metrics and optional plotting.

Usage Examples:
    # Basic analysis (all metrics, no plots)
    ./gcc_analyzer.py /path/to/experiment

    # Bitrate analysis with plot
    ./gcc_analyzer.py /path/to/experiment --bitrate --plot

    # All metrics with plots
    ./gcc_analyzer.py /path/to/experiment --all --plot

    # All metrics except SSIM (faster)
    ./gcc_analyzer.py /path/to/experiment --all --no-ssim --plot

    # With analysis delay for OUT bitrate (default 10s delay)
    ./gcc_analyzer.py /path/to/experiment --all --analysis-delay --plot

    # With custom analysis delay (5s delay)
    ./gcc_analyzer.py /path/to/experiment --all --analysis-delay 5 --plot

    # Specific metrics only
    ./gcc_analyzer.py /path/to/experiment --utilization --ssim --fps

Available Metrics:
    --bitrate         All 5 bitrate types over time (OUT, IN, As, Ar, GCC)
    --utilization     Bandwidth utilization for all 5 bitrate types during loss
    --recovery        Recovery time for all 5 bitrate types  
    --ssim           Video quality (SSIM) during loss (percentiles)
    --fps            Frame rate during loss (percentiles)
    --h264           H264 decode failure percentage
    --all            All metrics
    --no-ssim        Exclude SSIM analysis when using --all (faster execution)
    --analysis-delay  Analysis delay for OUT bitrate utilization (seconds)

5 Bitrate Types Explained:
    OUT              Bitrate sent by client (application layer)
    IN               Bitrate received by client (application layer)
    As               Loss-based estimate (GCC congestion control)
    Ar               REMB feedback estimate (GCC congestion control) 
    GCC              Combined target = min(As, Ar) (GCC congestion control)

Options:
    --plot           Generate plots for applicable metrics
    --no-percentiles Skip percentile calculations (faster)
"""

import argparse
import json
import os
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import cv2
from skimage.metrics import structural_similarity as ssim

# Global configuration
ANALYSIS_DELAY_S = 10.0  # Default delay for OUT bitrate utilization analysis

def parse_client_stats(stats_file: str) -> List[Dict]:
    """Parse client stats log and extract bitrate/FPS data."""
    bitrate_data = []
    
    if not os.path.exists(stats_file):
        print(f"Client stats file not found: {stats_file}")
        return []
    
    with open(stats_file, 'r') as f:
        content = f.read()
        
    # Split by stats entries
    stats_entries = content.split('stats: [STATS]')
    
    for entry in stats_entries[1:]:  # Skip first empty entry
        lines = entry.strip().split('\n')
        if not lines:
            continue
            
        # Parse timestamp from first line
        import re
        timestamp_match = re.search(r'time=(\d+)', lines[0])
        if not timestamp_match:
            continue
            
        timestamp_ms = timestamp_match.group(1)
        timestamp_s = float(timestamp_ms) / 1000.0
        
        # Parse each stats line separately
        data_entry = {'timestamp_s': timestamp_s}
        
        # Join all lines for regex matching
        full_entry = '\n'.join(lines)
        
        # Parse CLIENT SENT
        client_sent_match = re.search(r'CLIENT SENT: bitrate=(\d+)bps, fps=(\d+), res=([^\n]+)', full_entry)
        if client_sent_match:
            bitrate, fps, res = client_sent_match.groups()
            data_entry.update({
                'client_sent_bitrate_bps': int(bitrate),
                'client_sent_bitrate_mbps': int(bitrate) / 1000000.0,
                'client_sent_fps': int(fps),
                'client_sent_resolution': res.strip()
            })
        
        # Parse SERVER RECEIVED
        server_received_match = re.search(r'SERVER RECEIVED: bitrate=(\d+)bps, fps=([\d.]+), res=([^\n]+)', full_entry)
        if server_received_match:
            bitrate, fps, res = server_received_match.groups()
            data_entry.update({
                'server_received_bitrate_bps': int(bitrate),
                'server_received_bitrate_mbps': int(bitrate) / 1000000.0,
                'server_received_fps': float(fps),
                'server_received_resolution': res.strip()
            })
        
        # Parse SERVER SENT
        server_sent_match = re.search(r'SERVER SENT: bitrate=(\d+)bps, fps=([\d.]+), res=([^\n]+)', full_entry)
        if server_sent_match:
            bitrate, fps, res = server_sent_match.groups()
            data_entry.update({
                'server_sent_bitrate_bps': int(bitrate),
                'server_sent_bitrate_mbps': int(bitrate) / 1000000.0,
                'server_sent_fps': float(fps),
                'server_sent_resolution': res.strip()
            })
        
        # Parse CLIENT RECEIVED
        client_received_match = re.search(r'CLIENT RECEIVED: bitrate=(\d+)bps, fps=(\d+), res=([^\n]+)', full_entry)
        if client_received_match:
            bitrate, fps, res = client_received_match.groups()
            data_entry.update({
                'client_received_bitrate_bps': int(bitrate),
                'client_received_bitrate_mbps': int(bitrate) / 1000000.0,
                'client_received_fps': int(fps),
                'client_received_resolution': res.strip()
            })
        
        # Only add entry if we have at least some data
        if len(data_entry) > 1:  # More than just timestamp_s
            bitrate_data.append(data_entry)
    
    return sorted(bitrate_data, key=lambda x: x['timestamp_s'])

def parse_server_reception_stats(stats_file: str) -> List[Dict]:
    """Parse server reception stats log and extract server-side metrics."""
    server_data = []
    
    if not os.path.exists(stats_file):
        print(f"Server reception stats file not found: {stats_file}")
        return []
    
    with open(stats_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line.startswith("server_reception:"):
                continue
                
            # Parse server reception metrics
            import re
            import json
            try:
                # Extract the JSON part after "server_reception: "
                json_str = line.split("server_reception: ", 1)[1]
                server_info = json.loads(json_str)
                
                timestamp_s = float(server_info['timestamp_ms']) / 1000.0
                
                server_data.append({
                    'timestamp_s': timestamp_s,
                    'frame_number': server_info['frame_number'],
                    'server_received_fps': server_info['server_received_fps'],
                    'server_received_resolution': server_info['server_received_resolution'],
                    'total_packets_received': server_info['total_packets_received'],
                    'decode_failures': server_info['decode_failures']
                })
            except Exception as e:
                print(f"Failed to parse server reception line: {line}, error: {e}")
                continue
    
    return sorted(server_data, key=lambda x: x['timestamp_s'])

def parse_gcc_estimates(gcc_file: str) -> List[Dict]:
    """Parse GCC estimates log and extract As, Ar, GCC data."""
    gcc_data = []
    
    if not os.path.exists(gcc_file):
        print(f"GCC estimates file not found: {gcc_file}")
        return []
    
    with open(gcc_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            
            # Parse: timestamp_s, as_bps, ar_bps, gcc_bps
            try:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 4:
                    timestamp_s = float(parts[0])
                    as_bps = int(parts[1]) if parts[1] != '0' else None
                    ar_bps = int(parts[2]) if parts[2] != '0' else None
                    gcc_bps = int(parts[3]) if parts[3] != '0' else None
                    
                    gcc_data.append({
                        'timestamp_s': timestamp_s,
                        'as_bps': as_bps,
                        'ar_bps': ar_bps, 
                        'gcc_bps': gcc_bps,
                        'as_mbps': as_bps / 1000000.0 if as_bps else None,
                        'ar_mbps': ar_bps / 1000000.0 if ar_bps else None,
                        'gcc_mbps': gcc_bps / 1000000.0 if gcc_bps else None
                    })
            except (ValueError, IndexError):
                continue
    
    return sorted(gcc_data, key=lambda x: x['timestamp_s'])

def parse_loss_timing(timing_file: str) -> Dict:
    """Parse packet loss timing information."""
    if not os.path.exists(timing_file):
        return {}
    
    timing_info = {}
    with open(timing_file, 'r') as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                event_type, data_str = line.split(':', 1)
                try:
                    data = json.loads(data_str.strip())
                    timing_info[event_type] = data
                except json.JSONDecodeError:
                    continue
    
    return timing_info

def calculate_reference_bitrate(data: List[Dict], loss_start_s: float, bitrate_field: str) -> Tuple[float, int]:
    """Calculate reference bitrate from 10 seconds before loss starts for any bitrate field."""
    if not data:
        return 0.0, 0
    
    t0 = data[0]['timestamp_s']
    loss_start_relative = loss_start_s - t0
    
    # Get 10 seconds before loss
    ref_start = loss_start_relative - 10.0
    ref_end = loss_start_relative
    
    ref_data = [d for d in data if ref_start <= (d['timestamp_s'] - t0) <= ref_end and d.get(bitrate_field) is not None]
    
    if not ref_data:
        return 0.0, 0
    
    bitrates = [d[bitrate_field] for d in ref_data]
    reference_bitrate = sum(bitrates) / len(bitrates)
    
    return reference_bitrate, len(ref_data)



def calculate_percentiles(values: List[float]) -> Dict:
    """Calculate 5, 25, 50, 75, 95 percentiles."""
    if not values:
        return {}
    
    return {
        'p5': float(np.percentile(values, 5)),
        'p25': float(np.percentile(values, 25)),
        'p50': float(np.percentile(values, 50)),
        'p75': float(np.percentile(values, 75)),
        'p95': float(np.percentile(values, 95)),
        'mean': float(np.mean(values)),
        'min': float(np.min(values)),
        'max': float(np.max(values))
    }

def analyze_bitrate(bitrate_data: List[Dict], gcc_data: List[Dict], timing_info: Dict, args) -> Dict:
    """Analyze all 4 bitrates over time."""
    if not bitrate_data:
        return {}
    
    # Define the 4 bitrate fields to analyze
    bitrate_fields = [
        'client_sent_bitrate_mbps',
        'server_received_bitrate_mbps', 
        'server_sent_bitrate_mbps',
        'client_received_bitrate_mbps'
    ]
    
    result = {
        'total_duration_s': bitrate_data[-1]['timestamp_s'] - bitrate_data[0]['timestamp_s'],
        'total_samples': len(bitrate_data)
    }
    
    # Analyze each bitrate separately
    for field in bitrate_fields:
        if any(field in d for d in bitrate_data):
            values = [d[field] for d in bitrate_data if field in d and d[field] is not None]
            if values:
                result[f'{field}_stats'] = {
                    'min': min(values),
                    'max': max(values),
                    'mean': np.mean(values),
                    'samples': len(values)
                }
    
    if args.plot:
        # Generate comprehensive bitrate plot
        plot_bitrate_over_time(bitrate_data, gcc_data, timing_info, args.output_dir)
    
    return result

def analyze_comprehensive_utilization(bitrate_data: List[Dict], gcc_data: List[Dict], timing_info: Dict, experiment_info: Dict, args) -> Dict:
    """Analyze bandwidth utilization during loss for all 4 bitrate types."""
    if 'loss_start' not in timing_info:
        return {}
    
    loss_start_s = timing_info['loss_start']['timestamp_ms'] / 1000.0
    loss_end_s = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_s + 60) / 1000.0
    
    results = {}
    all_utilizations = {}  # Store all utilization data for plotting
    
    # Analyze all 4 bitrates
    if bitrate_data:
        t0 = bitrate_data[0]['timestamp_s']
        loss_start_rel = loss_start_s - t0
        loss_end_rel = loss_end_s - t0
        
        # Define the 4 bitrate fields to analyze
        bitrate_fields = [
            ('client_sent_bitrate_mbps', 'CLIENT SENT'),
            ('server_received_bitrate_mbps', 'SERVER RECEIVED'),
            ('server_sent_bitrate_mbps', 'SERVER SENT'),
            ('client_received_bitrate_mbps', 'CLIENT RECEIVED')
        ]
        
        for field, label in bitrate_fields:
            # Get loss period data for this bitrate
            loss_data = [d for d in bitrate_data if loss_start_rel <= (d['timestamp_s'] - t0) <= loss_end_rel and field in d and d[field] is not None]
            
            if loss_data:
                # Calculate reference bitrate from 5 seconds before loss
                ref_bitrate, ref_samples = calculate_reference_bitrate(bitrate_data, loss_start_s, field)
                
                if ref_bitrate > 0:
                    utilizations = [d[field] / ref_bitrate for d in loss_data]
                    utilizations_percent = [min(u * 100, 100.0) for u in utilizations]
                    all_utilizations[label] = utilizations_percent
                    
                    results[field] = {
                        'reference_bitrate_mbps': ref_bitrate,
                        'reference_samples': ref_samples,
                        'utilization_samples': len(utilizations)
                    }
                    if not args.no_percentiles:
                        results[field]['percentiles'] = calculate_percentiles(utilizations_percent)
    
    # GCC-level estimates (As, Ar, GCC)
    if gcc_data:
        gcc_t0 = gcc_data[0]['timestamp_s']
        # GCC estimates always start from loss start (no delay)
        gcc_loss_analysis_start_rel = loss_start_s - gcc_t0
        gcc_loss_end_rel = loss_end_s - gcc_t0
        
        gcc_loss_data = [d for d in gcc_data if gcc_loss_analysis_start_rel <= (d['timestamp_s'] - gcc_t0) <= gcc_loss_end_rel]
        
        # As (Loss-based) utilization
        # Use max_as_bitrate as reference if available, otherwise use historical data
        max_as_bitrate_bps = experiment_info.get('max_as_bitrate')
        if max_as_bitrate_bps:
            ref_as = max_as_bitrate_bps / 1000000.0  # Convert to Mbps
            ref_as_samples = 1  # Configured value, not historical samples
            print(f"  Using configured As reference: {ref_as:.2f} Mbps (from --max-as-bitrate)")
        else:
            ref_as, ref_as_samples = calculate_reference_bitrate(gcc_data, loss_start_s, 'as_mbps')
        
        if ref_as > 0 and gcc_loss_data:
            as_loss_data = [d for d in gcc_loss_data if d['as_mbps'] is not None]
            if as_loss_data:
                as_utilizations = [d['as_mbps'] / ref_as for d in as_loss_data]
                as_utilizations_percent = [min(u * 100, 100.0) for u in as_utilizations]
                all_utilizations['As (Loss-based)'] = as_utilizations_percent
                
                results['as_estimate'] = {
                    'reference_bitrate_mbps': ref_as,
                    'reference_samples': ref_as_samples,
                    'utilization_samples': len(as_utilizations)
                }
                if not args.no_percentiles:
                    results['as_estimate']['percentiles'] = calculate_percentiles(as_utilizations_percent)
        
        # Ar (REMB) utilization  
        ref_ar, ref_ar_samples = calculate_reference_bitrate(gcc_data, loss_start_s, 'ar_mbps')
        if ref_ar > 0 and gcc_loss_data:
            ar_loss_data = [d for d in gcc_loss_data if d['ar_mbps'] is not None]
            if ar_loss_data:
                ar_utilizations = [d['ar_mbps'] / ref_ar for d in ar_loss_data]
                ar_utilizations_percent = [min(u * 100, 100.0) for u in ar_utilizations]
                all_utilizations['Ar (REMB)'] = ar_utilizations_percent
                
                results['ar_estimate'] = {
                    'reference_bitrate_mbps': ref_ar,
                    'reference_samples': ref_ar_samples,
                    'utilization_samples': len(ar_utilizations)
                }
                if not args.no_percentiles:
                    results['ar_estimate']['percentiles'] = calculate_percentiles(ar_utilizations_percent)
        
        # GCC (Combined) utilization
        ref_gcc, ref_gcc_samples = calculate_reference_bitrate(gcc_data, loss_start_s, 'gcc_mbps')
        if ref_gcc > 0 and gcc_loss_data:
            gcc_loss_data_valid = [d for d in gcc_loss_data if d['gcc_mbps'] is not None]
            if gcc_loss_data_valid:
                gcc_utilizations = [d['gcc_mbps'] / ref_gcc for d in gcc_loss_data_valid]
                gcc_utilizations_percent = [min(u * 100, 100.0) for u in gcc_utilizations]
                all_utilizations['GCC (Combined)'] = gcc_utilizations_percent
                
                results['gcc_combined'] = {
                    'reference_bitrate_mbps': ref_gcc,
                    'reference_samples': ref_gcc_samples,
                    'utilization_samples': len(gcc_utilizations)
                }
                if not args.no_percentiles:
                    results['gcc_combined']['percentiles'] = calculate_percentiles(gcc_utilizations_percent)
    
    # Generate comprehensive utilization box plot if requested
    if args.plot and all_utilizations:
        plot_comprehensive_utilization_boxplot(all_utilizations, args.output_dir)
    
    return results

def analyze_utilization(bitrate_data: List[Dict], timing_info: Dict, args) -> Dict:
    """Legacy function - analyze OUT bitrate utilization only for backward compatibility."""
    if not bitrate_data or 'loss_start' not in timing_info:
        return {}
    
    loss_start_s = timing_info['loss_start']['timestamp_ms'] / 1000.0
    
    # Calculate reference bitrate
    ref_bitrate, ref_samples = calculate_reference_bitrate(bitrate_data, loss_start_s, 'out_bitrate_mbps')
    if ref_bitrate <= 0:
        return {}
    
    # Get utilization during loss (start from loss beginning)
    t0 = bitrate_data[0]['timestamp_s']
    loss_start_rel = loss_start_s - t0
    loss_end_s = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_s + 60) / 1000.0
    loss_end_rel = loss_end_s - t0
    
    loss_data = [d for d in bitrate_data if loss_start_rel <= (d['timestamp_s'] - t0) <= loss_end_rel]
    if not loss_data:
        return {}
    
    utilizations = [d['out_bitrate_mbps'] / ref_bitrate for d in loss_data]
    # Cap utilization at 100% maximum
    utilizations_percent = [min(u * 100, 100.0) for u in utilizations]
    
    result = {
        'reference_bitrate_mbps': ref_bitrate,
        'reference_samples': ref_samples,
        'utilization_samples': len(utilizations)
    }
    
    if not args.no_percentiles:
        result['percentiles'] = calculate_percentiles(utilizations_percent)
    
    if args.plot:
        plot_utilization_boxplot(utilizations_percent, args.output_dir)
    
    return result

def analyze_comprehensive_recovery(bitrate_data: List[Dict], gcc_data: List[Dict], timing_info: Dict, args) -> Dict:
    """Analyze recovery time for all 4 bitrate types."""
    if 'loss_start' not in timing_info:
        return {}
    
    loss_start_s = timing_info['loss_start']['timestamp_ms'] / 1000.0
    
    # Check if loss ended (experiment may have terminated during loss)
    if 'loss_end' not in timing_info:
        return {'error': 'Experiment ended during loss period - no recovery data available'}
    
    loss_end_s = timing_info['loss_end']['timestamp_ms'] / 1000.0
    recovery_threshold = 1.0  # 100% of reference
    
    results = {}
    
    # Analyze recovery for all 4 bitrates
    if bitrate_data:
        t0 = bitrate_data[0]['timestamp_s']
        loss_end_rel = loss_end_s - t0
        recovery_data = [d for d in bitrate_data if (d['timestamp_s'] - t0) > loss_end_rel]
        
        # Define the 4 bitrate fields to analyze
        bitrate_fields = [
            ('client_sent_bitrate_mbps', 'CLIENT SENT'),
            ('server_received_bitrate_mbps', 'SERVER RECEIVED'),
            ('server_sent_bitrate_mbps', 'SERVER SENT'),
            ('client_received_bitrate_mbps', 'CLIENT RECEIVED')
        ]
        
        for field, label in bitrate_fields:
            ref_bitrate, _ = calculate_reference_bitrate(bitrate_data, loss_start_s, field)
            if ref_bitrate > 0 and recovery_data:
                recovery_time_s = None
                for d in recovery_data:
                    if field in d and d[field] is not None:
                        utilization = d[field] / ref_bitrate
                        if utilization >= recovery_threshold:
                            recovery_time_s = (d['timestamp_s'] - t0) - loss_end_rel
                            break
                
                results[field] = {
                    'recovery_time_s': recovery_time_s,
                    'recovery_threshold': recovery_threshold,
                    'reference_bitrate_mbps': ref_bitrate
                }
    
    # GCC-level recovery (As, Ar, GCC)
    if gcc_data:
        gcc_t0 = gcc_data[0]['timestamp_s']
        gcc_loss_end_rel = loss_end_s - gcc_t0
        gcc_recovery_data = [d for d in gcc_data if (d['timestamp_s'] - gcc_t0) > gcc_loss_end_rel]
        
        # As (Loss-based) recovery
        ref_as, _ = calculate_reference_bitrate(gcc_data, loss_start_s, 'as_mbps')
        if ref_as > 0 and gcc_recovery_data:
            recovery_time_s = None
            for d in gcc_recovery_data:
                if d['as_mbps'] is not None:
                    utilization = d['as_mbps'] / ref_as
                    if utilization >= recovery_threshold:
                        recovery_time_s = (d['timestamp_s'] - gcc_t0) - gcc_loss_end_rel
                        break
            
            results['as_estimate'] = {
                'recovery_time_s': recovery_time_s,
                'recovery_threshold': recovery_threshold,
                'reference_bitrate_mbps': ref_as
            }
        
        # Ar (REMB) recovery
        ref_ar, _ = calculate_reference_bitrate(gcc_data, loss_start_s, 'ar_mbps')
        if ref_ar > 0 and gcc_recovery_data:
            recovery_time_s = None
            for d in gcc_recovery_data:
                if d['ar_mbps'] is not None:
                    utilization = d['ar_mbps'] / ref_ar
                    if utilization >= recovery_threshold:
                        recovery_time_s = (d['timestamp_s'] - gcc_t0) - gcc_loss_end_rel
                        break
            
            results['ar_estimate'] = {
                'recovery_time_s': recovery_time_s,
                'recovery_threshold': recovery_threshold,
                'reference_bitrate_mbps': ref_ar
            }
        
        # GCC (Combined) recovery
        ref_gcc, _ = calculate_reference_bitrate(gcc_data, loss_start_s, 'gcc_mbps')
        if ref_gcc > 0 and gcc_recovery_data:
            recovery_time_s = None
            for d in gcc_recovery_data:
                if d['gcc_mbps'] is not None:
                    utilization = d['gcc_mbps'] / ref_gcc
                    if utilization >= recovery_threshold:
                        recovery_time_s = (d['timestamp_s'] - gcc_t0) - gcc_loss_end_rel
                        break
            
            results['gcc_combined'] = {
                'recovery_time_s': recovery_time_s,
                'recovery_threshold': recovery_threshold,
                'reference_bitrate_mbps': ref_gcc
            }
    
    return results

def analyze_recovery(bitrate_data: List[Dict], timing_info: Dict, args) -> Dict:
    """Legacy function - analyze OUT bitrate recovery only for backward compatibility."""
    if not bitrate_data or 'loss_start' not in timing_info:
        return {}
    
    loss_start_s = timing_info['loss_start']['timestamp_ms'] / 1000.0
    loss_end_s = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_s + 60) / 1000.0
    
    # Calculate reference bitrate
    ref_bitrate, _ = calculate_reference_bitrate(bitrate_data, loss_start_s, 'out_bitrate_mbps')
    if ref_bitrate <= 0:
        return {}
    
    # Find recovery time (90% of reference)
    t0 = bitrate_data[0]['timestamp_s']
    loss_end_rel = loss_end_s - t0
    recovery_data = [d for d in bitrate_data if (d['timestamp_s'] - t0) > loss_end_rel]
    
    recovery_time_s = None
    for d in recovery_data:
        utilization = d['out_bitrate_mbps'] / ref_bitrate
        if utilization >= 0.9:  # 90% of reference
            recovery_time_s = (d['timestamp_s'] - t0) - loss_end_rel
            break
    
    return {
        'recovery_time_s': recovery_time_s,
                        'recovery_threshold': 1.0,
        'reference_bitrate_mbps': ref_bitrate
    }

def analyze_ssim(exp_dir: Path, timing_info: Dict, bitrate_data: List[Dict], args) -> Dict:
    """Analyze video quality (SSIM) during loss."""
    if 'loss_start' not in timing_info or not bitrate_data:
        return {}
    
    loss_start_ms = timing_info['loss_start']['timestamp_ms']
    loss_end_ms = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_ms + 60000)
    
    try:
        video_dir = exp_dir / "videos"
        if not video_dir.exists():
            return {'error': 'Videos directory not found'}
        
        # Find received video
        received_video = None
        for video_file in video_dir.glob("*.mp4"):
            received_video = video_file
            break
        
        if not received_video:
            return {'error': 'No received video found'}
        
        # Find reference video
        reference_video = Path("long_video_for_testing.mp4")
        if not reference_video.exists():
            return {'error': 'Reference video not found: long_video_for_testing.mp4'}
        
        # Calculate relative timing using bitrate data
        t0 = bitrate_data[0]['timestamp_s']
        loss_start_s = loss_start_ms / 1000.0
        loss_end_s = loss_end_ms / 1000.0
        
        # Convert to relative time from video start
        video_loss_start_s = loss_start_s - t0
        video_loss_end_s = loss_end_s - t0
        
        print(f"  Reference video: {reference_video}")
        print(f"  Received video: {received_video}")
        print(f"  Loss period: {loss_start_ms}ms - {loss_end_ms}ms")
        print(f"  Video loss period: {video_loss_start_s:.1f}s - {video_loss_end_s:.1f}s")
        
        # Create trimmed video containing only the loss period
        trimmed_video_path = video_dir / f"trimmed_loss_period_{received_video.stem}.mp4"
        
        # Check if trimmed video already exists
        if trimmed_video_path.exists():
            print(f"  Trimmed video already exists: {trimmed_video_path}")
            trim_success = True
        else:
            # Check if the input video is already trimmed (to avoid double-trimming)
            if "trimmed_loss_period_" in received_video.name:
                print(f"  Input video is already trimmed, skipping trimming")
                trim_success = False
            else:
                trim_success = trim_video_to_loss_period(received_video, trimmed_video_path, 
                                                       video_loss_start_s, video_loss_end_s)
                
                if trim_success:
                    print(f"  Created trimmed video: {trimmed_video_path}")
                else:
                    print(f"  Warning: Failed to create trimmed video, continuing with original")
        
        ssim_values = calculate_video_ssim_values(reference_video, received_video, 
                                                video_loss_start_s, video_loss_end_s)
        
        if not ssim_values:
            return {'error': 'No SSIM values calculated'}
        
        result = {'ssim_samples': len(ssim_values), 'values': ssim_values}
        
        if not args.no_percentiles:
            result['percentiles'] = calculate_percentiles(ssim_values)
        
        if args.plot:
            plot_ssim_boxplot(ssim_values, args.output_dir)
            # Also create time series plot
            plot_ssim_over_time(ssim_values, timing_info, args.output_dir)
        
        return result
        
    except Exception as e:
        return {'error': str(e)}

def analyze_fps(bitrate_data: List[Dict], timing_info: Dict, args) -> Dict:
    """Analyze FPS during loss for all four endpoints."""
    if not bitrate_data or 'loss_start' not in timing_info:
        return {}
    
    loss_start_ms = timing_info['loss_start']['timestamp_ms']
    loss_end_ms = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_ms + 60000)
    
    # Define the four FPS endpoints to analyze
    fps_endpoints = [
        ('client_sent_fps', 'CLIENT SENT'),
        ('server_received_fps', 'SERVER RECEIVED'),
        ('server_sent_fps', 'SERVER SENT'),
        ('client_received_fps', 'CLIENT RECEIVED')
    ]
    
    results = {}
    
    for fps_field, label in fps_endpoints:
        # Calculate reference FPS from 10 seconds before loss
        reference_fps = None
        reference_samples = []
        for entry in bitrate_data:
            timestamp_ms = entry['timestamp_s'] * 1000
            if (loss_start_ms - 10000) <= timestamp_ms <= loss_start_ms:
                fps = entry.get(fps_field, 0)
                if fps > 0:
                    reference_samples.append(fps)
        
        if reference_samples:
            reference_fps = sum(reference_samples) / len(reference_samples)
        
        # Extract FPS during loss (start from loss start)
        fps_values = []
        for entry in bitrate_data:
            timestamp_ms = entry['timestamp_s'] * 1000
            if loss_start_ms <= timestamp_ms <= loss_end_ms:
                fps = entry.get(fps_field, 0)
                if fps > 0:
                    # Cap FPS to reference FPS if available
                    if reference_fps and fps > reference_fps:
                        fps = reference_fps
                    fps_values.append(fps)
        
        if fps_values:
            result = {'fps_samples': len(fps_values)}
            if reference_fps:
                result['reference_fps'] = round(reference_fps, 1)
            
            if not args.no_percentiles:
                result['percentiles'] = calculate_percentiles(fps_values)
            
            results[fps_field] = result
        else:
            results[fps_field] = {'fps_samples': 0}
    
    # For backward compatibility, use client_received_fps as the main result
    main_result = results.get('client_received_fps', {'fps_samples': 0}).copy()
    # Create a copy of results to avoid circular references
    all_endpoints_copy = {}
    for key, value in results.items():
        all_endpoints_copy[key] = value.copy() if isinstance(value, dict) else value
    main_result['all_endpoints'] = all_endpoints_copy
    
    if args.plot:
        # Plot each FPS endpoint separately
        for fps_field, label in fps_endpoints:
            if fps_field in results and 'percentiles' in results[fps_field]:
                # Extract individual values for plotting
                fps_values = extract_fps_values_for_endpoint(bitrate_data, timing_info, fps_field)
                if fps_values:
                    # Create box plot for this endpoint
                    plot_fps_boxplot(fps_values, args.output_dir, label, fps_field)
                
                # Create time series plot for this endpoint (entire experiment duration)
                plot_fps_over_time(bitrate_data, timing_info, args.output_dir, fps_field, label)
    
    return main_result

def analyze_h264_failures(exp_dir: Path, timing_info: Dict, args) -> Dict:
    """Analyze H264 decode failures during loss (uses logged data from actual loss period)."""
    # Look for H264 failure log
    h264_log_paths = [
        exp_dir / "h264_decode_failures.log",
        exp_dir / "logs" / "h264_decode_failures.log",
        Path("/tmp/h264_decode_failures.log")
    ]
    
    h264_log = None
    for path in h264_log_paths:
        if path.exists():
            h264_log = path
            break
    
    if not h264_log:
        return {'total_failures': 0, 'failure_rate_percent': 0.0, 'note': 'No H264 failures detected'}
    
    try:
        with open(h264_log, 'r') as f:
            lines = f.readlines()
        
        # Count non-comment lines
        data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
        
        if not data_lines:
            return {'total_failures': 0, 'failure_rate_percent': 0.0, 'note': 'No H264 failures detected'}
        
        # Parse the last line for final counts
        last_line = data_lines[-1].strip() if data_lines else ""
        if not last_line:
            return {'total_failures': 0, 'failure_rate_percent': 0.0, 'note': 'No H264 failures detected'}
        
        # Parse new format: loss_failures=X, loss_total=Y, loss_rate=Z% or overall_failures=X, overall_total=Y, overall_rate=Z%
        import re
        
        # Try new format - prioritize overall rate (more realistic)
        overall_match = re.search(r'overall_failures=(\d+), overall_total=(\d+), overall_rate=([\d.]+)%', last_line)
        loss_match = re.search(r'loss_failures=(\d+), loss_total=(\d+), loss_rate=([\d.]+)%', last_line)
        if overall_match:
            failures_count = int(overall_match.group(1))
            total_count = int(overall_match.group(2))
            rate = float(overall_match.group(3))
            
            result = {
                'total_failures': failures_count,
                'total_attempts': total_count,
                'failure_rate_percent': rate,
                'context': 'overall'
            }
            
            # Include loss-specific data for reference if available
            if loss_match:
                loss_failures = int(loss_match.group(1))
                loss_total = int(loss_match.group(2))
                loss_rate = float(loss_match.group(3))
                result['loss_failures'] = loss_failures
                result['loss_attempts'] = loss_total
                result['loss_rate_percent'] = loss_rate
            
            return result
        
        # Fallback to loss-only data if overall not available
        elif loss_match:
            failures_count = int(loss_match.group(1))
            total_count = int(loss_match.group(2))
            rate = float(loss_match.group(3))
            
            return {
                'total_failures': failures_count,
                'total_attempts': total_count,
                'failure_rate_percent': rate,
                'context': 'loss_only'
            }
        
        # Try old format for backwards compatibility
        old_match = re.search(r'failures=(\d+), total=(\d+), rate=([\d.]+)%', last_line)
        if old_match:
            failures_count = int(old_match.group(1))
            total_count = int(old_match.group(2))
            rate = float(old_match.group(3))
            
            return {
                'total_failures': failures_count,
                'total_attempts': total_count,
                'failure_rate_percent': rate
            }
    except Exception as e:
        return {'error': str(e)}
    
    return {'total_failures': 0, 'failure_rate_percent': 0.0}

def trim_video_to_loss_period(input_video_path: Path, output_video_path: Path, 
                            loss_start_s: float, loss_end_s: float) -> bool:
    """Trim video to only include the loss period."""
    try:
        import subprocess
        
        # Use ffmpeg to trim the video
        cmd = [
            'ffmpeg', '-i', str(input_video_path),
            '-ss', str(loss_start_s),
            '-t', str(loss_end_s - loss_start_s),
            '-c', 'copy',  # Copy without re-encoding for speed
            '-y',  # Overwrite output file
            str(output_video_path)
        ]
        
        print(f"  Trimming video: {input_video_path.name} -> {output_video_path.name}")
        print(f"  Loss period: {loss_start_s:.1f}s - {loss_end_s:.1f}s (duration: {loss_end_s - loss_start_s:.1f}s)")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  Successfully trimmed video to {output_video_path}")
            return True
        else:
            print(f"  Error trimming video: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"  Error in video trimming: {e}")
        return False

def calculate_video_ssim_values(reference_path: Path, received_path: Path, 
                               loss_start_s: float, loss_end_s: float) -> List[float]:
    """Calculate SSIM values between reference and received video during loss period."""
    try:
        cap_ref = cv2.VideoCapture(str(reference_path))
        cap_rx = cv2.VideoCapture(str(received_path))
        
        if not cap_ref.isOpened() or not cap_rx.isOpened():
            print(f"  Failed to open videos: ref={cap_ref.isOpened()}, rx={cap_rx.isOpened()}")
            return []
        
        # Get video properties
        ref_fps = cap_ref.get(cv2.CAP_PROP_FPS) or 30
        rx_fps = cap_rx.get(cv2.CAP_PROP_FPS) or 30
        rx_total_frames = int(cap_rx.get(cv2.CAP_PROP_FRAME_COUNT))
        
        print(f"  Video FPS: ref={ref_fps}, rx={rx_fps}")
        print(f"  Received video total frames: {rx_total_frames}")
        
        # Calculate which frames in the received video correspond to loss period
        # Use received video timing
        rx_loss_start_frame = int(loss_start_s * rx_fps)
        rx_loss_end_frame = int(loss_end_s * rx_fps)
        
        # Clamp to actual received frames
        rx_loss_start_frame = max(0, rx_loss_start_frame)
        rx_loss_end_frame = min(rx_total_frames - 1, rx_loss_end_frame)
        
        print(f"  RX frame range for loss: {rx_loss_start_frame} - {rx_loss_end_frame}")
        
        # For reference video, use the same time range but with reference FPS
        ref_loss_start_frame = int(loss_start_s * ref_fps)
        ref_loss_end_frame = int(loss_end_s * ref_fps)
        
        print(f"  REF frame range for loss: {ref_loss_start_frame} - {ref_loss_end_frame}")
        
        ssim_values = []
        
        # Read frames and calculate SSIM for the loss period
        # We'll iterate through the received video frames in the loss period
        for rx_frame_idx in range(rx_loss_start_frame, rx_loss_end_frame + 1):
            # Set position in received video
            cap_rx.set(cv2.CAP_PROP_POS_FRAMES, rx_frame_idx)
            ret_rx, frame_rx = cap_rx.read()
            
            if not ret_rx:
                break
            
            # Calculate corresponding reference frame
            # Map received frame time to reference frame
            rx_time_s = rx_frame_idx / rx_fps
            ref_frame_idx = int(rx_time_s * ref_fps)
            
            # Set position in reference video
            cap_ref.set(cv2.CAP_PROP_POS_FRAMES, ref_frame_idx)
            ret_ref, frame_ref = cap_ref.read()
            
            if not ret_ref:
                break
            
            # Convert to grayscale and resize to match
            ref_gray = cv2.cvtColor(frame_ref, cv2.COLOR_BGR2GRAY)
            rx_gray = cv2.cvtColor(frame_rx, cv2.COLOR_BGR2GRAY)
            
            # Resize received frame to match reference if needed
            if ref_gray.shape != rx_gray.shape:
                rx_gray = cv2.resize(rx_gray, (ref_gray.shape[1], ref_gray.shape[0]))
            
            # Calculate SSIM
            ssim_value = ssim(ref_gray, rx_gray, data_range=255)
            ssim_values.append(ssim_value)
        
        cap_ref.release()
        cap_rx.release()
        
        print(f"  Calculated {len(ssim_values)} SSIM values (based on received frames)")
        return ssim_values
        
    except Exception as e:
        print(f"Error calculating SSIM: {e}")
        return []

# Plotting functions
def plot_bitrate_over_time(bitrate_data: List[Dict], gcc_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot comprehensive bitrate analysis: OUT, IN, As, Ar, GCC over time with loss markers."""
    if not bitrate_data:
        return
        
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    
    plt.figure(figsize=(15, 10))
    
    # Plot all 4 bitrates
    plt.subplot(2, 1, 1)
    
    # Define colors and labels for the 4 bitrates
    bitrate_configs = [
        ('client_sent_bitrate_mbps', 'blue', 'CLIENT SENT'),
        ('server_received_bitrate_mbps', 'green', 'SERVER RECEIVED'),
        ('server_sent_bitrate_mbps', 'orange', 'SERVER SENT'),
        ('client_received_bitrate_mbps', 'red', 'CLIENT RECEIVED')
    ]
    
    for field, color, label in bitrate_configs:
        if any(field in d for d in bitrate_data):
            bitrates = [d.get(field, 0) for d in bitrate_data]
            plt.plot(times_rel, bitrates, color=color, linewidth=2, label=label, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.ylabel('Bitrate (Mbps)')
    plt.title('All 4 Bitrates (Client/Server Send/Receive)')
    plt.ylim(0, 5)  # Set y-axis limit to 5 Mbps
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Plot GCC-level estimates (As, Ar, GCC)
    plt.subplot(2, 1, 2)
    
    if gcc_data:
        gcc_t0 = gcc_data[0]['timestamp_s']
        gcc_times_rel = [(d['timestamp_s'] - gcc_t0) for d in gcc_data]
        
        # Extract non-None values for each estimate
        as_values = [(t, d['as_mbps']) for t, d in zip(gcc_times_rel, gcc_data) if d['as_mbps'] is not None]
        ar_values = [(t, d['ar_mbps']) for t, d in zip(gcc_times_rel, gcc_data) if d['ar_mbps'] is not None]
        gcc_values = [(t, d['gcc_mbps']) for t, d in zip(gcc_times_rel, gcc_data) if d['gcc_mbps'] is not None]
        
        if as_values:
            as_times, as_bitrates = zip(*as_values)
            plt.plot(as_times, as_bitrates, 'orange', linewidth=2, label='As (Loss-based)', alpha=0.8, marker='o', markersize=3)
        
        if ar_values:
            ar_times, ar_bitrates = zip(*ar_values)
            plt.plot(ar_times, ar_bitrates, 'purple', linewidth=2, label='Ar (REMB)', alpha=0.8, marker='s', markersize=3)
        
        if gcc_values:
            gcc_times, gcc_bitrates = zip(*gcc_values)
            plt.plot(gcc_times, gcc_bitrates, 'red', linewidth=3, label='GCC (Combined)', alpha=0.9, marker='^', markersize=4)
    
    # Add loss period markers to second plot too
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        # Adjust for different t0 if needed
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - (gcc_data[0]['timestamp_s'] if gcc_data else t0)
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - (gcc_data[0]['timestamp_s'] if gcc_data else t0)
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('GCC Congestion Control Estimates')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = output_dir / "comprehensive_bitrate_analysis.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Comprehensive bitrate plot saved: {output_path}")

def plot_utilization_boxplot(utilizations: List[float], output_dir: Path):
    """Plot bandwidth utilization box plot with 95th, 75th, 25th, 5th percentiles, median, and mean."""
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Create box plot with custom style
    ax.boxplot([utilizations], labels=['During Loss'], positions=[1], showmeans=True, showfliers=False, widths=0.5,
               capprops={'linewidth': 1.5}, whis=(5, 95), 
               meanprops={'linewidth': 1.5, 'marker': 'o', 'markersize': 8, 'markerfacecolor': 'blue'},
               medianprops={'linewidth': 1.5, 'color': 'red'}, 
               boxprops={'linewidth': 1.0})
    
    ax.set_ylabel('Bandwidth Utilization (%)')
    ax.set_title('Bandwidth Utilization Distribution\n(5th, 25th, 50th, 75th, 95th percentiles, median=red, mean=blue dots)')
    ax.grid(True, alpha=0.3)
    
    output_path = output_dir / "utilization_boxplot.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Utilization plot saved: {output_path}")

def plot_comprehensive_utilization_boxplot(all_utilizations: Dict[str, List[float]], output_dir: Path):
    """Plot comprehensive bandwidth utilization box plot for all 4 bitrate types."""
    if not all_utilizations:
        return
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Prepare data for box plot
    labels = list(all_utilizations.keys())
    data = list(all_utilizations.values())
    
    # Create box plot with custom style
    ax.boxplot(data, labels=labels, showmeans=True, showfliers=False, widths=0.6,
               capprops={'linewidth': 1.5}, whis=(5, 95), 
               meanprops={'linewidth': 1.5, 'marker': 'o', 'markersize': 8, 'markerfacecolor': 'blue'},
               medianprops={'linewidth': 1.5, 'color': 'red'}, 
               boxprops={'linewidth': 1.0})
    
    ax.set_ylabel('Bandwidth Utilization (%)')
    ax.set_title('Comprehensive Bandwidth Utilization Analysis\n(All 7 Types During Loss Period)')
    ax.grid(True, alpha=0.3)
    
    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45, ha='right')
    
    plt.tight_layout()
    output_path = output_dir / "comprehensive_utilization_boxplot.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Comprehensive utilization plot saved: {output_path}")

def plot_out_bitrate_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot OUT bitrate over time with loss area highlighted."""
    if not bitrate_data:
        return
        
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    out_bitrates = [d['out_bitrate_mbps'] for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    
    # Plot OUT bitrate
    plt.plot(times_rel, out_bitrates, 'b-', linewidth=2, label='OUT Bitrate (Sent)', alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8, label='Loss Start')
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8, label='Loss End')
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red', label='Loss Period')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('OUT Bitrate Over Time\n(Application Layer - Sent Bitrate)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = output_dir / "out_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"OUT bitrate plot saved: {output_path}")

def plot_in_bitrate_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot IN bitrate over time with loss area highlighted."""
    if not bitrate_data:
        return
        
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    in_bitrates = [d['in_bitrate_mbps'] for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    
    # Plot IN bitrate
    plt.plot(times_rel, in_bitrates, 'g-', linewidth=2, label='IN Bitrate (Received)', alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8, label='Loss Start')
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8, label='Loss End')
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red', label='Loss Period')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('IN Bitrate Over Time\n(Application Layer - Received Bitrate)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = output_dir / "in_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"IN bitrate plot saved: {output_path}")

def plot_as_bitrate_over_time(gcc_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot As bitrate over time with loss area highlighted."""
    if not gcc_data:
        return
        
    # Filter out None values for As
    as_data = [(d['timestamp_s'], d['as_mbps']) for d in gcc_data if d.get('as_mbps') is not None]
    if not as_data:
        return
        
    t0 = as_data[0][0]
    times_rel = [(t - t0) for t, _ in as_data]
    as_bitrates = [b for _, b in as_data]
    
    plt.figure(figsize=(12, 6))
    
    # Plot As bitrate
    plt.plot(times_rel, as_bitrates, 'orange', linewidth=2, label='As (Loss-based)', alpha=0.8, marker='o', markersize=3)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8, label='Loss Start')
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8, label='Loss End')
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red', label='Loss Period')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('As Bitrate Over Time\n(GCC Loss-based Estimate)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = output_dir / "as_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"As bitrate plot saved: {output_path}")

def plot_ar_bitrate_over_time(gcc_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot Ar bitrate over time with loss area highlighted."""
    if not gcc_data:
        return
        
    # Filter out None values for Ar
    ar_data = [(d['timestamp_s'], d['ar_mbps']) for d in gcc_data if d.get('ar_mbps') is not None]
    if not ar_data:
        return
        
    t0 = ar_data[0][0]
    times_rel = [(t - t0) for t, _ in ar_data]
    ar_bitrates = [b for _, b in ar_data]
    
    plt.figure(figsize=(12, 6))
    
    # Plot Ar bitrate
    plt.plot(times_rel, ar_bitrates, 'purple', linewidth=2, label='Ar (REMB)', alpha=0.8, marker='s', markersize=3)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8, label='Loss Start')
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8, label='Loss End')
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red', label='Loss Period')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('Ar Bitrate Over Time\n(GCC REMB Feedback Estimate)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = output_dir / "ar_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Ar bitrate plot saved: {output_path}")

def plot_gcc_bitrate_over_time(gcc_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot GCC bitrate over time with loss area highlighted."""
    if not gcc_data:
        return
        
    # Filter out None values for GCC
    gcc_bitrate_data = [(d['timestamp_s'], d['gcc_mbps']) for d in gcc_data if d.get('gcc_mbps') is not None]
    if not gcc_bitrate_data:
        return
        
    t0 = gcc_bitrate_data[0][0]
    times_rel = [(t - t0) for t, _ in gcc_bitrate_data]
    gcc_bitrates = [b for _, b in gcc_bitrate_data]
    
    plt.figure(figsize=(12, 6))
    
    # Plot GCC bitrate
    plt.plot(times_rel, gcc_bitrates, 'red', linewidth=3, label='GCC (Combined)', alpha=0.9, marker='^', markersize=4)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8, label='Loss Start')
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8, label='Loss End')
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red', label='Loss Period')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('GCC Bitrate Over Time\n(GCC Combined Target Estimate)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = output_dir / "gcc_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"GCC bitrate plot saved: {output_path}")

def plot_ssim_boxplot(ssim_values: List[float], output_dir: Path):
    """Plot SSIM box plot with 95th, 75th, 25th, 5th percentiles, median, and mean."""
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Create box plot with custom style
    ax.boxplot([ssim_values], labels=['During Loss'], positions=[1], showmeans=True, showfliers=False, widths=0.5,
               capprops={'linewidth': 1.5}, whis=(5, 95), 
               meanprops={'linewidth': 1.5, 'marker': 'o', 'markersize': 8, 'markerfacecolor': 'blue'},
               medianprops={'linewidth': 1.5, 'color': 'red'}, 
               boxprops={'linewidth': 1.0})
    
    ax.set_ylabel('SSIM')
    ax.set_title('Video Quality (SSIM) Distribution\n(5th, 25th, 50th, 75th, 95th percentiles, median=red, mean=blue dots)')
    ax.grid(True, alpha=0.3)
    
    output_path = output_dir / "ssim_boxplot.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"SSIM plot saved: {output_path}")

def plot_fps_boxplot(fps_values: List[float], output_dir: Path, endpoint_name: str = "FPS", fps_field: str = None):
    """Plot FPS box plot for a specific endpoint."""
    if not fps_values:
        return
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Create box plot with custom style
    ax.boxplot([fps_values], labels=['During Loss'], positions=[1], showmeans=True, showfliers=False, widths=0.5,
               capprops={'linewidth': 1.5}, whis=(5, 95), 
               meanprops={'linewidth': 1.5, 'marker': 'o', 'markersize': 8, 'markerfacecolor': 'blue'},
               medianprops={'linewidth': 1.5, 'color': 'red'}, 
               boxprops={'linewidth': 1.0})
    
    ax.set_ylabel('FPS')
    ax.set_title(f'{endpoint_name} Distribution During Loss\n(5th, 25th, 50th, 75th, 95th percentiles, median=red, mean=blue dots)')
    ax.grid(True, alpha=0.3)
    
    # Use consistent naming: server_sent_fps_boxplot.png, client_sent_fps_boxplot.png, etc.
    if fps_field:
        filename = fps_field.replace('_fps', '_fps_boxplot')
    else:
        filename = endpoint_name.lower().replace(' ', '_') + '_fps_boxplot'
    output_path = output_dir / f"{filename}.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"{endpoint_name} box plot saved: {output_path}")

def plot_fps_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path, fps_field: str, endpoint_name: str):
    """Plot FPS over time for a specific endpoint."""
    if not bitrate_data:
        return
    
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    fps_values = [d.get(fps_field, 0) for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    plt.plot(times_rel, fps_values, 'b-', linewidth=2, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('FPS')
    plt.title(f'{endpoint_name} FPS Over Time')
    plt.grid(True, alpha=0.3)
    
    # Use consistent naming: server_sent_fps_over_time.png, client_sent_fps_over_time.png, etc.
    filename = fps_field.replace('_fps', '_fps_over_time')
    output_path = output_dir / f"{filename}.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"{endpoint_name} FPS time series plot saved: {output_path}")

def plot_ssim_over_time(ssim_values: List[float], timing_info: Dict, output_dir: Path):
    """Plot SSIM over time."""
    if not ssim_values:
        return
    
    # SSIM values are stored as simple array, so we need to create timestamps
    # Based on the loss period and number of SSIM samples
    loss_start_ms = timing_info['loss_start']['timestamp_ms']
    loss_end_ms = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_ms + 60000)
    
    # Create timestamps for SSIM values (evenly spaced during loss period)
    loss_duration_ms = loss_end_ms - loss_start_ms
    timestamps = []
    for i in range(len(ssim_values)):
        # Distribute SSIM values evenly across the loss period
        timestamp_ms = loss_start_ms + (i / len(ssim_values)) * loss_duration_ms
        timestamps.append(timestamp_ms / 1000.0)  # Convert to seconds
    
    # Normalize timestamps to start from 0
    t0 = timestamps[0]
    times_rel = [t - t0 for t in timestamps]
    
    plt.figure(figsize=(12, 6))
    plt.plot(times_rel, ssim_values, 'g-', linewidth=2, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('SSIM')
    plt.title('SSIM Over Time (During Loss Period)')
    plt.ylim(0, 1)
    plt.grid(True, alpha=0.3)
    
    output_path = output_dir / "ssim_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"SSIM time series plot saved: {output_path}")

def print_comprehensive_results(results: Dict, result_type: str, title: str):
    """Print comprehensive analysis results for all 5 bitrate types."""
    if result_type not in results:
        return
    
    comp_results = results[result_type]
    print(f"\n{title.upper()}:")
    
    # Handle error cases
    if 'error' in comp_results:
        print(f"  Error: {comp_results['error']}")
        return
    
    bitrate_types = [
        ('client_sent_bitrate_mbps', 'CLIENT SENT'),
        ('server_received_bitrate_mbps', 'SERVER RECEIVED'),
        ('server_sent_bitrate_mbps', 'SERVER SENT'),
        ('client_received_bitrate_mbps', 'CLIENT RECEIVED'),
        ('as_estimate', 'As (Loss-based)'),
        ('ar_estimate', 'Ar (REMB)'),
        ('gcc_combined', 'GCC (Combined)')
    ]
    
    for key, name in bitrate_types:
        if key in comp_results:
            data = comp_results[key]
            if result_type == 'utilization':
                print(f"  {name}:")
                print(f"    Reference: {data['reference_bitrate_mbps']:.2f} Mbps ({data['reference_samples']} samples)")
                if 'analysis_delay_s' in data:
                    print(f"    Loss samples: {data['utilization_samples']} (starting {data['analysis_delay_s']:.1f}s after loss begins)")
                else:
                    print(f"    Loss samples: {data['utilization_samples']} (starting from loss begin)")
                if 'percentiles' in data:
                    p = data['percentiles']
                    print(f"    Utilization: P5={p['p5']:.1f}%, P25={p['p25']:.1f}%, P50={p['p50']:.1f}%, P75={p['p75']:.1f}%, P95={p['p95']:.1f}%")
                    print(f"    Mean: {p['mean']:.1f}%, Min: {p['min']:.1f}%, Max: {p['max']:.1f}%")
            elif result_type == 'recovery':
                print(f"  {name}:")
                print(f"    Reference: {data['reference_bitrate_mbps']:.2f} Mbps")
                recovery_time = data['recovery_time_s']
                if recovery_time is not None:
                    print(f"    Recovery time: {recovery_time:.1f}s (to {data['recovery_threshold']*100:.0f}% of reference)")
                else:
                    print(f"    Recovery time: No recovery detected within analysis window")

def save_metric_values(results: Dict, args, bitrate_data: List[Dict], gcc_data: List[Dict], timing_info: Dict, exp_dir: Path):
    """Save individual metric values to JSON files for aggregation."""
    if not args.store_values:
        return
    
    # Create values directory
    values_dir = args.output_dir / "values"
    values_dir.mkdir(exist_ok=True)
    
    # Save bitrate data (all bitrate values over time) - separate files for each type
    if bitrate_data:
        # Extract CLIENT SENT bitrate values
        client_sent_bitrate_values = []
        for d in bitrate_data:
            if d.get('client_sent_bitrate_mbps') is not None:
                client_sent_bitrate_values.append({
                    'timestamp_s': d['timestamp_s'],
                    'bitrate_mbps': d['client_sent_bitrate_mbps']
                })
        
        with open(values_dir / "bitrate_client_sent.json", 'w') as f:
            json.dump(client_sent_bitrate_values, f, indent=2)
        print(f"Saved CLIENT SENT bitrate values to: {values_dir / 'bitrate_client_sent.json'}")
        
        # Extract SERVER RECEIVED bitrate values
        server_received_bitrate_values = []
        for d in bitrate_data:
            if d.get('server_received_bitrate_mbps') is not None:
                server_received_bitrate_values.append({
                    'timestamp_s': d['timestamp_s'],
                    'bitrate_mbps': d['server_received_bitrate_mbps']
                })
        
        with open(values_dir / "bitrate_server_received.json", 'w') as f:
            json.dump(server_received_bitrate_values, f, indent=2)
        print(f"Saved SERVER RECEIVED bitrate values to: {values_dir / 'bitrate_server_received.json'}")
        
        # Extract SERVER SENT bitrate values
        server_sent_bitrate_values = []
        for d in bitrate_data:
            if d.get('server_sent_bitrate_mbps') is not None:
                server_sent_bitrate_values.append({
                    'timestamp_s': d['timestamp_s'],
                    'bitrate_mbps': d['server_sent_bitrate_mbps']
                })
        
        with open(values_dir / "bitrate_server_sent.json", 'w') as f:
            json.dump(server_sent_bitrate_values, f, indent=2)
        print(f"Saved SERVER SENT bitrate values to: {values_dir / 'bitrate_server_sent.json'}")
        
        # Extract CLIENT RECEIVED bitrate values
        client_received_bitrate_values = []
        for d in bitrate_data:
            if d.get('client_received_bitrate_mbps') is not None:
                client_received_bitrate_values.append({
                    'timestamp_s': d['timestamp_s'],
                    'bitrate_mbps': d['client_received_bitrate_mbps']
                })
        
        with open(values_dir / "bitrate_client_received.json", 'w') as f:
            json.dump(client_received_bitrate_values, f, indent=2)
        print(f"Saved CLIENT RECEIVED bitrate values to: {values_dir / 'bitrate_client_received.json'}")
        
        # Extract GCC estimates if available
        if gcc_data:
            # As bitrate values
            as_bitrate_values = []
            for d in gcc_data:
                if d.get('as_mbps') is not None:
                    as_bitrate_values.append({
                        'timestamp_s': d['timestamp_s'],
                        'bitrate_mbps': d['as_mbps']
                    })
            
            with open(values_dir / "bitrate_as.json", 'w') as f:
                json.dump(as_bitrate_values, f, indent=2)
            print(f"Saved As bitrate values to: {values_dir / 'bitrate_as.json'}")
            
            # Ar bitrate values
            ar_bitrate_values = []
            for d in gcc_data:
                if d.get('ar_mbps') is not None:
                    ar_bitrate_values.append({
                        'timestamp_s': d['timestamp_s'],
                        'bitrate_mbps': d['ar_mbps']
                    })
            
            with open(values_dir / "bitrate_ar.json", 'w') as f:
                json.dump(ar_bitrate_values, f, indent=2)
            print(f"Saved Ar bitrate values to: {values_dir / 'bitrate_ar.json'}")
            
            # GCC bitrate values
            gcc_bitrate_values = []
            for d in gcc_data:
                if d.get('gcc_mbps') is not None:
                    gcc_bitrate_values.append({
                        'timestamp_s': d['timestamp_s'],
                        'bitrate_mbps': d['gcc_mbps']
                    })
            
            with open(values_dir / "bitrate_gcc.json", 'w') as f:
                json.dump(gcc_bitrate_values, f, indent=2)
            print(f"Saved GCC bitrate values to: {values_dir / 'bitrate_gcc.json'}")
    
    # Save utilization values
    if 'utilization' in results:
        util_results = results['utilization']
        
        # CLIENT SENT bitrate utilization
        if 'client_sent_bitrate_mbps' in util_results and 'percentiles' in util_results['client_sent_bitrate_mbps']:
            # Extract individual utilization values from the analysis
            client_sent_util_values = extract_utilization_values(bitrate_data, timing_info, 'client_sent_bitrate_mbps', args)
            with open(values_dir / "util_client_sent.json", 'w') as f:
                json.dump(client_sent_util_values, f, indent=2)
            print(f"Saved CLIENT SENT utilization values to: {values_dir / 'util_client_sent.json'}")
        
        # SERVER RECEIVED bitrate utilization
        if 'server_received_bitrate_mbps' in util_results and 'percentiles' in util_results['server_received_bitrate_mbps']:
            server_received_util_values = extract_utilization_values(bitrate_data, timing_info, 'server_received_bitrate_mbps', args)
            with open(values_dir / "util_server_received.json", 'w') as f:
                json.dump(server_received_util_values, f, indent=2)
            print(f"Saved SERVER RECEIVED utilization values to: {values_dir / 'util_server_received.json'}")
        
        # SERVER SENT bitrate utilization
        if 'server_sent_bitrate_mbps' in util_results and 'percentiles' in util_results['server_sent_bitrate_mbps']:
            server_sent_util_values = extract_utilization_values(bitrate_data, timing_info, 'server_sent_bitrate_mbps', args)
            with open(values_dir / "util_server_sent.json", 'w') as f:
                json.dump(server_sent_util_values, f, indent=2)
            print(f"Saved SERVER SENT utilization values to: {values_dir / 'util_server_sent.json'}")
        
        # CLIENT RECEIVED bitrate utilization
        if 'client_received_bitrate_mbps' in util_results and 'percentiles' in util_results['client_received_bitrate_mbps']:
            client_received_util_values = extract_utilization_values(bitrate_data, timing_info, 'client_received_bitrate_mbps', args)
            with open(values_dir / "util_client_received.json", 'w') as f:
                json.dump(client_received_util_values, f, indent=2)
            print(f"Saved CLIENT RECEIVED utilization values to: {values_dir / 'util_client_received.json'}")
        
        # GCC estimates utilization
        if gcc_data:
            if 'as_estimate' in util_results and 'percentiles' in util_results['as_estimate']:
                as_util_values = extract_gcc_utilization_values(gcc_data, timing_info, 'as_mbps')
                with open(values_dir / "util_as.json", 'w') as f:
                    json.dump(as_util_values, f, indent=2)
                print(f"Saved As utilization values to: {values_dir / 'util_as.json'}")
            
            if 'ar_estimate' in util_results and 'percentiles' in util_results['ar_estimate']:
                ar_util_values = extract_gcc_utilization_values(gcc_data, timing_info, 'ar_mbps')
                with open(values_dir / "util_ar.json", 'w') as f:
                    json.dump(ar_util_values, f, indent=2)
                print(f"Saved Ar utilization values to: {values_dir / 'util_ar.json'}")
            
            if 'gcc_combined' in util_results and 'percentiles' in util_results['gcc_combined']:
                gcc_util_values = extract_gcc_utilization_values(gcc_data, timing_info, 'gcc_mbps')
                with open(values_dir / "util_gcc.json", 'w') as f:
                    json.dump(gcc_util_values, f, indent=2)
                print(f"Saved GCC utilization values to: {values_dir / 'util_gcc.json'}")
    
    # Save recovery values
    if 'recovery' in results:
        rec_results = results['recovery']
        
        # CLIENT SENT bitrate recovery
        if 'client_sent_bitrate_mbps' in rec_results:
            client_sent_recovery = rec_results['client_sent_bitrate_mbps'].get('recovery_time_s')
            with open(values_dir / "recovery_client_sent.json", 'w') as f:
                json.dump([client_sent_recovery] if client_sent_recovery is not None else [], f, indent=2)
            print(f"Saved CLIENT SENT recovery value to: {values_dir / 'recovery_client_sent.json'}")
        
        # SERVER RECEIVED bitrate recovery
        if 'server_received_bitrate_mbps' in rec_results:
            server_received_recovery = rec_results['server_received_bitrate_mbps'].get('recovery_time_s')
            with open(values_dir / "recovery_server_received.json", 'w') as f:
                json.dump([server_received_recovery] if server_received_recovery is not None else [], f, indent=2)
            print(f"Saved SERVER RECEIVED recovery value to: {values_dir / 'recovery_server_received.json'}")
        
        # SERVER SENT bitrate recovery
        if 'server_sent_bitrate_mbps' in rec_results:
            server_sent_recovery = rec_results['server_sent_bitrate_mbps'].get('recovery_time_s')
            with open(values_dir / "recovery_server_sent.json", 'w') as f:
                json.dump([server_sent_recovery] if server_sent_recovery is not None else [], f, indent=2)
            print(f"Saved SERVER SENT recovery value to: {values_dir / 'recovery_server_sent.json'}")
        
        # CLIENT RECEIVED bitrate recovery
        if 'client_received_bitrate_mbps' in rec_results:
            client_received_recovery = rec_results['client_received_bitrate_mbps'].get('recovery_time_s')
            with open(values_dir / "recovery_client_received.json", 'w') as f:
                json.dump([client_received_recovery] if client_received_recovery is not None else [], f, indent=2)
            print(f"Saved CLIENT RECEIVED recovery value to: {values_dir / 'recovery_client_received.json'}")
        
        # GCC estimates recovery
        if gcc_data:
            if 'as_estimate' in rec_results:
                as_recovery = rec_results['as_estimate'].get('recovery_time_s')
                with open(values_dir / "recovery_as.json", 'w') as f:
                    json.dump([as_recovery] if as_recovery is not None else [], f, indent=2)
                print(f"Saved As recovery value to: {values_dir / 'recovery_as.json'}")
            
            if 'ar_estimate' in rec_results:
                ar_recovery = rec_results['ar_estimate'].get('recovery_time_s')
                with open(values_dir / "recovery_ar.json", 'w') as f:
                    json.dump([ar_recovery] if ar_recovery is not None else [], f, indent=2)
                print(f"Saved Ar recovery value to: {values_dir / 'recovery_ar.json'}")
            
            if 'gcc_combined' in rec_results:
                gcc_recovery = rec_results['gcc_combined'].get('recovery_time_s')
                with open(values_dir / "recovery_gcc.json", 'w') as f:
                    json.dump([gcc_recovery] if gcc_recovery is not None else [], f, indent=2)
                print(f"Saved GCC recovery value to: {values_dir / 'recovery_gcc.json'}")
    
    # Save SSIM values (reuse from results if available)
    if 'ssim' in results and 'error' not in results['ssim'] and 'values' in results['ssim']:
        ssim_values = results['ssim']['values']
        with open(values_dir / "ssim.json", 'w') as f:
            json.dump(ssim_values, f, indent=2)
        print(f"Saved SSIM values to: {values_dir / 'ssim.json'}")
    elif 'ssim' in results and 'error' not in results['ssim']:
        # Only calculate if not already done
        ssim_values = extract_ssim_values(exp_dir, timing_info, bitrate_data)
        if ssim_values:
            with open(values_dir / "ssim.json", 'w') as f:
                json.dump(ssim_values, f, indent=2)
            print(f"Saved SSIM values to: {values_dir / 'ssim.json'}")
    
    # Save FPS values for all four endpoints
    if 'fps' in results:
        # Save main FPS values (client received)
        fps_values = extract_fps_values(bitrate_data, timing_info)
        if fps_values:
            with open(values_dir / "fps.json", 'w') as f:
                json.dump(fps_values, f, indent=2)
            print(f"Saved FPS values to: {values_dir / 'fps.json'}")
        
        # Save FPS values for all four endpoints
        fps_endpoints = [
            ('client_sent_fps', 'fps_client_sent'),
            ('server_received_fps', 'fps_server_received'),
            ('server_sent_fps', 'fps_server_sent'),
            ('client_received_fps', 'fps_client_received')
        ]
        
        for fps_field, filename in fps_endpoints:
            fps_values = extract_fps_values_for_endpoint(bitrate_data, timing_info, fps_field)
            if fps_values:
                with open(values_dir / f"{filename}.json", 'w') as f:
                    json.dump(fps_values, f, indent=2)
                print(f"Saved {filename} values to: {values_dir / f'{filename}.json'}")
    
    # Save H264 failure rate
    if 'h264' in results and 'error' not in results['h264']:
        failure_rate = results['h264'].get('failure_rate_percent', 0.0)
        with open(values_dir / "h264_failure_rate.json", 'w') as f:
            json.dump([failure_rate], f, indent=2)
        print(f"Saved H264 failure rate to: {values_dir / 'h264_failure_rate.json'}")

def extract_utilization_values(bitrate_data: List[Dict], timing_info: Dict, bitrate_field: str, args = None) -> List[float]:
    """Extract utilization values for a specific bitrate field."""
    if 'loss_start' not in timing_info or not bitrate_data:
        return []
    
    loss_start_s = timing_info['loss_start']['timestamp_ms'] / 1000.0
    loss_end_s = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_s + 60) / 1000.0
    
    t0 = bitrate_data[0]['timestamp_s']
    
    # Determine analysis start time
    if bitrate_field == 'out_bitrate_mbps' and args and args.analysis_delay is not None:
        # For OUT bitrate with analysis delay, use time-based delay
        analysis_start_s = loss_start_s + args.analysis_delay
    else:
        # For other bitrates or no delay, start from loss start
        analysis_start_s = loss_start_s
    
    analysis_start_rel = analysis_start_s - t0
    loss_end_rel = loss_end_s - t0
    
    # Get reference bitrate
    ref_bitrate, _ = calculate_reference_bitrate(bitrate_data, loss_start_s, bitrate_field)
    if ref_bitrate <= 0:
        return []
    
    # Extract utilization values
    utilizations = []
    for d in bitrate_data:
        timestamp_rel = d['timestamp_s'] - t0
        if analysis_start_rel <= timestamp_rel <= loss_end_rel and d.get(bitrate_field) is not None:
            utilization = d[bitrate_field] / ref_bitrate
            utilizations.append(min(utilization * 100, 100.0))
    
    return utilizations

def extract_gcc_utilization_values(gcc_data: List[Dict], timing_info: Dict, bitrate_field: str) -> List[float]:
    """Extract utilization values for GCC estimates."""
    if 'loss_start' not in timing_info or not gcc_data:
        return []
    
    loss_start_s = timing_info['loss_start']['timestamp_ms'] / 1000.0
    loss_end_s = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_s + 60) / 1000.0
    
    gcc_t0 = gcc_data[0]['timestamp_s']
    # GCC estimates always start from loss start (no delay)
    analysis_start_rel = loss_start_s - gcc_t0
    loss_end_rel = loss_end_s - gcc_t0
    
    # Get reference bitrate
    ref_bitrate, _ = calculate_reference_bitrate(gcc_data, loss_start_s, bitrate_field)
    if ref_bitrate <= 0:
        return []
    
    # Extract utilization values
    utilizations = []
    for d in gcc_data:
        timestamp_rel = d['timestamp_s'] - gcc_t0
        if analysis_start_rel <= timestamp_rel <= loss_end_rel and d.get(bitrate_field) is not None:
            utilization = d[bitrate_field] / ref_bitrate
            utilizations.append(min(utilization * 100, 100.0))
    
    return utilizations

def extract_ssim_values(exp_dir: Path, timing_info: Dict, bitrate_data: List[Dict]) -> List[float]:
    """Extract SSIM values from video analysis."""
    if 'loss_start' not in timing_info or not bitrate_data:
        return []
    
    loss_start_ms = timing_info['loss_start']['timestamp_ms']
    loss_end_ms = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_ms + 60000)
    
    try:
        video_dir = exp_dir / "videos"
        if not video_dir.exists():
            return []
        
        # Find received video
        received_video = None
        for video_file in video_dir.glob("*.mp4"):
            received_video = video_file
            break
        
        if not received_video:
            return []
        
        # Find reference video
        reference_video = Path("long_video_for_testing.mp4")
        if not reference_video.exists():
            return []
        
        # Calculate relative timing using bitrate data
        t0 = bitrate_data[0]['timestamp_s']
        loss_start_s = loss_start_ms / 1000.0
        loss_end_s = loss_end_ms / 1000.0
        
        # Convert to relative time from video start
        video_loss_start_s = loss_start_s - t0
        video_loss_end_s = loss_end_s - t0
        
        ssim_values = calculate_video_ssim_values(reference_video, received_video, 
                                                video_loss_start_s, video_loss_end_s)
        
        return ssim_values if ssim_values else []
        
    except Exception as e:
        return []

def extract_fps_values(bitrate_data: List[Dict], timing_info: Dict) -> List[float]:
    """Extract FPS values during loss period."""
    if not bitrate_data or 'loss_start' not in timing_info:
        return []
    
    loss_start_ms = timing_info['loss_start']['timestamp_ms']
    loss_end_ms = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_ms + 60000)
    
    # Extract client received FPS during loss (start from loss start)
    fps_values = []
    for entry in bitrate_data:
        timestamp_ms = entry['timestamp_s'] * 1000
        if loss_start_ms <= timestamp_ms <= loss_end_ms:
            fps = entry.get('client_received_fps', 0)  # Use client received FPS
            if fps > 0:
                fps_values.append(fps)
    
    return fps_values

def extract_fps_values_for_endpoint(bitrate_data: List[Dict], timing_info: Dict, fps_field: str) -> List[float]:
    """Extract FPS values for a specific endpoint."""
    if not bitrate_data or 'loss_start' not in timing_info:
        return []
    
    loss_start_ms = timing_info['loss_start']['timestamp_ms']
    loss_end_ms = timing_info.get('loss_end', {}).get('timestamp_ms', loss_start_ms + 60000)
    
    fps_values = []
    for entry in bitrate_data:
        timestamp_ms = entry['timestamp_s'] * 1000
        if loss_start_ms <= timestamp_ms <= loss_end_ms:
            fps = entry.get(fps_field, 0)
            if fps > 0:
                fps_values.append(fps)
    
    return fps_values

def print_results(results: Dict, args):
    """Print analysis results to terminal."""
    print("\n" + "="*60)
    print("GCC PERFORMANCE ANALYSIS RESULTS")
    print("(Analysis starts from loss begin, except OUT bitrate utilization which may use overshoot detection)")
    print("="*60)
    
    # Bitrate analysis removed - now using utilization analysis below
    
    if 'recovery' in results:
        rec = results['recovery']
        if rec.get('recovery_time_s'):
            print(f"\nRECOVERY ANALYSIS:")
            print(f"  Recovery time: {rec['recovery_time_s']:.1f}s")
            print(f"  Threshold: {rec['recovery_threshold']*100}% of reference")
        else:
            print(f"\nRECOVERY ANALYSIS:")
            print(f"  Recovery time: >experiment duration")
    
    if 'ssim' in results:
        ssim_res = results['ssim']
        if 'error' in ssim_res:
            print(f"\nSSIM ANALYSIS:")
            print(f"  Error: {ssim_res['error']}")
        else:
            print(f"\nSSIM ANALYSIS:")
            print(f"  Samples: {ssim_res['ssim_samples']}")
            if 'percentiles' in ssim_res:
                p = ssim_res['percentiles']
                print(f"  Percentiles: P5={p['p5']:.3f}, P25={p['p25']:.3f}, P50={p['p50']:.3f}, P75={p['p75']:.3f}, P95={p['p95']:.3f}")
                print(f"  Mean: {p['mean']:.3f}, Min: {p['min']:.3f}, Max: {p['max']:.3f}")
    
    if 'fps' in results:
        fps_res = results['fps']
        print(f"\nFPS ANALYSIS:")
        if 'reference_fps' in fps_res:
            print(f"  Reference FPS: {fps_res['reference_fps']} (from 5s before loss, used as cap)")
        print(f"  Loss samples: {fps_res['fps_samples']} (starting from loss begin)")
        print(f"  Note: All FPS values capped at reference FPS to show realistic performance")
        if 'percentiles' in fps_res:
            p = fps_res['percentiles']
            print(f"  Percentiles: P5={p['p5']:.1f}, P25={p['p25']:.1f}, P50={p['p50']:.1f}, P75={p['p75']:.1f}, P95={p['p95']:.1f}")
            print(f"  Mean: {p['mean']:.1f}, Min: {p['min']:.1f}, Max: {p['max']:.1f}")
        
        # Print all four endpoints if available
        if 'all_endpoints' in fps_res:
            print(f"  All endpoints analysis:")
            for endpoint, data in fps_res['all_endpoints'].items():
                if 'fps_samples' in data and data['fps_samples'] > 0:
                    endpoint_name = endpoint.replace('_', ' ').title()
                    print(f"    {endpoint_name}: {data['fps_samples']} samples")
                    if 'percentiles' in data:
                        p = data['percentiles']
                        print(f"      Mean: {p['mean']:.1f}, Min: {p['min']:.1f}, Max: {p['max']:.1f}")
    
    if 'h264' in results:
        h264_res = results['h264']
        if 'error' in h264_res:
            print(f"\nH264 DECODE ANALYSIS:")
            print(f"  Error: {h264_res['error']}")
        else:
            print(f"\nH264 DECODE ANALYSIS:")
            print(f"  Failures: {h264_res['total_failures']}/{h264_res.get('total_attempts', 'N/A')}")
            print(f"  Failure rate: {h264_res['failure_rate_percent']:.1f}%")
    
    # Print comprehensive analysis results
    print_comprehensive_results(results, 'utilization', 'Utilization Analysis (All 7 Types)')
    print_comprehensive_results(results, 'recovery', 'Recovery Analysis (All 7 Types)')

def plot_client_sent_bitrate_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot CLIENT SENT bitrate over time."""
    if not bitrate_data:
        return
    
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    client_sent_bitrates = [d.get('client_sent_bitrate_mbps', 0) for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    plt.plot(times_rel, client_sent_bitrates, 'b-', linewidth=2, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('CLIENT SENT Bitrate Over Time')
    plt.ylim(0, 5)  # Set y-axis limit to 5 Mbps
    plt.grid(True, alpha=0.3)
    
    output_path = output_dir / "client_sent_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"CLIENT SENT bitrate plot saved: {output_path}")

def plot_server_received_bitrate_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot SERVER RECEIVED bitrate over time."""
    if not bitrate_data:
        return
    
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    server_received_bitrates = [d.get('server_received_bitrate_mbps', 0) for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    plt.plot(times_rel, server_received_bitrates, 'g-', linewidth=2, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('SERVER RECEIVED Bitrate Over Time')
    plt.ylim(0, 5)  # Set y-axis limit to 5 Mbps
    plt.grid(True, alpha=0.3)
    
    output_path = output_dir / "server_received_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"SERVER RECEIVED bitrate plot saved: {output_path}")

def plot_server_sent_bitrate_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot SERVER SENT bitrate over time."""
    if not bitrate_data:
        return
    
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    server_sent_bitrates = [d.get('server_sent_bitrate_mbps', 0) for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    plt.plot(times_rel, server_sent_bitrates, 'orange', linewidth=2, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('SERVER SENT Bitrate Over Time')
    plt.ylim(0, 5)  # Set y-axis limit to 5 Mbps
    plt.grid(True, alpha=0.3)
    
    output_path = output_dir / "server_sent_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"SERVER SENT bitrate plot saved: {output_path}")

def plot_client_received_bitrate_over_time(bitrate_data: List[Dict], timing_info: Dict, output_dir: Path):
    """Plot CLIENT RECEIVED bitrate over time."""
    if not bitrate_data:
        return
    
    t0 = bitrate_data[0]['timestamp_s']
    times_rel = [(d['timestamp_s'] - t0) for d in bitrate_data]
    client_received_bitrates = [d.get('client_received_bitrate_mbps', 0) for d in bitrate_data]
    
    plt.figure(figsize=(12, 6))
    plt.plot(times_rel, client_received_bitrates, 'red', linewidth=2, alpha=0.8)
    
    # Add loss period markers
    if 'loss_start' in timing_info and 'loss_end' in timing_info:
        loss_start_rel = (timing_info['loss_start']['timestamp_ms'] / 1000.0) - t0
        loss_end_rel = (timing_info['loss_end']['timestamp_ms'] / 1000.0) - t0
        
        plt.axvline(x=loss_start_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvline(x=loss_end_rel, color='r', linestyle='-', alpha=0.8)
        plt.axvspan(loss_start_rel, loss_end_rel, alpha=0.2, color='red')
    
    plt.xlabel('Time (seconds)')
    plt.ylabel('Bitrate (Mbps)')
    plt.title('CLIENT RECEIVED Bitrate Over Time')
    plt.ylim(0, 5)  # Set y-axis limit to 5 Mbps
    plt.grid(True, alpha=0.3)
    
    output_path = output_dir / "client_received_bitrate_over_time.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"CLIENT RECEIVED bitrate plot saved: {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description='GCC Performance Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('experiment_dir', help='Path to experiment directory')
    
    # Analysis options
    parser.add_argument('--bitrate', action='store_true', help='Analyze all 5 bitrate types over time: OUT (sent), IN (received), As (loss-based), Ar (REMB), GCC (combined)')
    parser.add_argument('--utilization', action='store_true', help='Analyze bandwidth utilization for all 5 bitrate types during loss')
    parser.add_argument('--recovery', action='store_true', help='Analyze recovery time for all 5 bitrate types')
    parser.add_argument('--ssim', action='store_true', help='Analyze video quality (SSIM) during loss')
    parser.add_argument('--fps', action='store_true', help='Analyze FPS during loss')
    parser.add_argument('--h264', action='store_true', help='Analyze H264 decode failures')
    parser.add_argument('--all', action='store_true', help='Run all analyses')
    parser.add_argument('--no-ssim', action='store_true', help='Exclude SSIM analysis when using --all (faster execution)')
    
    # Output options
    parser.add_argument('--plot', action='store_true', help='Generate plots for applicable metrics')
    parser.add_argument('--no-percentiles', action='store_true', help='Skip percentile calculations (faster)')
    parser.add_argument('--output', '-o', default=None, help='Output directory for results and plots')
    parser.add_argument('--store-values', action='store_true', help='Store individual metric values to JSON files for aggregation')
    parser.add_argument('--analysis-delay', nargs='?', const=ANALYSIS_DELAY_S, type=float, 
                       metavar='SECONDS', help=f'Analysis delay for OUT bitrate utilization (seconds, default: {ANALYSIS_DELAY_S})')
    
    args = parser.parse_args()
    
    # Validate experiment directory
    exp_dir = Path(args.experiment_dir)
    if not exp_dir.exists():
        print(f"Experiment directory not found: {exp_dir}")
        return 1
    
    # Set output directory
    if args.output:
        args.output_dir = Path(args.output)
    else:
        args.output_dir = exp_dir / "analysis"
    args.output_dir.mkdir(exist_ok=True)
    
    # If no specific analysis requested, default to all
    if not any([args.bitrate, args.utilization, args.recovery, args.ssim, args.fps, args.h264, args.all]):
        args.all = True
    
    # Set analysis flags
    if args.all:
        args.bitrate = args.utilization = args.recovery = args.fps = args.h264 = True
        # Only enable SSIM if --no-ssim is not specified
        if not args.no_ssim:
            args.ssim = True
    
    # Find required files
    client_stats_file = exp_dir / "logs" / "stats.log"
    timing_file = exp_dir / "packet_loss_timing.log"
    if not timing_file.exists():
        timing_file = exp_dir / "logs" / "packet_loss_timing.log"
    
    if not client_stats_file.exists():
        print(f"Client stats file not found: {client_stats_file}")
        return 1
    
    # Parse data
    print("Loading experiment data...")
    bitrate_data = parse_client_stats(str(client_stats_file))
    timing_info = parse_loss_timing(str(timing_file))
    
    # Load experiment info to get max_as_bitrate
    experiment_info = {}
    experiment_info_file = exp_dir / "experiment_info.json"
    if experiment_info_file.exists():
        with open(experiment_info_file, 'r') as f:
            experiment_info = json.load(f)
    
    # Load GCC estimates if available
    gcc_estimates_file = exp_dir / "logs" / "gcc_estimates.log"
    gcc_data = parse_gcc_estimates(str(gcc_estimates_file))
    
    if not bitrate_data:
        print("No bitrate data found")
        return 1
    
    # Run analyses
    results = {}
    
    # Generate individual bitrate plots if --plot is requested
    if args.plot:
        print("Generating comprehensive bitrate plot...")
        if gcc_data:
            plot_as_bitrate_over_time(gcc_data, timing_info, args.output_dir)
            plot_ar_bitrate_over_time(gcc_data, timing_info, args.output_dir)
            plot_gcc_bitrate_over_time(gcc_data, timing_info, args.output_dir)
        
        # Generate separate plots for each of the 4 bitrates
        print("Generating separate bitrate plots...")
        plot_client_sent_bitrate_over_time(bitrate_data, timing_info, args.output_dir)
        plot_server_received_bitrate_over_time(bitrate_data, timing_info, args.output_dir)
        plot_server_sent_bitrate_over_time(bitrate_data, timing_info, args.output_dir)
        plot_client_received_bitrate_over_time(bitrate_data, timing_info, args.output_dir)
    
    if args.bitrate:
        print("Analyzing bitrate (all 7 types)...")
        print("  • CLIENT SENT: Bitrate sent by client")
        print("  • SERVER RECEIVED: Bitrate received by server")
        print("  • SERVER SENT: Bitrate sent by server")
        print("  • CLIENT RECEIVED: Bitrate received by client")
        print("  • As: Loss-based estimate (GCC congestion control)")
        print("  • Ar: REMB feedback estimate (GCC congestion control)")
        print("  • GCC: Combined target = min(As, Ar) (GCC congestion control)")
        # Store bitrate analysis for internal use but don't include in final results
        bitrate_analysis = analyze_bitrate(bitrate_data, gcc_data, timing_info, args)
    
    if args.utilization:
        print("Analyzing utilization (all 7 types)...")
        print("  Reference: 10 seconds before loss | Analysis: During loss (from loss start)")
        results['utilization'] = analyze_comprehensive_utilization(bitrate_data, gcc_data, timing_info, experiment_info, args)
    
    if args.recovery:
        print("Analyzing recovery (all 7 types)...")
        print("  Recovery: Time to reach 100% of reference after loss ends")
        results['recovery'] = analyze_comprehensive_recovery(bitrate_data, gcc_data, timing_info, args)
    
    if args.ssim:
        print("Analyzing SSIM...")
        results['ssim'] = analyze_ssim(exp_dir, timing_info, bitrate_data, args)
    
    if args.fps:
        print("Analyzing FPS...")
        results['fps'] = analyze_fps(bitrate_data, timing_info, args)
    
    if args.h264:
        print("Analyzing H264 failures...")
        results['h264'] = analyze_h264_failures(exp_dir, timing_info, args)
    
    # Print results
    print_results(results, args)
    
    # Save individual metric values if requested
    save_metric_values(results, args, bitrate_data, gcc_data, timing_info, exp_dir)
    
    # Save results (without bitrate section)
    results_file = args.output_dir / "gcc_analysis_results.json"
    results['analysis_info'] = {
        'experiment_dir': str(exp_dir),
        'timestamp': datetime.now().isoformat(),
        'analyses_run': [k for k in results.keys() if k != 'analysis_info']
    }
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    
    return 0

if __name__ == "__main__":
    exit(main())