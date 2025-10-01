
#!/usr/bin/env python3
"""
Analyze Cellular Trace Statistics

This script analyzes the cellular trace data from cell-emulation-util
to understand loss patterns and extract the first 90 seconds for our RTT testbed.
"""

import re
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple

def parse_shell_array(script_content: str, array_name: str) -> List[float]:
    """Parse a bash array definition from script content"""
    match = re.search(rf'{array_name}=\((.*?)\)', script_content, re.DOTALL)
    if not match:
        return []
    
    content = match.group(1).replace('\n', ' ').strip()
    return [float(x) for x in content.split()]

def get_trace_data(script_path: str) -> Dict:
    """Extract trace data from cellular_emulation.sh"""
    with open(script_path, 'r') as f:
        content = f.read()

    # Split by conditions
    conditions = content.split('elif [ "$2" ==')
    
    data = {}
    
    # Process "good" condition from first block
    good_block = conditions[0]
    data['good'] = {
        'gaps': parse_shell_array(good_block, 'gap_array'),
        'loss': parse_shell_array(good_block, 'loss_array')
    }
    
    # Process other conditions
    for block in conditions[1:]:
        if '"median"' in block:
            data['median'] = {
                'gaps': parse_shell_array(block, 'gap_array'),
                'loss': parse_shell_array(block, 'loss_array')
            }
        elif '"poor"' in block:
            data['poor'] = {
                'gaps': parse_shell_array(block, 'gap_array'),
                'loss': parse_shell_array(block, 'loss_array')
            }
            
    return data

def analyze_trace_statistics(trace_data: Dict) -> None:
    """Analyze and compare trace statistics"""
    
    print("CELLULAR TRACE ANALYSIS")
    print("=" * 60)
    
    for condition in ['good', 'median', 'poor']:
        if condition in trace_data:
            gaps = trace_data[condition]['gaps']
            losses = trace_data[condition]['loss']
            
            # Calculate cycle duration (one full cycle through the arrays)
            cycle_duration = sum(gaps)
            
            # Loss statistics
            avg_loss = np.mean(losses)
            max_loss = np.max(losses)
            min_loss = np.min(losses)
            std_loss = np.std(losses)
            
            # Loss event statistics
            high_loss_events = sum(1 for l in losses if l > 50)
            medium_loss_events = sum(1 for l in losses if 20 <= l <= 50)
            low_loss_events = sum(1 for l in losses if l < 20)
            
            print(f"\n{condition.upper()} CONDITION:")
            print(f"  Cycle Duration: {cycle_duration:.1f}s")
            print(f"  Loss Events: {len(losses)}")
            print(f"  Loss Statistics:")
            print(f"    Average: {avg_loss:.1f}%")
            print(f"    Max: {max_loss:.1f}%")
            print(f"    Min: {min_loss:.1f}%")
            print(f"    Std Dev: {std_loss:.1f}%")
            print(f"  Loss Event Distribution:")
            print(f"    High Loss (>50%): {high_loss_events} events")
            print(f"    Medium Loss (20-50%): {medium_loss_events} events")
            print(f"    Low Loss (<20%): {low_loss_events} events")

def extract_90s_trace(trace_data: Dict, condition: str) -> Tuple[List[float], List[float]]:
    """Extract first 90 seconds of loss events from a trace"""
    gaps = trace_data[condition]['gaps']
    losses = trace_data[condition]['loss']
    
    extracted_gaps = []
    extracted_losses = []
    cumulative_time = 0.0
    
    i = 0
    while cumulative_time < 90.0 and i < len(gaps):
        gap_time = gaps[i]
        
        if cumulative_time + gap_time <= 90.0:
            # Full gap fits within 90s
            extracted_gaps.append(gap_time)
            extracted_losses.append(losses[i])
            cumulative_time += gap_time
        else:
            # Partial gap to reach exactly 90s
            remaining_time = 90.0 - cumulative_time
            if remaining_time > 0.1:  # Only add if significant time remains
                extracted_gaps.append(remaining_time)
                extracted_losses.append(losses[i])
            break
        
        i += 1
    
    return extracted_gaps, extracted_losses

