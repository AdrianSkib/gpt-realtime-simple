import os
import json
import base64
import asyncio
import signal
import numpy as np
import sounddevice as sd
import websockets
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]
API_VER = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

WS_URL = (
    f"wss://{ENDPOINT.split('://')[-1]}"
    f"/openai/realtime?api-version={API_VER}&deployment={DEPLOYMENT}"
)

SR = 16000
CH = 1
CHUNK_MS = 100
CHUNK_SAMPLES = SR * CHUNK_MS // 1000


def float32_to_pcm16(frames: np.ndarray) -> bytes:
    return (np.clip(frames, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


async def playback_consumer(play_q: asyncio.Queue, stop: asyncio.Event):
    """Stream pcm16 bytes to the speaker using sounddevice RawOutputStream."""
    # print(sd.query_devices())  # to list devices
    # e.g., choose specific input (index 1) and default output
    # sd.default.device = (1, None)
    sd.default.samplerate = SR
    OUT_SR = 24000
    stream = sd.RawOutputStream(
        samplerate=OUT_SR, channels=CH, dtype="int16", blocksize=0
    )
    stream.start()
    try:
        while not stop.is_set():
            try:
                chunk = await asyncio.wait_for(play_q.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            if chunk:
                stream.write(chunk)
    finally:
        stream.stop()
        stream.close()


async def reader(ws, play_q: asyncio.Queue):
    while True:
        msg = await ws.recv()
        evt = json.loads(msg)
        t = evt.get("type")
        if t == "session.created":
            print("session created")
        elif t in ("response.audio.delta", "response.output_audio.delta"):
            b64 = evt.get("delta") or evt.get("audio")
            if b64:
                await play_q.put(base64.b64decode(b64))
        elif t in (
            "response.audio.done",
            "response.output_audio.done",
            "response.completed",
            "response.done",
        ):
            pass  # end of an utterance
        elif t == "conversation.item.input_audio_transcription.completed":
            tx = evt.get("transcript") or ""
            if tx:
                print(f"[you]: {tx}")
        elif t == "error" or t == "response.error":
            print("response error:", evt)


async def mic_producer(ws, stop: asyncio.Event):
    q = asyncio.Queue(maxsize=10)

    def cb(indata, frames, time, status):
        try:
            q.put_nowait(indata.copy())
        except asyncio.QueueFull:
            pass

    stream = sd.InputStream(
        channels=CH,
        samplerate=SR,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
        callback=cb,
    )
    stream.start()
    try:
        while not stop.is_set():
            try:
                frame = await asyncio.wait_for(q.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            pcm = float32_to_pcm16(frame)
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm).decode("ascii"),
                    }
                )
            )
    finally:
        stream.stop()
        stream.close()


async def send_session_update(ws):
    await ws.send(
        json.dumps(
            {
                "type": "session.update",
                "session": {
                    "voice": "alloy",
                    "modalities": ["text", "audio"],
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "silence_duration_ms": 600,
                    },
                    "input_audio_transcription": {"model": "whisper-1"},
                    "instructions": "Be concise and helpful. Speak clearly. Always speak in english.",
                },
            }
        )
    )


async def main():
    stop = asyncio.Event()

    def _sigint(*_):
        stop.set()

    signal.signal(signal.SIGINT, _sigint)

    play_q = asyncio.Queue(maxsize=50)

    async with websockets.connect(
        WS_URL,
        additional_headers=[("api-key", API_KEY)],
        subprotocols=["realtime"],
        max_size=None,
    ) as ws:
        await send_session_update(ws)

        tasks = [
            asyncio.create_task(reader(ws, play_q)),
            asyncio.create_task(mic_producer(ws, stop)),
            asyncio.create_task(playback_consumer(play_q, stop)),
        ]

        # Optional: have the model greet first
        await ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {"instructions": "Greet the user briefly in english."},
                }
            )
        )

        await stop.wait()
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
