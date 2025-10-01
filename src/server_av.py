import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid
import whisper
import asyncio
from aiortc.contrib.media import MediaRecorder
from aiortc.sdp import candidate_from_sdp
from experiment_logger import init_experiment_logger, get_experiment_logger

import cv2
from aiohttp import web
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from av import VideoFrame
from av import AudioFrame
import time
import fractions
# numpy not needed for silence generation - using av.AudioFrame directly

#RECORDING_DURATION = 5
#Useful github issues
#https://github.com/aiortc/aiortc/issues/571
ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
model = whisper.load_model("base")

# Store peer connections by session to enable renegotiation
peer_connections = {}
# Track which connections have been initialized
initialized_connections = set()
# Track pending candidates for Trickle ICE
pending_candidates = {}

RESPONSE_DIR = os.path.join(ROOT, "audio_clips")

def select_response(text: str) -> str:
    """
    Selects a pre-recorded audio file based on keywords in the text.
    """
    lower_text = text.lower()

    if any(keyword in lower_text for keyword in ["hello", "hi", "hey"]):
        return os.path.join(RESPONSE_DIR, "response_greeting_stereo.wav")
    
    elif any(keyword in lower_text for keyword in ["weather", "forecast"]):
        return os.path.join(RESPONSE_DIR, "response_weather_stereo.wav")

    elif "time" in lower_text:
        return os.path.join(RESPONSE_DIR, "response_time_stereo.wav")

    elif any(keyword in lower_text for keyword in ["joke", "funny"]):
        return os.path.join(RESPONSE_DIR, "response_joke_stereo.wav")
    
    elif any(keyword in lower_text for keyword in ["help", "what can you do"]):
        return os.path.join(RESPONSE_DIR, "response_help_stereo.wav")
    
    else:
        # Default fallback response
        return os.path.join(RESPONSE_DIR, "response_fallback_stereo.wav")

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track, transform):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform

    async def recv(self):
        frame = await self.track.recv()

        if self.transform == "cartoon":
            img = frame.to_ndarray(format="bgr24")

            # prepare color
            img_color = cv2.pyrDown(cv2.pyrDown(img))
            for _ in range(6):
                img_color = cv2.bilateralFilter(img_color, 9, 9, 7)
            img_color = cv2.pyrUp(cv2.pyrUp(img_color))

            # prepare edges
            img_edges = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            img_edges = cv2.adaptiveThreshold(
                cv2.medianBlur(img_edges, 7),
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                9,
                2,
            )
            img_edges = cv2.cvtColor(img_edges, cv2.COLOR_GRAY2RGB)

            # combine color and edges
            img = cv2.bitwise_and(img_color, img_edges)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == "edges":
            # perform edge detection
            img = frame.to_ndarray(format="bgr24")
            img = cv2.cvtColor(cv2.Canny(img, 100, 200), cv2.COLOR_GRAY2BGR)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == "rotate":
            # rotate image
            img = frame.to_ndarray(format="bgr24")
            rows, cols, _ = img.shape
            M = cv2.getRotationMatrix2D((cols / 2, rows / 2), frame.time * 45, 1)
            img = cv2.warpAffine(img, M, (cols, rows))

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        else:
            return frame

