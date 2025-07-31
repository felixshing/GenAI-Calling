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

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
model = whisper.load_model("base")

# Store peer connections by session to enable renegotiation
peer_connections = {}
# Track which connections have been initialized
initialized_connections = set()

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
    else:
        # Create new peer connection for new session
        pc = RTCPeerConnection()
        pc_id = f"PeerConnection({session_id})[NEW]"
        peer_connections[session_id] = pc
        pcs.add(pc)
        logger.info(f"{pc_id} Created new connection for {request.remote}")
        
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

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    # prepare local media
    player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    # Only set up event handlers for connections that haven't been initialized
    if pc not in initialized_connections:
        initialized_connections.add(pc)
        log_info("Setting up event handlers for new connection")
        
        # Storage for current recorder per connection
        pc.current_recorder = None
        pc.current_wav_path = None

        @pc.on("datachannel")
        def on_datachannel(channel):
            print(f"Data channel opened on {pc_id}")
            
            @channel.on("message")
            async def on_message(message):
                print(f"[{pc_id}] Data channel received message: '{message}'")
                #print(f"[{pc_id}] pc.current_recorder is: {pc.current_recorder}")
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
                        print("Transcription (immediate):", result["text"])
                        
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
                # ---- 1. create a unique WAV path per incoming track ----
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
    else:
        log_info("Reusing existing connection, skipping handler setup")

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()

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
