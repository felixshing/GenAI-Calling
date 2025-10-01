#!/usr/bin/env python3
"""
Experiment Logger - Manages organized logging directories for GCC evaluation experiments.
Creates timestamped experiment folders and manages file paths for logs, videos, and analysis results.
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

class ExperimentLogger:
    """Manages experiment logging directories and file paths."""
    
    def __init__(self, base_dir: str = "experiments", experiment_id: Optional[str] = None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        
        # Create experiment directory with timestamp
        if experiment_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            experiment_id = f"gcc_exp_{timestamp}"
        
        self.experiment_dir = self.base_dir / experiment_id
        self.experiment_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        self.logs_dir = self.experiment_dir / "logs"
        self.videos_dir = self.experiment_dir / "videos"
        self.analysis_dir = self.experiment_dir / "analysis"
        
        self.logs_dir.mkdir(exist_ok=True)
        self.videos_dir.mkdir(exist_ok=True)
        self.analysis_dir.mkdir(exist_ok=True)
        
        self.experiment_id = experiment_id
        print(f"Experiment directory: {self.experiment_dir}")
    
    def get_rtcp_log_path(self) -> str:
        """Get path for RTCP loss log."""
        return str(self.logs_dir / "rtcp_loss.log")
    
    def get_stats_log_path(self) -> str:
        """Get path for stats log."""
        return str(self.logs_dir / "stats.log")
    
    def get_log_path(self, filename: str) -> str:
        """Get path for any log file in the logs directory."""
        return str(self.logs_dir / filename)
    
    def get_video_path(self, side: str, session_id: str = "default") -> str:
        """Get path for video recording (sender/receiver)."""
        timestamp = int(time.time() * 1000)
        filename = f"video_{side}_{session_id}_{timestamp}.mp4"
        return str(self.videos_dir / filename)
    
    def get_analysis_path(self, analysis_type: str, file_extension: str = "json") -> str:
        """Get path for analysis results."""
        filename = f"{analysis_type}.{file_extension}"
        return str(self.analysis_dir / filename)
    
    def get_experiment_info_path(self) -> str:
        """Get path for experiment metadata."""
        return str(self.experiment_dir / "experiment_info.json")
    
    def save_experiment_info(self, info: dict):
        """Save experiment metadata."""
        import json
        info_path = self.get_experiment_info_path()
        with open(info_path, 'w') as f:
            json.dump(info, f, indent=2)
        print(f"Experiment info saved to: {info_path}")
    
    def setup_environment_variables(self):
        """Set up environment variables for logging paths."""
        os.environ["RTCP_LOSS_LOG"] = self.get_rtcp_log_path()
        os.environ["STATS_LOG"] = self.get_stats_log_path()
        os.environ["EXPERIMENT_DIR"] = str(self.experiment_dir)
        os.environ["VIDEOS_DIR"] = str(self.videos_dir)
        
        print(f"Environment variables set:")
        print(f"   RTCP_LOSS_LOG: {os.environ['RTCP_LOSS_LOG']}")
        print(f"   STATS_LOG: {os.environ['STATS_LOG']}")
        print(f"   VIDEOS_DIR: {os.environ['VIDEOS_DIR']}")

# Global experiment logger instance
_experiment_logger = None

def get_experiment_logger() -> ExperimentLogger:
    """Get the global experiment logger instance."""
    global _experiment_logger
    if _experiment_logger is None:
        _experiment_logger = ExperimentLogger()
        _experiment_logger.setup_environment_variables()
    return _experiment_logger

def init_experiment_logger(base_dir: str = "experiments", experiment_id: Optional[str] = None) -> ExperimentLogger:
    """Initialize a new experiment logger."""
    global _experiment_logger
    _experiment_logger = ExperimentLogger(base_dir, experiment_id)
    _experiment_logger.setup_environment_variables()
    return _experiment_logger

if __name__ == "__main__":
    # Test the experiment logger
    logger = ExperimentLogger()
    logger.setup_environment_variables()
    
    # Save some test info
    test_info = {
        "experiment_id": logger.experiment_id,
        "timestamp": datetime.now().isoformat(),
        "congestion_control": "gcc-v0",
        "description": "Test experiment"
    }
    logger.save_experiment_info(test_info)
    
    print("\nTest paths:")
    print(f"RTCP log: {logger.get_rtcp_log_path()}")
    print(f"Stats: {logger.get_stats_log_path()}")
    print(f"Receiver video: {logger.get_video_path('receiver', 'test_session')}")
    print(f"SSIM analysis: {logger.get_analysis_path('ssim_analysis')}")