#!/usr/bin/env python3

import re
from typing import Dict, List


def parse_shell_array(script_content: str, array_name: str) -> List[float]:
    match = re.search(rf"{array_name}=\((.*?)\)", script_content, re.DOTALL)
    if not match:
        return []
    content = match.group(1).replace('\n', ' ').strip()
    return [float(x) for x in content.split()] if content else []


def get_trace_data(script_path: str) -> Dict[str, Dict[str, List[float]]]:
    try:
        with open(script_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: Script '{script_path}' not found.")
        return {}

    conditions = content.split('elif [ "$2" ==')

    data: Dict[str, Dict[str, List[float]]] = {}

    # first block is the default (good)
    good_block = conditions[0]
    data['good'] = {
        'gaps': parse_shell_array(good_block, 'gap_array'),
        'loss': parse_shell_array(good_block, 'loss_array'),
    }

    for block in conditions[1:]:
        if '"median"' in block:
            data['median'] = {
                'gaps': parse_shell_array(block, 'gap_array'),
                'loss': parse_shell_array(block, 'loss_array'),
            }
        elif '"poor"' in block:
            data['poor'] = {
                'gaps': parse_shell_array(block, 'gap_array'),
                'loss': parse_shell_array(block, 'loss_array'),
            }

    return data


def compute_fps_from_loss(loss_values: List[float]) -> List[float]:
    # FPS = 30 * (1 - loss_rate)
    # loss_values are percentages (0-100)
    return [30.0 * (1.0 - (lv / 100.0)) for lv in loss_values]


def main():
    # Hairpin: import raw loss data
    try:
        from plot_hairpin_traces import HAIRPIN_TRACE
        hairpin_loss = HAIRPIN_TRACE['loss']
    except Exception as e:
        print(f"Error loading hairpin trace: {e}")
        hairpin_loss = []

    hairpin_fps = compute_fps_from_loss(hairpin_loss)[:100]

    # Akamai (good): parse from shell script in the same folder
    akamai_script = 'celluar_emulation.sh'
    akamai_data = get_trace_data(akamai_script)
    akamai_good_loss = akamai_data.get('good', {}).get('loss', [])
    akamai_good_fps = compute_fps_from_loss(akamai_good_loss)[:100]

    # Print lists as Python literals
    print('hairpin_fps =', hairpin_fps)
    print('akamai_good_fps =', akamai_good_fps)


if __name__ == '__main__':
    main()

