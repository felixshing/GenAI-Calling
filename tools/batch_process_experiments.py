#!/usr/bin/env python3
"""
Batch process all experiment folders with gcc_analyzer and rename_experiment.
"""

import argparse
import subprocess
import sys
from pathlib import Path
import time

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"{description}...")
    print(f"   Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"{description} completed successfully")
        if result.stdout.strip():
            print(f"   Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{description} failed with return code {e.returncode}")
        if e.stdout.strip():
            print(f"   Stdout: {e.stdout.strip()}")
        if e.stderr.strip():
            print(f"   Stderr: {e.stderr.strip()}")
        return False
    except Exception as e:
        print(f"{description} failed with error: {e}")
        return False

def process_experiment_folder(exp_dir, args):
    """Process a single experiment folder."""
    print(f"\nProcessing: {exp_dir.name}")
    print("=" * 60)
    
    success_count = 0
    total_commands = 0
    
    # Step 1: Run gcc_analyzer
    if args.analyze:
        total_commands += 1
        gcc_cmd = [
            "python", "tools/gcc_analyzer.py", str(exp_dir),
            "--all", "--plot", "--store-values"
        ]
        
        # Add --no-ssim if requested
        if args.no_ssim:
            gcc_cmd.append("--no-ssim")
        
        if run_command(gcc_cmd, "GCC Analysis"):
            success_count += 1
    
    # Step 2: Rename experiment folder
    if args.rename:
        total_commands += 1
        rename_cmd = ["python", "tools/rename_experiment.py", str(exp_dir)]
        if run_command(rename_cmd, "Folder Renaming"):
            success_count += 1
    
    return success_count, total_commands

def main():
    parser = argparse.ArgumentParser(
        description='Batch process all experiment folders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process all experiments (analyze + rename)
    python tools/batch_process_experiments.py --analyze --rename
    
    # Only analyze (no renaming)
    python tools/batch_process_experiments.py --analyze --no-ssim
    
    # Only rename (no analysis)
    python tools/batch_process_experiments.py --rename
    
    # Process specific pattern
    python tools/batch_process_experiments.py --analyze --rename --pattern "gcc-v0_20250817*"
        """
    )
    
    parser.add_argument('--analyze', action='store_true', 
                       help='Run gcc_analyzer on each experiment folder')
    parser.add_argument('--rename', action='store_true',
                       help='Rename experiment folders with loss conditions')
    parser.add_argument('--no-ssim', action='store_true',
                       help='Skip SSIM analysis (faster)')
    parser.add_argument('--pattern', default='gcc-v0_*',
                       help='Pattern to match experiment folders (default: gcc-v0_*)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without actually running')
    
    args = parser.parse_args()
    
    if not args.analyze and not args.rename:
        print("Please specify at least one action: --analyze or --rename")
        parser.print_help()
        return 1
    
    # Find experiment folders
    experiments_dir = Path("experiments")
    if not experiments_dir.exists():
        print(f"Experiments directory not found: {experiments_dir}")
        return 1
    
    # Get all matching experiment folders
    experiment_folders = []
    for item in experiments_dir.iterdir():
        if item.is_dir() and item.name.startswith('gcc-v0_'):
            if args.pattern != 'gcc-v0_*':
                # Use custom pattern matching
                import fnmatch
                if fnmatch.fnmatch(item.name, args.pattern):
                    experiment_folders.append(item)
            else:
                experiment_folders.append(item)
    
    if not experiment_folders:
        print(f"No experiment folders found matching pattern: {args.pattern}")
        return 1
    
    # Sort by creation time (oldest first)
    experiment_folders.sort(key=lambda x: x.stat().st_ctime)
    
    print(f"Found {len(experiment_folders)} experiment folders:")
    for exp_dir in experiment_folders:
        print(f"   - {exp_dir.name}")
    
    if args.dry_run:
        print(f"\nDRY RUN - Would process {len(experiment_folders)} folders:")
        for exp_dir in experiment_folders:
            print(f"   - {exp_dir.name}")
            if args.analyze:
                print(f"     → Run gcc_analyzer --all --plot --store-values")
            if args.rename:
                print(f"     → Run rename_experiment")
        return 0
    
    # Confirm before proceeding
    print(f"\nAbout to process {len(experiment_folders)} experiment folders")
    if args.analyze:
        print(f"   - GCC Analysis: --all --plot --store-values" + (" --no-ssim" if args.no_ssim else ""))
    if args.rename:
        print(f"   - Folder Renaming: with loss conditions")
    
    response = input("\nContinue? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("Cancelled")
        return 0
    
    # Process each experiment folder
    print(f"\nStarting batch processing...")
    start_time = time.time()
    
    total_success = 0
    total_commands = 0
    failed_folders = []
    
    for i, exp_dir in enumerate(experiment_folders, 1):
        print(f"\nProgress: {i}/{len(experiment_folders)}")
        
        success, commands = process_experiment_folder(exp_dir, args)
        total_success += success
        total_commands += commands
        
        if success < commands:
            failed_folders.append(exp_dir.name)
    
    # Summary
    elapsed_time = time.time() - start_time
    print(f"\n" + "=" * 60)
    print(f"BATCH PROCESSING COMPLETE")
    print(f"   Total folders: {len(experiment_folders)}")
    print(f"   Successful commands: {total_success}/{total_commands}")
    print(f"   Failed commands: {total_commands - total_success}")
    print(f"   Elapsed time: {elapsed_time:.1f}s")
    
    if failed_folders:
        print(f"\nFailed folders:")
        for folder in failed_folders:
            print(f"   - {folder}")
    
    if total_success == total_commands:
        print(f"\nAll operations completed successfully!")
        return 0
    else:
        print(f"\nSome operations failed. Check the output above.")
        return 1

if __name__ == "__main__":
    exit(main()) 