# reno.py
from .base import CongestionControl, Packet

class Reno(CongestionControl):
    def __init__(self, max_datagram_size: int):
        super().__init__(max_datagram_size)
        self.ssthresh = None
        self.in_slow_start = True
        self._congestion_recovery_start_time = 0.0
        self._congestion_stash = 0

    def on_packet_sent(self, packet: Packet) -> None:
        self.bytes_in_flight += packet.sent_bytes

    def on_packet_acked(self, now: float, packet: Packet) -> None:
        self.bytes_in_flight -= packet.sent_bytes
        if packet.sent_time <= self._congestion_recovery_start_time:
            return

        if self.ssthresh is None or self.congestion_window < self.ssthresh:
            self.congestion_window += packet.sent_bytes
        else:
            self._congestion_stash += packet.sent_bytes
            count = self._congestion_stash // self.congestion_window
            if count:
                self._congestion_stash -= count * self.congestion_window
                self.congestion_window += count * self.max_datagram_size

    def on_packets_lost(self, now: float, packets: list[Packet]) -> None:
        lost_largest_time = max(p.sent_time for p in packets)
        for packet in packets:
            self.bytes_in_flight -= packet.sent_bytes

        if lost_largest_time > self._congestion_recovery_start_time:
            self._congestion_recovery_start_time = now
            self.congestion_window = max(
                int(self.congestion_window * 0.5), 2 * self.max_datagram_size
            )
            self.ssthresh = self.congestion_window
