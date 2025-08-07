"""Google Congestion Control (GCC) V0 implementation."""

from typing import Optional
from .base import CongestionController
from ..rate import RemoteBitrateEstimator


class LossRateControl:
    """Loss-based rate controller implementing equation (5) from GCC paper."""
    
    def __init__(self, initial_bitrate: int = 500_000):
        """Initialize loss rate controller.
        
        Args:
            initial_bitrate: Starting bitrate in bits per second
        """
        self._as = initial_bitrate  # As(t) - sender-side estimate
    
    def update(self, fraction_lost: float) -> int:
        """Update sender-side estimate based on packet loss.
        
        Implements equation (5) from GCC paper:
        - If loss > 10%: multiplicative decrease  
        - If loss < 2%: gentle increase (5%)
        - Otherwise: hold steady
        
        Args:
            fraction_lost: Normalized fraction lost [0.0, 1.0]
            
        Returns:
            Updated sender-side bitrate estimate
        """
        if fraction_lost > 0.10:
            # Fast decrease on serious loss
            self._as *= (1.0 - 0.5 * fraction_lost)
        elif fraction_lost < 0.02:
            # Gentle increase when almost no loss
            self._as *= 1.05
        # else: hold steady
        
        # Clamp to reasonable bounds
        self._as = max(self._as, 10_000)      # Never go below 10 kbps
        self._as = min(self._as, 50_000_000)  # Cap at 50 Mbps #note this
        
        return int(self._as)
    
    @property
    def bitrate(self) -> int:
        """Current sender-side bitrate estimate."""
        return int(self._as)


class GccV0Controller(CongestionController):
    """Google Congestion Control V0 - combines delay and loss-based control.
    
    This implements the full GCC algorithm from the paper:
    - Delay-based controller (receiver-side) estimates Ar
    - Loss-based controller (sender-side) estimates As  
    - Final rate is min(Ar, As) per section 3.5
    """
    
    def __init__(self, initial_bitrate: int = 500_000, **kwargs):
        """Initialize GCC V0 controller.
        
        Args:
            initial_bitrate: Starting bitrate for loss controller
        """
        # Delay-based controller (receiver-side)
        self._delay_estimator = RemoteBitrateEstimator()
        self._ar: Optional[int] = None  # Receiver-side estimate
        
        # Loss-based controller (sender-side)
        self._loss_controller = LossRateControl(initial_bitrate)
        
    def on_packet_received(
        self, 
        *, 
        abs_send_time: int, 
        arrival_time_ms: int, 
        payload_size: int, 
        ssrc: int
    ) -> Optional[tuple[int, list[int]]]:
        """Process packet for delay-based estimation (receiver-side)."""
        result = self._delay_estimator.add(
            arrival_time_ms=arrival_time_ms,
            abs_send_time=abs_send_time,
            payload_size=payload_size, 
            ssrc=ssrc
        )
        
        if result is not None:
            self._ar, ssrc_list = result
            # Return the combined estimate for REMB
            target = self.target_bitrate()
            if target is not None:
                return (target, ssrc_list)
                
        return None
    
    def on_receiver_report(self, fraction_lost: int) -> None:
        """Process RTCP RR for loss-based estimation (sender-side)."""
        # Convert from RTCP format (0-255) to normalized (0.0-1.0)
        fraction_lost_normalized = fraction_lost / 255.0
        self._loss_controller.update(fraction_lost_normalized)
    
    def target_bitrate(self) -> Optional[int]:
        """Get combined target bitrate: min(Ar, As)."""
        if self._ar is None:
            return None
            
        # Section 3.5: A = min(Ar, As)
        as_bitrate = self._loss_controller.bitrate
        return min(self._ar, as_bitrate)