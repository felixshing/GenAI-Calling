import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid
import whisper
import os
import asyncio
from aiortc.contrib.media import MediaRecorder

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
                #print(f"🎵 Playing response frame {self._timestamp}")
            except Exception as e:
                #print(f"⚠️ Response playback finished or error: {e}")
                self._is_playing_response = False
                self._current_player = None
                frame = self._generate_silence()
        else:
            # Generate silence
            frame = self._generate_silence()
            # if self._silence_frames_sent % 50 == 0:  # Log every ~1 second
            #     print(f"🔇 Silence frame {self._silence_frames_sent}")
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
            print(f"🎵 Switching to response: {audio_file_path}")
            self._current_player = MediaPlayer(audio_file_path)
            self._is_playing_response = True
            self._silence_frames_sent = 0
        except Exception as e:
            print(f"❌ Failed to load response audio: {e}")
            self._is_playing_response = False
            self._current_player = None
    
    def stop_response(self):
        """Switch back to silence"""
        print("🔇 Switching back to silence")
        self._is_playing_response = False
        if self._current_player:
            self._current_player = None


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
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
                initialized_connections.discard(pc)
                pcs.discard(pc)
                logger.info(f"{pc_id} Cleaned up session {session_id}")

        # Set up event handlers for new connection
        initialized_connections.add(pc)
        
        # Storage for current recorder per connection
        pc.current_recorder = None
        pc.current_wav_path = None

        @pc.on("datachannel")
        def on_datachannel(channel):
            print(f"Data channel opened on {pc_id}")
            
            @channel.on("message")
            async def on_message(message):
                print(f"[{pc_id}] Data channel received message: '{message}'")
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
                            print(f"🎵 Triggering response playback: {response_file}")
                            pc.response_track.play_response(response_file)
                            print("📊 Watch WebRTC-internals inbound-rtp bytesReceived for audio!")
                        else:
                            print("❌ No response track available")
                        
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


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


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
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

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
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
