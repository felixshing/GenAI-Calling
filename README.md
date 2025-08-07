# GenAI-Calling

A demo WebRTC application with **pluggable congestion control algorithms**. Records user speech, transcribes it with Whisper, and replies with prerecorded audio clips.

```
📦 repository layout
.
├── src/
│   ├── server.py                 ← main application server
│   ├── web/                      ← static web assets  
│   │   ├── index.html
│   │   └── client.js
│   ├── audio_clips/ *.wav        ← prerecorded responses
│   └── aiortc/                   ← modified WebRTC library
│       ├── cc/                   ← 🎯 congestion control algorithms
│       │   ├── base.py           ←   abstract interface
│       │   ├── remb.py           ←   delay-based (original)
│       │   └── gcc_v0.py         ←   GCC with loss control
│       ├── rate.py               ←   delay estimation (Kalman filter)
│       ├── rtcrtpreceiver.py     ←   receiver-side CC integration  
│       └── rtcrtpsender.py       ←   sender-side CC integration
└── tests/                        ← unit tests
```

## 🎯 Congestion Control Algorithms

This project implements multiple congestion control algorithms for WebRTC:

| Algorithm | Description | Status |
|-----------|-------------|---------|
| **REMB** | Delay-based only (original aiortc) | ✅ Working |
| **GCC V0** | Google Congestion Control with loss + delay | ✅ Working |
| **CUBIC** | TCP-friendly congestion control | 🚧 Future |
| **BBR** | Bottleneck Bandwidth and RTT | 🚧 Future |

### Algorithm Selection
```bash
python src/server.py --cc remb      # Delay-based (default)
python src/server.py --cc gcc-v0    # Full GCC with loss control
```

## Features  
* **Pluggable CC algorithms** – easy to add CUBIC, Reno, BBR, etc.
* **Full GCC implementation** – combines delay (receiver) + loss (sender) control  
* **Industry-standard** – follows WebRTC specifications and Google's GCC paper
* **Real-time audio/video** – live bidirectional communication with Whisper transcription

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install aiortc aiohttp whisper-openai opencv-python
   ```

2. **Run with different congestion control:**
   ```bash
   # Default REMB (delay-based only)
   python src/server.py --host 0.0.0.0 --port 8080
   
   # GCC V0 (delay + loss control) 
   python src/server.py --cc gcc-v0 --host 0.0.0.0 --port 8080
   ```

3. **Test the application:**
   - Open `http://localhost:8080` in Chrome/Firefox
   - Click **Start Call** and allow camera/microphone access
   - Speak into your microphone, then click **Stop & Transcribe**  
   - Listen for the AI-generated audio response

4. **HTTPS for external devices:**
   ```bash
   openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
          -keyout key.pem -out cert.pem -subj '/CN=localhost'
   python src/server.py --cert-file cert.pem --key-file key.pem
   ```

Testing
-------
Unit tests rely on `pytest` and live in the top-level `tests/` directory:

```bash
pytest -q
```

All existing aiortc test-suites still run unchanged thanks to a thin
compatibility stub in `src/aiortc/__init__.py` that re-exports the vendored
`third_party.aiortc` package.

## Adding New Algorithms

To implement a new congestion control algorithm:

1. **Create the algorithm class:**
   ```python
   # src/aiortc/cc/cubic.py
   from .base import CongestionController
   
   class CubicController(CongestionController):
       def on_packet_received(self, ...): # Implement delay logic
       def on_receiver_report(self, ...): # Implement loss logic  
       def target_bitrate(self): # Return combined estimate
   ```

2. **Register in factory:**
   ```python
   # src/aiortc/cc/__init__.py
   from .cubic import CubicController
   _ALGORITHMS["cubic"] = CubicController
   ```

3. **Add CLI option:**
   ```python
   # src/server.py  
   choices=["remb", "gcc-v0", "cubic"]
   ```

## FAQ

**Why modify aiortc directly?** We need deep integration with RTP packet processing and RTCP feedback loops. A wrapper approach would be too complex and inefficient.

**How does GCC work?** It combines two controllers: delay-based (receiver measures one-way delay gradients) and loss-based (sender reacts to packet loss reports). The final rate is `min(delay_estimate, loss_estimate)`.

**Can I use this in production?** This is a research/demo implementation. For production, consider using aiortc's standard REMB or a dedicated media server.
