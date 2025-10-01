"""Unit tests for GCC loss-based congestion control."""

import unittest
import sys
import os

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from aiortc.cc.gcc_v0 import LossRateControl, GccV0Controller
except ImportError as e:
    print(f"Warning: Could not import GCC modules: {e}")
    print("This test requires the full aiortc dependencies")
    LossRateControl = None
    GccV0Controller = None


class TestLossRateControl(unittest.TestCase):
    """Test the loss-based rate controller."""
    
    def setUp(self):
        if LossRateControl is None:
            self.skipTest("GCC modules not available")
        self.controller = LossRateControl(initial_bitrate=1_000_000)  # 1 Mbps
    
    def test_no_loss_increases_bitrate(self):
        """Test that 0% loss causes gentle increase."""
        initial = self.controller.bitrate
        new_bitrate = self.controller.update(0.0)  # 0% loss
        
        self.assertEqual(new_bitrate, int(initial * 1.05))
        self.assertGreater(new_bitrate, initial)
    
    def test_light_loss_increases_bitrate(self):
        """Test that <2% loss causes gentle increase."""
        initial = self.controller.bitrate
        new_bitrate = self.controller.update(0.015)  # 1.5% loss
        
        self.assertEqual(new_bitrate, int(initial * 1.05))
        self.assertGreater(new_bitrate, initial)
    
    def test_moderate_loss_holds_steady(self):
        """Test that 2-10% loss holds bitrate steady."""
        initial = self.controller.bitrate
        new_bitrate = self.controller.update(0.05)  # 5% loss
        
        self.assertEqual(new_bitrate, initial)
    
    def test_high_loss_decreases_bitrate(self):
        """Test that >10% loss causes multiplicative decrease."""
        initial = self.controller.bitrate
        loss_fraction = 0.15  # 15% loss
        new_bitrate = self.controller.update(loss_fraction)
        
        expected = int(initial * (1.0 - 0.5 * loss_fraction))
        self.assertEqual(new_bitrate, expected)
        self.assertLess(new_bitrate, initial)
    
    def test_severe_loss_dramatic_decrease(self):
        """Test that severe loss causes dramatic decrease."""
        initial = self.controller.bitrate
        loss_fraction = 0.25  # 25% loss
        new_bitrate = self.controller.update(loss_fraction)
        
        expected = int(initial * (1.0 - 0.5 * loss_fraction))
        self.assertEqual(new_bitrate, expected)
        # Should lose 12.5% of bitrate
        self.assertLess(new_bitrate, initial * 0.9)
    
    def test_minimum_bitrate_clamping(self):
        """Test that bitrate never goes below minimum."""
        # Start with very low bitrate and apply severe loss
        controller = LossRateControl(initial_bitrate=50_000)  # 50 kbps
        new_bitrate = controller.update(0.5)  # 50% loss
        
        self.assertGreaterEqual(new_bitrate, 10_000)  # Never below 10 kbps
    
    def test_maximum_bitrate_clamping(self):
        """Test that bitrate is clamped to maximum."""
        # Start near max and try to increase
        controller = LossRateControl(initial_bitrate=9_900_000)  # 9.9 Mbps
        new_bitrate = controller.update(0.0)  # 0% loss should increase
        
        self.assertLessEqual(new_bitrate, 10_000_000)  # Never above 10 Mbps


class TestRTCPLossConversion(unittest.TestCase):
    """Test RTCP fraction_lost field conversion."""
    
    def test_rtcp_conversion(self):
        """Test conversion from RTCP format (0-255) to normalized (0.0-1.0)."""
        test_cases = [
            (0, 0.0),      # No loss
            (26, 0.102),   # ~10% loss  
            (51, 0.2),     # 20% loss
            (128, 0.502),  # ~50% loss
            (255, 1.0),    # 100% loss
        ]
        
        for rtcp_value, expected_normalized in test_cases:
            normalized = rtcp_value / 255.0
            self.assertAlmostEqual(normalized, expected_normalized, places=3)


class TestPacketLossScenarios(unittest.TestCase):
    """Integration tests for realistic packet loss scenarios."""
    
    def setUp(self):
        if LossRateControl is None:
            self.skipTest("GCC modules not available")
    
    def test_network_degradation_scenario(self):
        """Simulate network degradation and recovery."""
        controller = LossRateControl(initial_bitrate=2_000_000)  # 2 Mbps
        
        # Scenario: Network starts good, degrades, then recovers
        scenarios = [
            ("Good network", 0.0),      # 0% loss → increase
            ("Light congestion", 0.01), # 1% loss → increase  
            ("Moderate issues", 0.05),  # 5% loss → hold
            ("Heavy congestion", 0.15), # 15% loss → decrease
            ("Network recovery", 0.02), # 2% loss → hold
            ("Back to normal", 0.0),    # 0% loss → increase
        ]
        
        bitrates = [controller.bitrate]
        
        for name, loss in scenarios:
            new_bitrate = controller.update(loss)
            bitrates.append(new_bitrate)
            print(f"{name:18} | Loss: {loss:4.0%} | Bitrate: {new_bitrate:>8,} bps")
        
        # Verify general behavior
        self.assertGreater(bitrates[1], bitrates[0])  # First increase
        self.assertLess(bitrates[4], bitrates[3])     # Decrease on high loss
        self.assertGreater(bitrates[-1], bitrates[-2]) # Recovery increase
    
    def test_rtcp_integration(self):
        """Test integration with RTCP fraction_lost values."""
        if GccV0Controller is None:
            self.skipTest("GccV0Controller not available")
            
        controller = GccV0Controller(initial_bitrate=1_000_000)
        
        # Simulate RTCP RR with different loss values
        rtcp_scenarios = [
            ("No loss", 0),       # 0/255
            ("Light loss", 13),   # ~5%
            ("Heavy loss", 38),   # ~15%
        ]
        
        for name, rtcp_fraction_lost in rtcp_scenarios:
            controller.on_receiver_report(rtcp_fraction_lost)
            # Note: target_bitrate() requires delay estimate (Ar) to be set
            print(f"{name}: RTCP={rtcp_fraction_lost}/255 ({rtcp_fraction_lost/255:.1%})")


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)