class VideoDisplayTrack:
    """
    A video consumer that displays received frames using cv2.imshow and saves them for SSIM analysis
    """
    
    def __init__(self, track, window_name="Server Video"):
        self.track = track
        self.window_name = window_name
        self.frame_count = 0
        self.running = False
        
        # Video recording setup
        self.video_writer = None
        self.recording_path = None
        self.frames_buffer = []  # Store frames with timestamps
        self.setup_video_recording()
        
        # Video quality metrics
        self.decode_failures = 0
        self.total_packets = 0
        self.loss_start_time = None
        self.loss_frames_sent = 0
        self.loss_decode_failures = 0
        
        # Create empty H264 log file for tracking
        if hasattr(exp_logger, 'experiment_dir'):
            h264_log_path = os.path.join(exp_logger.experiment_dir, "logs", "h264_decode_failures.log")
            os.makedirs(os.path.dirname(h264_log_path), exist_ok=True)
            with open(h264_log_path, "w") as f:
                f.write("# H264 decode failure log - timestamp, failures, total, rate\n")
            
            # Create GCC estimates log file for tracking
            gcc_log_path = os.path.join(exp_logger.experiment_dir, "logs", "gcc_estimates.log")
            with open(gcc_log_path, "w") as f:
                f.write("# GCC estimates log - timestamp_s, as_bps, ar_bps, gcc_bps\n")
            # Set environment variable for RTP sender to find the log file
            os.environ["GCC_ESTIMATES_LOG"] = gcc_log_path
        
        # FPS tracking for accurate video recording
        self.last_frame_time = None
        self.frame_times = []
        self.estimated_fps = 30.0  # Default
        
        # Frame-level logging for packet loss correlation
        self.frame_log_path = None
        self.setup_frame_logging()
        
        print(f"Created VideoDisplayTrack with window: {window_name}")
    
    def setup_video_recording(self):
        """Setup video recording to save received frames"""
        # Always setup the path, but don't enable recording yet
        try:
            exp_logger = get_experiment_logger()
            session_id = getattr(self, 'session_id', 'default')
            self.recording_path = exp_logger.get_video_path('receiver', session_id)
            print(f"Video recording path ready: {self.recording_path}")
        except Exception as e:
            print(f" Failed to setup video recording path: {e}")
            self.recording_path = None
        
        # Check initial recording state
        self.recording_enabled = os.getenv("ENABLE_VIDEO_RECORDING") == "1"
        print(f"Video recording initially {'enabled' if self.recording_enabled else 'disabled'}")
    
    def setup_frame_logging(self):
        """Setup frame-level timestamp logging for packet loss correlation"""
        try:
            exp_logger = get_experiment_logger()
            self.frame_log_path = exp_logger.get_log_path("frame_timestamps.log")
            print(f"Frame logging enabled: {self.frame_log_path}")
        except Exception as e:
            print(f"Failed to setup frame logging: {e}")
            self.frame_log_path = None
    
    def enable_recording(self):
        """Enable video recording dynamically"""
        self.recording_enabled = True
        print(f"Video recording ENABLED dynamically")
    
    def disable_recording(self):
        """Disable video recording dynamically"""
        self.recording_enabled = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            print(f"Video recording DISABLED - released writer")
        
        # Encode any remaining buffered frames
        if self.frames_buffer:
            print("Encoding remaining buffered frames...")
            self._encode_buffered_frames()
            self.frames_buffer = []
        print(f"Video recording DISABLED dynamically")
    
    def _log_h264_failure(self, timestamp):
        """Log H264 decode failure with loss period awareness."""
        try:
            print(f"[DEBUG] H264 failure detected at {timestamp:.3f}s, total failures: {self.decode_failures}")
            
            # Check if we're in loss period
            timing_log_path = os.path.join(exp_logger.experiment_dir, "logs", "packet_loss_timing.log")
            in_loss_period = False
            
            if os.path.exists(timing_log_path):
                with open(timing_log_path, 'r') as f:
                    content = f.read()
                    if 'loss_start:' in content and 'loss_end:' not in content:
                        in_loss_period = True
                        if self.loss_start_time is None:
                            self.loss_start_time = timestamp
                            self.loss_frames_sent = 0
                            self.loss_decode_failures = 0
                        print(f"[DEBUG] In loss period, loss failures: {self.loss_decode_failures}")
            
            if in_loss_period:
                self.loss_decode_failures += 1
                self.loss_frames_sent = max(self.loss_frames_sent, self.total_packets - (self.total_packets - self.decode_failures))
                loss_rate = (self.loss_decode_failures / max(1, self.loss_frames_sent)) * 100
            
            # Log to experiment folder
            h264_log_path = os.path.join(exp_logger.experiment_dir, "logs", "h264_decode_failures.log")
            os.makedirs(os.path.dirname(h264_log_path), exist_ok=True)
            print(f"[DEBUG] Writing to H264 log: {h264_log_path}")
            
            overall_rate = (self.decode_failures / max(1, self.total_packets)) * 100
            
            with open(h264_log_path, "a") as f:
                if in_loss_period:
                    f.write(f"timestamp={timestamp:.3f}, loss_failures={self.loss_decode_failures}, loss_total={self.loss_frames_sent}, loss_rate={loss_rate:.1f}%, overall_failures={self.decode_failures}, overall_total={self.total_packets}, overall_rate={overall_rate:.1f}%\n")
                else:
                    f.write(f"timestamp={timestamp:.3f}, failures={self.decode_failures}, total={self.total_packets}, rate={overall_rate:.1f}%\n")
                f.flush()  # Ensure data is written
            
            print(f"[DEBUG] H264 log entry written successfully")
        except Exception as e:
            print(f"Error logging H264 failure: {e}")
            import traceback
            traceback.print_exc()
    
    def _encode_buffered_frames(self):
        """Encode buffered frames with correct timestamps."""
        if not self.frames_buffer or not self.recording_path:
            return
        
        print(f"Encoding {len(self.frames_buffer)} frames with real timestamps...")
        
        # Calculate frame intervals from real timestamps
        frame_intervals = []
        for i in range(1, len(self.frames_buffer)):
            interval_ms = self.frames_buffer[i]['timestamp_ms'] - self.frames_buffer[i-1]['timestamp_ms']
            frame_intervals.append(max(16, interval_ms))  # Minimum 16ms (60fps max)
        
        if not frame_intervals:
            return
        
        # Use average interval to determine base FPS, but write with variable timing
        avg_interval_ms = sum(frame_intervals) / len(frame_intervals)
        base_fps = 1000.0 / avg_interval_ms
        base_fps = max(5.0, min(60.0, base_fps))
        
        height, width = self.frames_buffer[0]['frame'].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # Create video writer with base FPS
        video_writer = cv2.VideoWriter(self.recording_path, fourcc, base_fps, (width, height))
        
        if not video_writer.isOpened():
            print(f"Failed to create video writer for {self.recording_path}")
            return
        
        # Write frames, duplicating/skipping frames to match real timing
        base_interval_ms = 1000.0 / base_fps
        
        for i, frame_data in enumerate(self.frames_buffer):
            if i == 0:
                # Write first frame
                video_writer.write(frame_data['frame'])
                continue
            
            # Calculate how much real time passed
            real_interval_ms = frame_intervals[i-1]
            
            # Determine how many video frames this represents
            frames_to_write = max(1, round(real_interval_ms / base_interval_ms))
            
            # Write the frame the calculated number of times
            for _ in range(frames_to_write):
                video_writer.write(frame_data['frame'])
        
        video_writer.release()
        print(f"Video encoded with real frame timing: {base_fps:.1f} base fps, {len(self.frames_buffer)} unique frames -> {self.recording_path}")
    
    def __del__(self):
        """Cleanup - encode any remaining frames"""
        if hasattr(self, 'frames_buffer') and self.frames_buffer:
            try:
                self._encode_buffered_frames()
            except:
                pass
    
    async def start_display(self):
        """Start consuming and displaying frames from the track"""
        self.running = True
        print(f"Starting video display for {self.window_name}")
        
        try:
            while self.running:
                frame = await self.track.recv()
                
                # Convert frame to numpy array and display
                try:
                    img = frame.to_ndarray(format="bgr24")
                    
                    # Track frame timing for FPS estimation
                    import time
                    current_time = time.time()
                    self.total_packets += 1
                    
                    # Check for H264 decode failures
                    from aiortc.codecs.h264 import _decode_failure_count, _total_decode_attempts
                    if _total_decode_attempts > 0:
                        current_failures = _decode_failure_count
                        if current_failures > self.decode_failures:
                            # New decode failure occurred
                            print(f"[DEBUG] H264 decode failure detected: {current_failures} failures out of {_total_decode_attempts} attempts")
                            self.decode_failures = current_failures
                            self._log_h264_failure(current_time)
                    elif self.total_packets % 100 == 0:  # Debug every 100 frames
                        print(f"[DEBUG] H264 stats: {_total_decode_attempts} attempts, {_decode_failure_count} failures")
                    
                    # Track frame timing
                    if self.last_frame_time is not None:
                        frame_interval = current_time - self.last_frame_time
                        
                        self.frame_times.append(frame_interval)
                        
                        # Keep only recent frame times (last 30 frames)
                        if len(self.frame_times) > 30:
                            self.frame_times.pop(0)
                        
                        # Update estimated FPS
                        if len(self.frame_times) >= 10:
                            avg_interval = sum(self.frame_times) / len(self.frame_times)
                            self.estimated_fps = 1.0 / avg_interval if avg_interval > 0 else 30.0
                            # Clamp to reasonable range
                            self.estimated_fps = max(5.0, min(60.0, self.estimated_fps))
                    
                    self.last_frame_time = current_time
                    
                    # Store frame with real timestamp (only if recording enabled)
                    if self.recording_enabled and self.recording_path:
                        self.frames_buffer.append({
                            'frame': img.copy(),
                            'timestamp_ms': int(current_time * 1000),
                            'frame_number': self.frame_count
                        })
                        
                        # Limit buffer size to prevent memory issues
                        if len(self.frames_buffer) > 10000:  # ~10 minutes at 15fps
                            print(" Frame buffer full, starting to encode video...")
                            self._encode_buffered_frames()
                            self.frames_buffer = []
                    
                    # Log frame timestamp for packet loss correlation
                    if self.frame_log_path:
                        try:
                            with open(self.frame_log_path, "a", encoding="utf-8") as f:
                                frame_info = {
                                    "frame_number": self.frame_count,
                                    "timestamp_ms": int(current_time * 1000),
                                    "estimated_fps": round(self.estimated_fps, 2),
                                    "recording": self.recording_enabled and self.video_writer is not None
                                }
                                f.write(f"frame: {frame_info}\n")
                                f.flush()
                        except Exception as e:
                            if self.frame_count % 100 == 0:  # Log error occasionally
                                print(f"Frame logging error: {e}")
                    
                    # Log server-side reception metrics to experiment directory
                    if hasattr(self, 'experiment_dir') and self.experiment_dir:
                        try:
                            server_stats_path = os.path.join(self.experiment_dir, "logs", "server_reception_stats.log")
                            with open(server_stats_path, "a", encoding="utf-8") as f:
                                server_info = {
                                    "timestamp_ms": int(current_time * 1000),
                                    "frame_number": self.frame_count,
                                    "server_received_fps": round(self.estimated_fps, 2),
                                    "server_received_resolution": f"{width}x{height}",
                                    "total_packets_received": self.total_packets,
                                    "decode_failures": self.decode_failures
                                }
                                f.write(f"server_reception: {server_info}\n")
                                f.flush()
                        except Exception as e:
                            if self.frame_count % 100 == 0:  # Log error occasionally
                                print(f"Server stats logging error: {e}")
                    
                    # Add frame info overlay for display
                    self.frame_count += 1
                    height, width = img.shape[:2]
                    
                    # Update server stats for client
                    if hasattr(self, 'pc') and hasattr(self.pc, 'server_stats'):
                        self.pc.server_stats.update({
                            'last_update': current_time,
                            'total_packets_received': self.total_packets,
                            'decode_failures': self.decode_failures,
                            'estimated_fps': round(self.estimated_fps, 2),
                            'received_resolution': f"{width}x{height}"
                        })
                    fps_text = f"{self.estimated_fps:.1f}fps" if len(self.frame_times) >= 10 else "estimating..."
                    text = f"Frame: {self.frame_count} | Size: {width}x{height} | {fps_text}"
                    if self.frame_count % 30 == 0:  # Print every 30 frames (~1 second)
                        recording_status = "recording" if (self.recording_enabled and self.video_writer) else "display only"
                        print(f"Displaying frame: {text} | Status: {recording_status}")
                    
                    cv2.putText(img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # Display the frame
                    cv2.imshow(self.window_name, img)
                    cv2.waitKey(1)  # Non-blocking, just refresh the display
                    
                except Exception as e:
                    print(f"Error displaying video frame: {e}")
                    
        except Exception as e:
            print(f"Video display loop ended: {e}")
        finally:
            # Encode any remaining buffered frames
            if self.frames_buffer:
                print("Encoding final buffered frames...")
                self._encode_buffered_frames()
                self.frames_buffer = []
            
            # Release video writer
            if self.video_writer:
                self.video_writer.release()
                print(f"Released video writer. Saved {self.frame_count} frames to: {self.recording_path}")
            
            cv2.destroyWindow(self.window_name)
            print(f"Closed video window: {self.window_name}")
    
    def stop(self):
        """Stop the display loop"""
        self.running = False
        if self.video_writer:
            self.video_writer.release()
            print(f"Video recording stopped. Saved to: {self.recording_path}")

class ResponseAudioTrack(MediaStreamTrack):
    """
    Custom audio track that can dynamically switch between silence and response audio.
    Based on GitHub issue examples for real-time audio generation.
    """
    kind = "audio"
    
    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.samples_per_frame = int(self.sample_rate * 0.020)  # 20ms frames
        self._timestamp = 0
        self._start_time = None
        
        # Audio state
        self._current_player = None
        self._is_playing_response = False
        self._silence_frames_sent = 0
        
    async def recv(self):
        """Generate audio frames - silence by default, response audio when available"""
        
        # Handle timing for consistent frame delivery
        if self._start_time is None:
            self._start_time = time.time()
        
        # Calculate when this frame should be delivered
        expected_time = self._start_time + (self._timestamp / self.sample_rate)
        now = time.time()
        wait_time = expected_time - now
        
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # Generate audio frame
        if self._is_playing_response and self._current_player:
            try:
                # Try to get frame from current response player
                frame = await self._current_player.audio.recv()
                #print(f"Playing response frame {self._timestamp}")
            except Exception as e:
                #print(f" Response playback finished or error: {e}")
                self._is_playing_response = False
                self._current_player = None
                frame = self._generate_silence()
        else:
            # Generate silence
            frame = self._generate_silence()
            # if self._silence_frames_sent % 50 == 0:  # Log every ~1 second
            #     print(f"Silence frame {self._silence_frames_sent}")
            self._silence_frames_sent += 1
        
        # Set timing properties
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        self._timestamp += self.samples_per_frame
        
        return frame
    
    def _generate_silence(self):
        """Generate a silent audio frame using EXACTLY your working pattern"""
        import numpy as np
        
        # Follow your exact working pattern for PyAudio data:
        # Create interleaved stereo silence (L,R,L,R,L,R,...)
        silence_data = np.zeros(self.samples_per_frame * 2, dtype=np.int16)  # *2 for stereo
        
        # Use your exact reshape pattern: data.reshape(-1, 1)
        silence_data = silence_data.reshape(-1, 1)
        
        # Use your exact transpose: data.T
        frame = AudioFrame.from_ndarray(silence_data.T, format='s16', layout='stereo')
        frame.sample_rate = self.sample_rate
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        
        return frame
    
    def play_response(self, audio_file_path):
        """Switch to playing a response audio file"""
        try:
            print(f"Switching to response: {audio_file_path}")
            self._current_player = MediaPlayer(audio_file_path)
            self._is_playing_response = True
            self._silence_frames_sent = 0
        except Exception as e:
            print(f"Failed to load response audio: {e}")
            self._is_playing_response = False
            self._current_player = None
    
    def stop_response(self):
        """Switch back to silence"""
        print("Switching back to silence")
        self._is_playing_response = False
        if self._current_player:
            self._current_player = None


async def index(request):
    content = open(os.path.join(ROOT, "web", "index_av.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "web", "client_av.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    session_id = params.get("session_id", "default")

    # Check if we already have a peer connection for this session
    if session_id in peer_connections:
        pc = peer_connections[session_id]
        pc_id = f"PeerConnection({session_id})[REUSED]"
        logger.info(f"{pc_id} Reusing existing connection for {request.remote}")
        
        # For reused connections, just handle the SDP negotiation
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
            ),
        )
    else:
        # Create new peer connection for new session
        pc = RTCPeerConnection()
        pc_id = f"PeerConnection({session_id})[NEW]"
        peer_connections[session_id] = pc
        pcs.add(pc)
        pc.session_id = session_id
        logger.info(f"{pc_id} Created new connection for {request.remote}")
        
        # Create and add our custom response audio track FIRST (starts with silence)
        pc.response_track = ResponseAudioTrack()
        pc.addTrack(pc.response_track)
        logger.info(f"{pc_id} Added custom response audio track (starts with silence)")
        
        # Set up cleanup when connection closes
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"{pc_id} Connection state is {pc.connectionState}")
            if pc.connectionState in ["failed", "closed"]:
                if session_id in peer_connections:
                    del peer_connections[session_id]
                if session_id in pending_candidates:
                    del pending_candidates[session_id]
                initialized_connections.discard(pc)
                pcs.discard(pc)
                logger.info(f"{pc_id} Cleaned up session {session_id}")

        # Set up event handlers for new connection
        initialized_connections.add(pc)
        
        # Storage for current recorder per connection
        pc.current_recorder = None
        pc.current_wav_path = None
        
        # Server-side stats collection
        pc.server_stats = {
            'last_update': time.time(),
            'total_packets_received': 0,
            'decode_failures': 0,
            'estimated_fps': 30.0,
            'received_resolution': '0x0',
            'received_bitrate': 0,
            'send_bitrate': 0,
            'send_fps': 30.0,
            'send_resolution': '1920x1080'
        }
        
        # Store data channel reference for server stats
        pc.data_channel = None

        # @pc.on("connectionstatechange")
        # async def on_connectionstatechange():
        #     print(f"[{pc_id}] Connection state changed to: {pc.connectionState}")
            
        @pc.on("iceconnectionstatechange")  
        async def on_iceconnectionstatechange():
            print(f"[{pc_id}] ICE connection state changed to: {pc.iceConnectionState}")

        @pc.on("datachannel")
        def on_datachannel(channel):
            print(f"Data channel opened on {pc_id}")
            pc.data_channel = channel
            
            # Start periodic server stats sending
            async def send_server_stats():
                while pc.connectionState == 'connected':
                    try:
                        if pc.data_channel and pc.data_channel.readyState == 'open':
                            # Collect server send and receive stats
                            await collect_server_stats(pc)
                            server_stats_msg = f"server_stats: {json.dumps(pc.server_stats)}"
                            pc.data_channel.send(server_stats_msg)
                    except Exception as e:
                        print(f"Failed to send server stats: {e}")
                    await asyncio.sleep(1.0)  # Send every second
            
            asyncio.create_task(send_server_stats())
            
            @channel.on("message")
            async def on_message(message):
                print(f"[{pc_id}] Data channel received message: '{message}'")
                
                # Save stats to experiment directory
                if message.startswith("stats: [STATS]") and hasattr(pc, 'experiment_dir'):
                    stats_path = os.path.join(pc.experiment_dir, "logs", "stats.log")
                    try:
                        with open(stats_path, "a", encoding="utf-8") as f:
                            f.write(f"{message}\n")
                    except Exception as e:
                        print(f"Failed to save stats: {e}")
                
                # Copy packet loss timing log if it exists
                elif message.startswith("copy_loss_timing") and hasattr(pc, 'experiment_dir'):
                    import shutil
                    timing_log_src = "/tmp/packet_loss_timing.log"
                    timing_log_dst = os.path.join(pc.experiment_dir, "logs", "packet_loss_timing.log")
                    try:
                        if os.path.exists(timing_log_src):
                            shutil.copy2(timing_log_src, timing_log_dst)
                            print(f"Copied loss timing log to experiment directory")
                    except Exception as e:
                        print(f"Failed to copy loss timing log: {e}")
                
                if message == "transcribe_now" and pc.current_recorder:
                    print("Received transcribe_now signal - processing immediately")
                    await pc.current_recorder.stop()
                    wav_path = pc.current_wav_path
                    
                    # Check file size before transcribing
                    if os.path.getsize(wav_path) < 4096:
                        print("Empty chunk, skipping transcription")
                        os.remove(wav_path)
                        pc.current_recorder = None
                        return
                    
                    try:
                        result = model.transcribe(wav_path)
                        transcribed_text = result["text"]
                        print("Transcription (immediate):", transcribed_text)
                        #transcribed_text='hello' #just for testing
                        
                        # Select and play response using our custom track
                        response_file = select_response(transcribed_text)
                        print(f"Selected response file: {response_file}")
                        
                        # Use our custom track to play the response
                        if hasattr(pc, 'response_track'):
                            print(f"Triggering response playback: {response_file}")
                            pc.response_track.play_response(response_file)
                            #print("Watch WebRTC-internals inbound-rtp bytesReceived for audio!")
                        else:
                            print("No response track available")
                        
                        # Delete file immediately after successful transcription
                        print(f"Deleting audio file: {wav_path}")
                        os.remove(wav_path)
                        print(f"Successfully deleted: {wav_path}")
                        
                    except Exception as exc:
                        print("Transcription failed:", exc)
                        # Still try to delete the file even if transcription failed
                        try:
                            print(f"Cleaning up failed transcription file: {wav_path}")
                            os.remove(wav_path)
                            print(f"Cleanup successful: {wav_path}")
                        except Exception as delete_error:
                            print(f"Cleanup failed for {wav_path}: {delete_error}")
                    finally:
                        # Reset recorder state regardless of success/failure
                        pc.current_recorder = None
                        pc.current_wav_path = None
                        print("Reset recorder state")
                elif isinstance(message, str) and message.startswith("ping"):
                    channel.send("pong" + message[4:])
                elif isinstance(message, str) and message.startswith("stats:"):
                    # Log WebRTC stats
                    try:
                        stats_log = os.getenv("STATS_LOG", "/tmp/stats.log")
                        with open(stats_log, "a", encoding="utf-8") as f:
                            f.write(f"{message}\n")
                    except Exception:
                        pass
                elif isinstance(message, str) and message.startswith("prerecorded_video_info:"):
                    # Log pre-recorded video information from client
                    try:
                        video_info_str = message[23:]  # Remove "prerecorded_video_info:" prefix
                        video_info = json.loads(video_info_str)
                        print(f"Pre-recorded video: {video_info['filename']} ({video_info['width']}x{video_info['height']}, {video_info.get('duration', 'unknown')}s)")
                        
                        # Log to experiment directory
                        exp_logger = get_experiment_logger()
                        prerecorded_log_path = exp_logger.get_analysis_path("prerecorded_video", "log")
                        with open(prerecorded_log_path, "a", encoding="utf-8") as f:
                            f.write(f"{json.dumps(video_info)}\n")
                    except Exception as e:
                        print(f" Failed to log pre-recorded video info: {e}")
                elif message == "enable_video_recording":
                    # Enable video recording on server side
                    print("Client requested video recording ENABLED")
                    os.environ["ENABLE_VIDEO_RECORDING"] = "1"
                    
                    # If we have an active video display track, enable its recording
                    if hasattr(pc, 'video_display_track'):
                        pc.video_display_track.enable_recording()
                    
                    channel.send("video_recording_enabled")
                elif message == "disable_video_recording":
                    # Disable video recording on server side
                    print("Client requested video recording DISABLED")
                    os.environ["ENABLE_VIDEO_RECORDING"] = "0"
                    
                    # If we have an active video display track, disable its recording
                    if hasattr(pc, 'video_display_track'):
                        pc.video_display_track.disable_recording()
                    
                    channel.send("video_recording_disabled")

        @pc.on("track")
        def on_track(track):
            print(f"[{pc_id}] Received track: {track.kind}")

            if track.kind == "audio":
                print(f"[{pc_id}] Setting up recording for client audio track")
                
                # Create a unique WAV path for this track
                wav_path = os.path.join(
                    ROOT, f"capture-{uuid.uuid4().hex}.wav"
                )

                recorder = MediaRecorder(wav_path)
                recorder.addTrack(track)
                asyncio.create_task(recorder.start())
                
                # Store for immediate access via data-channel
                pc.current_recorder = recorder
                pc.current_wav_path = wav_path
                print(f"[{pc_id}] Set pc.current_recorder to: {recorder}")
                print(f"[{pc_id}] Set pc.current_wav_path to: {wav_path}")
            elif track.kind == "video":
                print(f"[{pc_id}] Setting up video processing for client video track")
                
                # Create a video display track to show received frames on server
                video_display_track = VideoDisplayTrack(track, pc_id)
                # Pass experiment directory for server-side metrics logging
                if hasattr(pc, 'experiment_dir'):
                    video_display_track.experiment_dir = pc.experiment_dir
                # Pass pc reference for server stats updates
                video_display_track.pc = pc
                
                # Store reference for dynamic recording control
                pc.video_display_track = video_display_track
                
                # Add the video track back to the client for BWE testing
                print(f"[{pc_id}] Adding video echo-back for delay-based BWE")
                pc.addTrack(relay.subscribe(track))
                
                # Start the display track (it needs to be actively consuming frames)
                asyncio.create_task(video_display_track.start_display())

    # handle offer - this works for both new and reused connections
    await pc.setRemoteDescription(offer)

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def add_candidate(request):
    """Handle Trickle ICE candidate addition"""
    params = await request.json()
    session_id = params.get("session_id", "default")
    candidate_data = params.get("candidate")
    
    if session_id not in peer_connections:
        return web.Response(status=404, text="Session not found")
    
    pc = peer_connections[session_id]
    
    try:
        candidate = candidate_from_sdp(candidate_data["candidate"])
        candidate.sdpMid = candidate_data.get("sdpMid")
        candidate.sdpMLineIndex = candidate_data.get("sdpMLineIndex")
        
        await pc.addIceCandidate(candidate)
        logger.info(f"Added ICE candidate for session {session_id}")
        
        return web.Response()
    except Exception as e:
        logger.error(f"Failed to add ICE candidate: {e}")
        return web.Response(status=500, text=str(e))


