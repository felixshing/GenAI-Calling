import re
import matplotlib.pyplot as plt
import numpy as np
from typing import Optional, Dict, List
from config_32inchs import plot,FONT_SIZE,LABEL_SIZE,LEGEND_FONT_SIZE,LINE_WIDTH,colors,marker,marker_size,line_styles
def parse_shell_array(script_content: str, array_name: str) -> list[float]:
    """
    Parses a bash array definition from a string and returns a list of floats.
    Example: `arr=(1 2.5 3)` -> `[1.0, 2.5, 3.0]`
    """
    # Regex to find the array assignment, capturing the content inside parentheses
    match = re.search(rf'{array_name}=\((.*?)\)', script_content, re.DOTALL)
    if not match:
        return []
    
    # Extract content, remove newlines, and split by space
    content = match.group(1).replace('\n', ' ').strip()
    return [float(x) for x in content.split()]

def get_trace_data(script_path: str) -> dict:
    """
    Parses the cellular_emulation.sh script to extract traces for different conditions.
    """
    try:
        with open(script_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: Script '{script_path}' not found.")
        return {}

    # Split the script content by the 'elif' conditions to isolate each block
    conditions = content.split('elif [ "$2" ==')
    
    data = {}
    
    # Process "good" condition from the first block
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

def calculate_and_print_statistics(trace_data: Dict, duration_limit_s: Optional[int] = None):
    """
    Calculates and prints key statistics for each trace.
    If duration_limit_s is provided, it analyzes only up to that time.
    """
    header_text = f"Trace Statistics (Full Trace)" if duration_limit_s is None else f"Trace Statistics (First {duration_limit_s} Seconds)"
    
    print("\n" + "="*95)
    print(header_text)
    print("="*95)
    print(f"{'Condition':<12} | {'# Loss Events':<15} | {'Avg. Time Between Loss (s)':<28} | {'Avg. Loss %':<14} | {'Max Loss %':<12} | {'Std. Loss %':<12}")
    print("-" * 95)

    for condition, data in trace_data.items():
        gaps = data['gaps']
        losses = data['loss']
        
        event_times = np.cumsum(gaps)
        
        # If a duration limit is set, filter the data accordingly
        if duration_limit_s is not None:
            indices_within_limit = np.where(event_times <= duration_limit_s)[0]
            
            if len(indices_within_limit) == 0:
                print(f"{condition.capitalize():<12} | {'0':<15} | {'N/A':<28} | {'0.0':<14} | {'0.0':<12} | {'0.0':<12}")
                continue

            filtered_gaps = np.array(gaps)[indices_within_limit]
            filtered_losses = np.array(losses)[indices_within_limit]
        else:
            # Use the entire trace if no limit is set
            filtered_gaps = np.array(gaps)
            filtered_losses = np.array(losses)
        
        num_events = len(filtered_losses)
        avg_gap = np.mean(filtered_gaps) if num_events > 0 else 0
        avg_loss = np.mean(filtered_losses) if num_events > 0 else 0
        max_loss = np.max(filtered_losses) if num_events > 0 else 0
        std_loss = np.std(filtered_losses) if num_events > 0 else 0

        print(f"{condition.capitalize():<12} | {num_events:<15} | {avg_gap:<28.2f} | {avg_loss:<14.2f} | {max_loss:<12.2f} | {std_loss:<12.2f}")
    print("="*95)


def plot_loss_profiles(trace_data: dict):
    """
    Generates and saves a plot of the loss rate over time for each condition.
    """
    if not trace_data:
        print("No trace data to plot.")
        return

    # Create a figure with 3 subplots, one for each condition
    # fig, axes = plt.subplots(3, 1, figsize=(15, 12), sharex=True)
    fig, ax1 = plt.subplots()
    #fig.suptitle('Simulated Cellular Packet Loss Profiles', fontsize=18, weight='bold')

    #conditions_to_plot = ['good', 'median', 'poor']
    conditions_to_plot = ['good']
    #colors = {'good': 'green', 'median': 'orange', 'poor': 'red'}

    for i, condition in enumerate(conditions_to_plot):
        if condition in trace_data:
            ax = ax1
            gaps = trace_data[condition]['gaps']
            losses = trace_data[condition]['loss']
            
            # Calculate cumulative time for the x-axis (when loss events occur)
            event_times = np.cumsum(gaps)
            total_duration = event_times[-1]

            # Extend the trace to 300 seconds by looping through the data
            target_duration = 300.0
            extended_times = []
            extended_losses = []
            
            current_time = 0
            cycle_count = 0
            
            while current_time < target_duration:
                for i, (gap, loss) in enumerate(zip(gaps, losses)):
                    if current_time + gap > target_duration:
                        break
                    
                    current_time += gap
                    extended_times.append(current_time)
                    extended_losses.append(loss)
                
                cycle_count += 1
                if cycle_count > 100:  # Safety break to prevent infinite loops
                    break

            # Plot raw trace data exactly as it exists
            plot_times = extended_times
            plot_losses = extended_losses

            
            
            ax.plot(plot_times, plot_losses, color='blue', linewidth=4)
            
            #ax.set_title(f'"{condition.capitalize()}" Condition (Total Duration: {total_duration:.1f}s)', fontsize=14)
            #ax.set_ylabel('Loss Rate (%)')
            # ax.grid(True, linestyle=':', alpha=0.6)
            # ax.set_ylim(bottom=0)

    ax1.set_xlabel('Time (seconds)')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.tick_params(axis='x', labelsize=90)
    ax1.tick_params(axis='y', labelsize=90)
    #ax1.set_xlim(0, 62)
    ax.set_ylim(bottom=0)
    #ax1.set_xticks([30,60,90])
    #ax1.set_xticks([20,40,60])
    ax1.set_yticks([0,20,40,60,80,100])
    ax1.set_xlabel('Time (s)', fontsize=90)
    ax1.set_ylabel('Loss Rate (%)', fontsize=90)
    ax1.set_xticks([50,100,150,200,250,300])
    ax1.set_xlim(0, 301)
    ax1.set_ylim(0, 101)
    # plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    # output_filename = 'cellular_loss_profiles.png'
    # plt.savefig(output_filename, dpi=150)
    # print(f"\nPlot saved to '{output_filename}'")
    plt.show()

if __name__ == "__main__":
    # Path to the emulation script
    emulation_script_path = 'celluar_emulation.sh'
    
    # Parse the script and get the data
    trace_data = get_trace_data(emulation_script_path)
    
    if trace_data:
        # Calculate and print statistics for the ENTIRE trace
        calculate_and_print_statistics(trace_data, duration_limit_s=None)
        
        # Calculate and print statistics for the FIRST 90 SECONDS
        #calculate_and_print_statistics(trace_data, duration_limit_s=90)
        
        # Plot the loss profiles
        plot_loss_profiles(trace_data)