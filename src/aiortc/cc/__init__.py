"""Congestion Control Algorithms for aiortc."""

from .base import CongestionController
from .remb import RembController  
from .gcc_v0 import GccV0Controller

__all__ = ["CongestionController", "create_controller"]

# Registry of available congestion control algorithms
_ALGORITHMS = {
    "remb": RembController,
    "gcc-v0": GccV0Controller,
}

def create_controller(algorithm: str, **kwargs) -> CongestionController:
    """Create a congestion control algorithm instance.
    
    Args:
        algorithm: Algorithm name ("remb", "gcc-v0", etc.)
        **kwargs: Algorithm-specific parameters
        
    Returns:
        CongestionController instance
        
    Raises:
        ValueError: If algorithm is not supported
    """
    if algorithm not in _ALGORITHMS:
        available = ", ".join(_ALGORITHMS.keys())
        raise ValueError(f"Unknown congestion control algorithm '{algorithm}'. Available: {available}")
    
    return _ALGORITHMS[algorithm](**kwargs)

def list_algorithms() -> list[str]:
    """List available congestion control algorithms."""
    return list(_ALGORITHMS.keys())