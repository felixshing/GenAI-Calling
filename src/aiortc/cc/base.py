"""Base classes for congestion control algorithms."""

from abc import ABC, abstractmethod
from typing import Optional


class CongestionController(ABC):
    """Abstract base class for congestion control algorithms.
    
    This interface is used by RTCRtpReceiver and RTCRtpSender to implement
    different congestion control strategies (REMB, GCC, CUBIC, etc.).
    """
    
    @abstractmethod
    def on_packet_received(
        self, 
        *, 
        abs_send_time: int, 
        arrival_time_ms: int, 
        payload_size: int, 
        ssrc: int
    ) -> Optional[tuple[int, list[int]]]:
        """Handle an incoming RTP packet for delay-based estimation.
        
        Args:
            abs_send_time: Absolute send time from RTP extension
            arrival_time_ms: Local arrival time in milliseconds  
            payload_size: Size of RTP payload + padding in bytes
            ssrc: RTP stream identifier
            
        Returns:
            Tuple of (target_bitrate, ssrc_list) if estimate updated, None otherwise
        """
        pass
    
    @abstractmethod 
    def on_receiver_report(self, fraction_lost: int) -> None:
        """Handle RTCP Receiver Report for loss-based estimation.
        
        Args:
            fraction_lost: Fraction lost field from RTCP RR (0-255 range)
        """
        pass
    
    @abstractmethod
    def target_bitrate(self) -> Optional[int]:
        """Get the current target bitrate for the encoder/pacer.
        
        Returns:
            Target bitrate in bits per second, or None if not available
        """
        pass