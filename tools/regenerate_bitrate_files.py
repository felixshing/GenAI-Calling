#!/usr/bin/env python3
"""
Regenerate bitrate files for all experiment folders
"""

import subprocess
import sys
from pathlib import Path

def main():
    experiments_dir = Path("experiments")
    
    # Find all experiment folders
    experiment_folders = []
    for item in experiments_dir.iterdir():
        if item.is_dir() and item.name.startswith('gcc-v0_akamai_median_rtt'):
            experiment_folders.append(item)
    
    print(f"Found {len(experiment_folders)} experiment folders")
    
    # Run gcc_analyzer on each folder
    for i, folder in enumerate(experiment_folders, 1):
        print(f"\n[{i}/{len(experiment_folders)}] Processing {folder.name}...")
        
        cmd = [
            "python", "tools/gcc_analyzer.py", 
            str(folder),
            "--bitrate", "--utilization", "--recovery", 
            "--store-values", "--no-ssim"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                print(f"✅ Successfully processed {folder.name}")
            else:
                print(f"❌ Failed to process {folder.name}")
                print(f"Error: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"⏰ Timeout processing {folder.name}")
        except Exception as e:
            print(f"❌ Exception processing {folder.name}: {e}")
    
    print(f"\nCompleted processing {len(experiment_folders)} experiment folders")

if __name__ == "__main__":
    main() 