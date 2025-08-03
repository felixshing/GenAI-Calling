# base.py
from abc import ABC, abstractmethod
from typing import List

class Packet:
    def __init__(self, sent_time: float, sent_bytes: int):
        self.sent_time = sent_time
        self.sent_bytes = sent_bytes

class CongestionControl(ABC):
    bytes_in_flight: int = 0
    congestion_window: int = 0
    ssthresh: int | None = None

    def __init__(self, max_datagram_size: int):
        self.max_datagram_size = max_datagram_size
        self.congestion_window = 10 * max_datagram_size  # K_INITIAL_WINDOW

    @abstractmethod
    def on_packet_sent(self, packet: Packet) -> None:
        pass

    @abstractmethod
    def on_packet_acked(self, now: float, packet: Packet) -> None:
        pass

    @abstractmethod
    def on_packets_lost(self, now: float, packets: List[Packet]) -> None:
        pass

    def on_packets_expired(self, packets: List[Packet]) -> None:
        for packet in packets:
            self.bytes_in_flight -= packet.sent_bytes

    def get_window(self) -> int:
        return self.congestion_window