def create_90s_cellular_traces() -> Dict:
    """Create 90-second cellular traces for our testbed"""
    
    # Load original trace data
    script_path = 'celluar_emulation.sh'
    original_traces = get_trace_data(script_path)
    
    # Extract 90s for each condition
    traces_90s = {}
    
    print("\nEXTRACTING 90-SECOND TRACES FOR TESTBED")
    print("=" * 60)
    
    for condition in ['good', 'median', 'poor']:
        if condition in original_traces:
            gaps_90s, losses_90s = extract_90s_trace(original_traces, condition)
            
            traces_90s[condition] = {
                'gaps': gaps_90s,
                'loss': losses_90s
            }
            
            total_duration = sum(gaps_90s)
            avg_loss = np.mean(losses_90s)
            max_loss = np.max(losses_90s)
            
            print(f"\n{condition.upper()} (90s extract):")
            print(f"  Duration: {total_duration:.1f}s")
            print(f"  Events: {len(losses_90s)}")
            print(f"  Avg Loss: {avg_loss:.1f}%")
            print(f"  Max Loss: {max_loss:.1f}%")
    
    return traces_90s

def extract_450s_trace(trace_data: Dict, condition: str) -> Tuple[List[float], List[float]]:
    """Extract first 450 seconds of loss events from a trace"""
    gaps = trace_data[condition]['gaps']
    losses = trace_data[condition]['loss']
    
    extracted_gaps = []
    extracted_losses = []
    cumulative_time = 0.0
    
    i = 0
    while cumulative_time < 450.0 and i < len(gaps):
        gap_time = gaps[i]
        
        if cumulative_time + gap_time <= 450.0:
            # Full gap fits within 450s
            extracted_gaps.append(gap_time)
            extracted_losses.append(losses[i])
            cumulative_time += gap_time
        else:
            # Partial gap to reach exactly 450s
            remaining_time = 450.0 - cumulative_time
            if remaining_time > 0.1:  # Only add if significant time remains
                extracted_gaps.append(remaining_time)
                extracted_losses.append(losses[i])
            break
        
        i += 1
    
    return extracted_gaps, extracted_losses

def create_450s_cellular_traces() -> Dict:
    """Create 450-second cellular traces for extended analysis"""
    
    # Load original trace data
    script_path = 'celluar_emulation.sh'
    original_traces = get_trace_data(script_path)
    
    # Extract 450s for each condition
    traces_450s = {}
    
    print("\nEXTRACTING 450-SECOND TRACES FOR EXTENDED ANALYSIS")
    print("=" * 60)
    
    for condition in ['good', 'median', 'poor']:
        if condition in original_traces:
            gaps_450s, losses_450s = extract_450s_trace(original_traces, condition)
            
            traces_450s[condition] = {
                'gaps': gaps_450s,
                'loss': losses_450s
            }
            
            total_duration = sum(gaps_450s)
            avg_loss = np.mean(losses_450s)
            max_loss = np.max(losses_450s)
            
            print(f"\n{condition.upper()} (450s extract):")
            print(f"  Duration: {total_duration:.1f}s")
            print(f"  Events: {len(losses_450s)}")
            print(f"  Avg Loss: {avg_loss:.1f}%")
            print(f"  Max Loss: {max_loss:.1f}%")
    
    return traces_450s