async def collect_server_stats(pc):
    """Collect server send and receive stats."""
    try:
        # Get all stats from peer connection
        all_stats = await pc.getStats()
        
        # Collect send stats from RTP senders
        senders = pc.getSenders()
        for sender in senders:
            if sender.track and sender.track.kind == "video":
                stats = await sender.getStats()
                for report in stats.values():
                    if report.type == "outbound-rtp" and getattr(report, 'kind', '') == "video":
                        # Calculate send bitrate from bytes sent
                        current_time = time.time()
                        if hasattr(pc, 'last_send_stats'):
                            delta_time = current_time - pc.last_send_stats['time']
                            if delta_time > 0:
                                delta_bytes = report.bytesSent - pc.last_send_stats['bytes_sent']
                                bitrate = int((delta_bytes * 8) / delta_time)
                                pc.server_stats['send_bitrate'] = bitrate
                        
                        # Get FPS and resolution from the video track
                        if hasattr(sender.track, 'estimated_fps'):
                            pc.server_stats['send_fps'] = sender.track.estimated_fps
                        else:
                            pc.server_stats['send_fps'] = 30.0  # Default
                        
                        # Get resolution from the track's current frame
                        if hasattr(sender.track, 'current_resolution'):
                            pc.server_stats['send_resolution'] = sender.track.current_resolution
                        else:
                            pc.server_stats['send_resolution'] = '1920x1080'  # Default
                        
                        # Store for next bitrate calculation
                        pc.last_send_stats = {
                            'time': current_time,
                            'bytes_sent': report.bytesSent or 0
                        }
                        break
        
        # Collect receive stats from transport
        for report in all_stats.values():
            if report.type == "transport":
                # Calculate receive bitrate from bytes received
                current_time = time.time()
                if hasattr(pc, 'last_receive_stats'):
                    delta_time = current_time - pc.last_receive_stats['time']
                    if delta_time > 0:
                        delta_bytes = report.bytesReceived - pc.last_receive_stats['bytes_received']
                        bitrate = int((delta_bytes * 8) / delta_time)
                        pc.server_stats['received_bitrate'] = bitrate
                
                # Store for next bitrate calculation
                pc.last_receive_stats = {
                    'time': current_time,
                    'bytes_received': report.bytesReceived or 0
                }
                break
                
    except Exception as e:
        print(f"Failed to collect server stats: {e}")

