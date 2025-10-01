"""Google Congestion Control (GCC) V0 implementation."""

from typing import Optional, Tuple
import os
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
        self._target_bitrate: Optional[int] = None  # Target bitrate constraint
    
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
        old_as = self._as
        action = "HOLD"
        
        if fraction_lost > 0.10:
            # Fast decrease on serious loss
            self._as *= (1.0 - 0.5 * fraction_lost)
            action = f"DECREASE (loss={fraction_lost:.3f})"
        elif fraction_lost < 0.02:
            # Gentle increase when almost no loss
            self._as *= 1.05
            action = f"INCREASE (loss={fraction_lost:.3f})"
        else:
            action = f"HOLD (loss={fraction_lost:.3f})"
        
        # Apply target bitrate constraint if set
        if self._target_bitrate is not None:
            self._as = min(self._as, self._target_bitrate)
        

        
        # Use adaptive bounds similar to rate.py
        # Minimum: 10 kbps (audio-only baseline)
        # Maximum: let it grow naturally, but cap at reasonable video limits
        self._as = max(self._as, 10_000)
        self._as = min(self._as, 10_000_000)  # 10 Mbps max (4K video territory)
        
        # Optional logging for debugging
        try:
            import os, time
            loss_log_path = os.getenv("RTCP_LOSS_LOG")
            if loss_log_path:
                # Log all changes, but mark different types
                if fraction_lost > 0.0:
                    # Log losses prominently
                    with open(loss_log_path, "a", encoding="utf-8") as f:
                        f.write(f"GCC_LOSS {action}: As {int(old_as)} -> {int(self._as)}, time={time.time():.3f}\n")
                elif old_as != self._as:
                    # Log increases when debugging
                    debug_log = os.getenv("DEBUG_GCC_INCREASE", "0") == "1"
                    if debug_log:
                        with open(loss_log_path, "a", encoding="utf-8") as f:
                            f.write(f"GCC_INCREASE {action}: As {int(old_as)} -> {int(self._as)}, time={time.time():.3f}\n")
        except Exception:
            pass
        
        return int(self._as)
    
    @property
    def bitrate(self) -> int:
        """Current sender-side bitrate estimate."""
        return int(self._as)
    
    def set_target_bitrate(self, target_bitrate: int) -> None:
        """Set target bitrate constraint for As component."""
        self._target_bitrate = target_bitrate
    



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
        # Allow env override for evaluation start bitrate
        try:
            env_init = int(os.getenv("GCC_LOSS_INIT_BPS", os.getenv("EVAL_TARGET_BPS", str(initial_bitrate))))
            initial_bitrate = env_init
        except Exception:
            pass

        # Delay-based controller (receiver-side)
        self._delay_estimator = RemoteBitrateEstimator()
        self._ar: Optional[int] = None  # Receiver-side estimate
        
        # Loss-based controller (sender-side)
        self._loss_controller = LossRateControl(initial_bitrate)
        
        # Set target bitrate constraint if available
        try:
            target_bps = int(os.getenv("EVAL_TARGET_BPS", "0"))
            if target_bps > 0:
                self._loss_controller.set_target_bitrate(target_bps)
                self._delay_estimator.set_target_bitrate(target_bps)
                print(f"[GCC] Set target bitrate constraint: {target_bps/1000000:.1f} Mbps")
        except Exception:
            pass
        

        
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
        
        # Apply adaptive clamping similar to rate.py
        # Use delay-based estimate as reference for reasonable bounds
        min_bitrate = max(10_000, int(0.1 * self._ar))  # At least 10% of delay estimate
        max_bitrate = min(10_000_000, int(2.0 * self._ar))  # At most 2x delay estimate
        
        combined = min(self._ar, as_bitrate)

        # Optional cap to evaluation target bitrate
        try:
            eval_cap = int(os.getenv("EVAL_TARGET_BPS", "0"))
        except Exception:
            eval_cap = 0
        if eval_cap > 0:
            combined = min(combined, eval_cap)

        return max(min_bitrate, min(combined, max_bitrate))

    # --- helpers for logging / evaluation ---
    def estimates(self) -> Tuple[Optional[int], int, Optional[int]]:
        """Return (Ar, As, A) where A = min(Ar, As) with current clamping.

        This is useful for evaluation / logging without coupling to encoder state.
        """
        import os
        ar = self._ar
        as_bps = self._loss_controller.bitrate
        
        # Apply As (loss-based) constraint if set
        max_as_env = os.getenv("MAX_AS_BITRATE_BPS")
        if max_as_env and as_bps:
            max_as_bitrate = int(max_as_env)
            if as_bps > max_as_bitrate:
                as_bps = max_as_bitrate
        
        # Apply target bitrate constraint to both components
        target_bps = int(os.getenv("EVAL_TARGET_BPS", "0"))
        if target_bps > 0:
            if ar is not None:
                ar = min(ar, target_bps)
            as_bps = min(as_bps, target_bps)
        

        
        a = self.target_bitrate()
        return ar, as_bps, a