# cubic.py
import math
from .base import CongestionControl, Packet

class CUBIC(CongestionControl):
    def __init__(self, max_datagram_size: int):
        super().__init__(max_datagram_size)
        self._W_max = self.congestion_window
        self._t_epoch = 0.0
        self._cwnd_epoch = 0
        self._W_est = 0
        self._starting_congestion_avoidance = False
        self._congestion_recovery_start_time = 0.0
        self._last_ack = 0.0
        self.rtt = 0.02

    def _better_cube_root(self, x: float) -> float:
        return -((-x) ** (1.0 / 3.0)) if x < 0 else x ** (1.0 / 3.0)

    def _calculate_K(self) -> float:
        W_max = self._W_max / self.max_datagram_size
        W_cwnd = self._cwnd_epoch / self.max_datagram_size
        return self._better_cube_root((W_max - W_cwnd) / 0.4)

    def W_cubic(self, t: float) -> int:
        W_max = self._W_max / self.max_datagram_size
        return int((0.4 * (t - self.K) ** 3 + W_max) * self.max_datagram_size)

    def on_packet_sent(self, packet: Packet) -> None:
        self.bytes_in_flight += packet.sent_bytes
        if self._last_ack == 0.0:
            return
        if packet.sent_time - self._last_ack >= 2.0:
            self._reset()

    def on_packet_acked(self, now: float, packet: Packet) -> None:
        self.bytes_in_flight -= packet.sent_bytes
        self._last_ack = packet.sent_time

        if self.ssthresh is None or self.congestion_window < self.ssthresh:
            self.congestion_window += packet.sent_bytes
        else:
            if not self._starting_congestion_avoidance:
                self._starting_congestion_avoidance = True
                self._t_epoch = now
                self._cwnd_epoch = self.congestion_window
                self._W_max = self.congestion_window
                self._W_est = self._cwnd_epoch
                self.K = self._calculate_K()

            self._W_est += int(
                self.max_datagram_size * (packet.sent_bytes / self.congestion_window)
            )

            t = now - self._t_epoch
            target = self.W_cubic(t + self.rtt)

            if target < self.congestion_window:
                pass
            elif target > 1.5 * self.congestion_window:
                self.congestion_window = int(self.congestion_window * 1.5)
            else:
                self.congestion_window = target

    def on_packets_lost(self, now: float, packets: list[Packet]) -> None:
        latest_time = max(p.sent_time for p in packets)
        for packet in packets:
            self.bytes_in_flight -= packet.sent_bytes

        if latest_time > self._congestion_recovery_start_time:
            self._congestion_recovery_start_time = now
            if self._W_max and self.congestion_window < self._W_max:
                self._W_max = int((self.congestion_window * 1.7) / 2)
            else:
                self._W_max = self.congestion_window

            self.ssthresh = max(
                int(self.bytes_in_flight * 0.7), 2 * self.max_datagram_size
            )
            self.congestion_window = max(self.ssthresh, 2 * self.max_datagram_size)
            self._starting_congestion_avoidance = True

    def _reset(self):
        self.congestion_window = 10 * self.max_datagram_size
        self._W_max = self.congestion_window
        self._t_epoch = 0.0
        self._cwnd_epoch = 0
        self._W_est = 0
        self.K = 0.0
        self._starting_congestion_avoidance = False
        self.ssthresh = None