async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    peer_connections.clear()
    pending_candidates.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file.")
    parser.add_argument(
        "--cc", 
        default="remb", 
        choices=["remb", "gcc-v0"],
        help="Congestion control algorithm (default: remb)"
    )

    parser.add_argument(
        "--target-bitrate", type=int, default=None,
        help="Evaluation: Target bitrate in bps (e.g. 3000000 for 3 Mbps). Seems not working...."
    )
    parser.add_argument(
        "--max-as-bitrate", type=int, default=None,
        help="Maximum As (loss-based) estimate cap in bps (e.g., 3000000 for 3Mbps)"
    )

    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Set congestion control algorithm via environment variable
    os.environ["AIORTC_CC"] = args.cc
    if args.target_bitrate:
        os.environ["EVAL_TARGET_BPS"] = str(args.target_bitrate)
        os.environ["EVAL_FORCE_ENCODER"] = "1"  # Enable forced encoder mode
        print(f"Using congestion control algorithm: {args.cc}, target={args.target_bitrate} bps (FORCED)")
    else:
        print(f"Using congestion control algorithm: {args.cc}")
    
    if args.max_as_bitrate:
        os.environ["MAX_AS_BITRATE_BPS"] = str(args.max_as_bitrate)
        print(f"As (loss-based) estimate cap: {args.max_as_bitrate/1000000:.1f} Mbps")
    
    # Initialize experiment logger for organized file management
    from datetime import datetime
    experiment_id = f"{args.cc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    exp_logger = init_experiment_logger("experiments", experiment_id)
    
    # Save experiment metadata with precise timestamps for Wireshark correlation
    experiment_start_time = datetime.now()
    experiment_info = {
        "experiment_id": experiment_id,
        "timestamp": experiment_start_time.isoformat(),
        "start_time_unix": experiment_start_time.timestamp(),
        "start_time_human": experiment_start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "congestion_control": args.cc,
        "target_bitrate": args.target_bitrate,  # Add target bitrate to experiment info
        "max_as_bitrate": args.max_as_bitrate,
        "video_recording_controlled_by": "client_checkbox",
        "host": args.host,
        "port": args.port,
        "wireshark_correlation_note": "Use start_time_unix as t0 reference for timestamp alignment"
    }
    exp_logger.save_experiment_info(experiment_info)
    
    # Video recording is now controlled by client checkbox
    print("Video recording controlled by client checkbox (not server argument)")

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    app.router.add_post("/add_candidate", add_candidate)
    app.router.add_static("/static/", path=os.path.join(ROOT, "web", "static"))  # Serve test videos
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )