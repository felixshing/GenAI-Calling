"""REMB-only congestion control (current aiortc behavior)."""

from typing import Optional
from .base import CongestionController
from ..rate import RemoteBitrateEstimator


class RembController(CongestionController):
    """Pure REMB (Receiver Estimated Maximum Bitrate) congestion control.
    
    This wraps the existing RemoteBitrateEstimator to provide the same
    delay-based congestion control that aiortc currently uses, but ignores
    packet loss reports.
    """
    
    def __init__(self, **kwargs):
        """Initialize REMB controller."""
        self._estimator = RemoteBitrateEstimator()
        self._target_bitrate: Optional[int] = None
    
    def on_packet_received(
        self, 
        *, 
        abs_send_time: int, 
        arrival_time_ms: int, 
        payload_size: int, 
        ssrc: int
    ) -> Optional[tuple[int, list[int]]]:
        """Process incoming packet for delay-based estimation."""
        result = self._estimator.add(
            arrival_time_ms=arrival_time_ms,
            abs_send_time=abs_send_time, 
            payload_size=payload_size,
            ssrc=ssrc
        )
        
        if result is not None:
            self._target_bitrate, ssrc_list = result
            return result
            
        return None
    
    def on_receiver_report(self, fraction_lost: int) -> None:
        """REMB ignores packet loss reports."""
        pass  # REMB is delay-based only
    
    def target_bitrate(self) -> Optional[int]:
        """Get current target bitrate from delay-based estimation."""
        return self._target_bitrate