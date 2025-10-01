#!/usr/bin/env python3
"""
Rename experiment folder to include loss conditions.
"""

import argparse
import json
import os
import shutil
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Rename experiment folder with loss conditions')
    parser.add_argument('experiment_dir', help='Path to experiment directory')
    
    args = parser.parse_args()
    
    exp_dir = Path(args.experiment_dir)
    if not exp_dir.exists():
        print(f"Experiment directory not found: {exp_dir}")
        return 1
    
    # Check for loss config
    loss_config_file = exp_dir / "logs" / "loss_config.json"
    if not loss_config_file.exists():
        print(f"No loss config found, keeping original name: {exp_dir}")
        return 0
    
    # Read loss config
    with open(loss_config_file, 'r') as f:
        loss_config = json.load(f)
    
    # Extract current folder name parts
    folder_name = exp_dir.name
    name_parts = folder_name.split('_')
    
    if len(name_parts) >= 3:
        # Format: gcc-v0_20250815_175438
        base_name = name_parts[0]  # 'gcc-v0'
        timestamp_parts = name_parts[1:]  # ['20250815', '175438']
        
        # Create new name with loss conditions
        profile = loss_config.get('profile', 'unknown')
        rtt = loss_config.get('rtt_ms', 0)
        duration = loss_config.get('duration_s', 0)
        
        new_name = f"{base_name}_{profile}_rtt{rtt}_dur{duration}_{timestamp_parts[0]}_{timestamp_parts[1]}"
        new_path = exp_dir.parent / new_name
        
        if new_path.exists():
            print(f"Target path already exists: {new_path}")
            return 1
        
        # Rename the directory
        shutil.move(str(exp_dir), str(new_path))
        print(f"Renamed experiment folder:")
        print(f"  From: {exp_dir}")
        print(f"  To:   {new_path}")
        
        return 0
    else:
        print(f"Cannot parse folder name format: {folder_name}")
        return 1

if __name__ == "__main__":
    exit(main())