def plot_90s_comparison(original_traces: Dict, traces_90s: Dict) -> None:
    """Plot comparison between original and 90s extracted traces"""
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('Cellular Trace Comparison: Original vs 90s Extract', fontsize=16)
    
    conditions = ['good', 'median', 'poor']
    colors = {'good': 'green', 'median': 'orange', 'poor': 'red'}
    
    for i, condition in enumerate(conditions):
        # Original trace (top row)
        ax_orig = axes[0, i]
        gaps_orig = original_traces[condition]['gaps']
        losses_orig = original_traces[condition]['loss']
        
        time_points_orig = []
        loss_points_orig = []
        current_time = 0
        
        for gap, loss in zip(gaps_orig, losses_orig):
            # Gap period (no loss)
            time_points_orig.extend([current_time, current_time + gap])
            loss_points_orig.extend([0, 0])
            # Loss event (assume 0.1s duration)
            time_points_orig.extend([current_time + gap, current_time + gap + 0.1])
            loss_points_orig.extend([loss, loss])
            current_time += gap + 0.1
        
        ax_orig.plot(time_points_orig, loss_points_orig, color=colors[condition], linewidth=1)
        ax_orig.set_xlim(0, 90)
        ax_orig.set_title(f'Original {condition.capitalize()} (showing first 90s)')
        ax_orig.set_ylabel('Loss Rate (%)')
        ax_orig.grid(True, alpha=0.3)
        ax_orig.set_ylim(0, 100)
        
        # 90s extract (bottom row)
        ax_90s = axes[1, i]
        gaps_90s = traces_90s[condition]['gaps']
        losses_90s = traces_90s[condition]['loss']
        
        time_points_90s = []
        loss_points_90s = []
        current_time = 0
        
        for gap, loss in zip(gaps_90s, losses_90s):
            # Gap period (no loss)
            time_points_90s.extend([current_time, current_time + gap])
            loss_points_90s.extend([0, 0])
            # Loss event
            time_points_90s.extend([current_time + gap, current_time + gap + 0.1])
            loss_points_90s.extend([loss, loss])
            current_time += gap + 0.1
        
        ax_90s.plot(time_points_90s, loss_points_90s, color=colors[condition], linewidth=1)
        ax_90s.set_xlim(0, 90)
        ax_90s.set_title(f'90s Extract {condition.capitalize()}')
        ax_90s.set_xlabel('Time (s)')
        ax_90s.set_ylabel('Loss Rate (%)')
        ax_90s.grid(True, alpha=0.3)
        ax_90s.set_ylim(0, 100)
        
        # Add statistics
        avg_loss_90s = np.mean(losses_90s)
        max_loss_90s = np.max(losses_90s)
        ax_90s.text(0.02, 0.98, f'Events: {len(losses_90s)}\nAvg: {avg_loss_90s:.1f}%\nMax: {max_loss_90s:.1f}%', 
                    transform=ax_90s.transAxes, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig('cellular_90s_comparison.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    print(f"\nComparison plot saved to 'cellular_90s_comparison.png'")

def plot_450s_comparison(original_traces: Dict, traces_450s: Dict) -> None:
    """Plot comparison between original and 450s extracted traces"""
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('Cellular Trace Comparison: Original vs 450s Extract', fontsize=16)
    
    conditions = ['good', 'median', 'poor']
    colors = {'good': 'green', 'median': 'orange', 'poor': 'red'}
    
    for i, condition in enumerate(conditions):
        # Original trace (top row)
        ax_orig = axes[0, i]
        gaps_orig = original_traces[condition]['gaps']
        losses_orig = original_traces[condition]['loss']
        
        time_points_orig = []
        loss_points_orig = []
        current_time = 0
        
        for gap, loss in zip(gaps_orig, losses_orig):
            # Gap period (no loss)
            time_points_orig.extend([current_time, current_time + gap])
            loss_points_orig.extend([0, 0])
            # Loss event (assume 0.1s duration)
            time_points_orig.extend([current_time + gap, current_time + gap + 0.1])
            loss_points_orig.extend([loss, loss])
            current_time += gap + 0.1
        
        ax_orig.plot(time_points_orig, loss_points_orig, color=colors[condition], linewidth=1)
        ax_orig.set_xlim(0, 450)
        ax_orig.set_title(f'Original {condition.capitalize()} (showing first 450s)')
        ax_orig.set_ylabel('Loss Rate (%)')
        ax_orig.grid(True, alpha=0.3)
        ax_orig.set_ylim(0, 100)
        
        # 450s extract (bottom row)
        ax_450s = axes[1, i]
        gaps_450s = traces_450s[condition]['gaps']
        losses_450s = traces_450s[condition]['loss']
        
        time_points_450s = []
        loss_points_450s = []
        current_time = 0
        
        for gap, loss in zip(gaps_450s, losses_450s):
            # Gap period (no loss)
            time_points_450s.extend([current_time, current_time + gap])
            loss_points_450s.extend([0, 0])
            # Loss event
            time_points_450s.extend([current_time + gap, current_time + gap + 0.1])
            loss_points_450s.extend([loss, loss])
            current_time += gap + 0.1
        
        ax_450s.plot(time_points_450s, loss_points_450s, color=colors[condition], linewidth=1)
        ax_450s.set_xlim(0, 450)
        ax_450s.set_title(f'450s Extract {condition.capitalize()}')
        ax_450s.set_xlabel('Time (s)')
        ax_450s.set_ylabel('Loss Rate (%)')
        ax_450s.grid(True, alpha=0.3)
        ax_450s.set_ylim(0, 100)
        
        # Add statistics
        avg_loss_450s = np.mean(losses_450s)
        max_loss_450s = np.max(losses_450s)
        ax_450s.text(0.02, 0.98, f'Events: {len(losses_450s)}\nAvg: {avg_loss_450s:.1f}%\nMax: {max_loss_450s:.1f}%', 
                    transform=ax_450s.transAxes, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig('cellular_450s_comparison.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    print(f"\nComparison plot saved to 'cellular_450s_comparison.png'")

def compare_conditions(traces_90s: Dict) -> None:
    """Compare the three conditions statistically"""
    
    print("\nSTATISTICAL COMPARISON OF CONDITIONS")
    print("=" * 60)
    
    conditions = ['good', 'median', 'poor']
    stats = {}
    
    for condition in conditions:
        losses = traces_90s[condition]['loss']
        stats[condition] = {
            'mean': np.mean(losses),
            'std': np.std(losses),
            'max': np.max(losses),
            'min': np.min(losses),
            'events': len(losses),
            'high_loss_ratio': sum(1 for l in losses if l > 50) / len(losses)
        }
    
    print(f"{'Metric':<15} {'Good':<10} {'Median':<10} {'Poor':<10}")
    print("-" * 50)
    print(f"{'Mean Loss %':<15} {stats['good']['mean']:<10.1f} {stats['median']['mean']:<10.1f} {stats['poor']['mean']:<10.1f}")
    print(f"{'Std Dev %':<15} {stats['good']['std']:<10.1f} {stats['median']['std']:<10.1f} {stats['poor']['std']:<10.1f}")
    print(f"{'Max Loss %':<15} {stats['good']['max']:<10.1f} {stats['median']['max']:<10.1f} {stats['poor']['max']:<10.1f}")
    print(f"{'Events':<15} {stats['good']['events']:<10} {stats['median']['events']:<10} {stats['poor']['events']:<10}")
    print(f"{'High Loss Ratio':<15} {stats['good']['high_loss_ratio']:<10.2f} {stats['median']['high_loss_ratio']:<10.2f} {stats['poor']['high_loss_ratio']:<10.2f}")
    
    # Similarity analysis
    print(f"\nCONDITION SIMILARITY ANALYSIS:")
    median_poor_mean_diff = abs(stats['median']['mean'] - stats['poor']['mean'])
    median_poor_std_diff = abs(stats['median']['std'] - stats['poor']['std'])
    
    good_median_mean_diff = abs(stats['good']['mean'] - stats['median']['mean'])
    good_poor_mean_diff = abs(stats['good']['mean'] - stats['poor']['mean'])
    
    print(f"  Median vs Poor mean difference: {median_poor_mean_diff:.1f}%")
    print(f"  Good vs Median mean difference: {good_median_mean_diff:.1f}%")
    print(f"  Good vs Poor mean difference: {good_poor_mean_diff:.1f}%")
    
    if median_poor_mean_diff < 10:
        print(f"  Median and Poor conditions are quite similar!")
    else:
        print(f"  ✓ All conditions are sufficiently distinct")

def main():
    """Main analysis function"""
    
    print("Cellular Trace Analysis for RTT Testbed")
    print("=" * 60)
    
    # Load and analyze original traces
    script_path = 'celluar_emulation.sh'
    original_traces = get_trace_data(script_path)
    
    # Full trace analysis
    analyze_trace_statistics(original_traces)
    
    # Extract 90s traces
    traces_90s = create_90s_cellular_traces()
    
    # Extract 450s traces
    traces_450s = create_450s_cellular_traces()
    
    # Compare conditions for 90s
    compare_conditions(traces_90s)
    
    # Compare conditions for 450s
    print(f"\nSTATISTICAL COMPARISON OF 450S CONDITIONS")
    print("=" * 60)
    compare_conditions(traces_450s)
    
    # Plot comparisons
    plot_90s_comparison(original_traces, traces_90s)
    plot_450s_comparison(original_traces, traces_450s)
    
    # Export 90s traces for testbed
    print(f"\nEXPORTING 90S TRACES FOR TESTBED")
    print("=" * 60)
    
    with open('cellular_traces_90s.py', 'w') as f:
        f.write("# 90-second cellular traces extracted from cell-emulation-util\n")
        f.write("# Timeline: 10s baseline + 90s trace + 30s recovery = 130s total\n\n")
        f.write("CELLULAR_TRACES_90S = {\n")
        
        for condition in ['good', 'median', 'poor']:
            f.write(f"    '{condition}': {{\n")
            f.write(f"        'gaps': {traces_90s[condition]['gaps']},\n")
            f.write(f"        'loss': {traces_90s[condition]['loss']}\n")
            f.write(f"    }},\n")
        
        f.write("}\n")
    
    # Export 450s traces
    print(f"\nEXPORTING 450S TRACES FOR EXTENDED ANALYSIS")
    print("=" * 60)
    
    with open('cellular_traces_450s.py', 'w') as f:
        f.write("# 450-second cellular traces extracted from cell-emulation-util\n")
        f.write("# Extended analysis for longer duration testing\n\n")
        f.write("CELLULAR_TRACES_450S = {\n")
        
        for condition in ['good', 'median', 'poor']:
            f.write(f"    '{condition}': {{\n")
            f.write(f"        'gaps': {traces_450s[condition]['gaps']},\n")
            f.write(f"        'loss': {traces_450s[condition]['loss']}\n")
            f.write(f"    }},\n")
        
        f.write("}\n")
    
    print("✓ Exported to 'cellular_traces_90s.py'")
    print("✓ Exported to 'cellular_traces_450s.py'")
    print("✓ Ready for integration into RTT testbed!")

if __name__ == "__main__":
    main() 
