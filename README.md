<div align="center">

# GPT Realtime Simple

Minimal, end‑to‑end Python client that turns your microphone into a live conversation with an Azure OpenAI Realtime model 
(bi‑directional audio + transcription + model responses in near real‑time).

[Inspo](https://github.com/Azure-Samples/aoai-realtime-audio-sdk/blob/main/python/rtclient/low_level_client.py)

</div>

---

## ✨ Features

- Live microphone capture (16 kHz mono) → streamed as `pcm16` chunks over WebSocket
- Server Voice Activity Detection (VAD) with configurable threshold & silence window
- Automatic Whisper transcription events printed as you speak
- Streaming model response audio (played immediately as deltas arrive) + optional greeting
- Simple, dependency‑light code (single `main.py`) using `websockets`, `sounddevice`, `numpy`
- Easily tweak voice, instructions, latency parameters, or switch to text‑only

---

## 📁 Repository Structure

| File | Purpose |
|------|---------|
| `main.py` | Core realtime client (capture → send → receive → playback) |
| `pyproject.toml` | Project metadata & dependencies |
| `uv.lock` | (If present) resolved dependency lock for `uv` / reproducible installs |
| `README.md` | This documentation |

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.12+
- An Azure OpenAI resource with a deployed Realtime‑capable model / voice (e.g. GPT‑4o Realtime)
- Working microphone & audio output
- PortAudio backend (installed automatically with `sounddevice`; on Linux you may need system packages: `sudo apt install portaudio19-dev`)

### 2. Environment Variables

Set the following (e.g. in a `.env` file placed next to `main.py`):

```
AZURE_OPENAI_ENDPOINT=https://<your-resource-name>.openai.azure.com
AZURE_OPENAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AZURE_OPENAI_DEPLOYMENT=<your-realtime-deployment-name>
# Optional (defaults to 2025-04-01-preview)
AZURE_OPENAI_API_VERSION=2025-04-01-preview
```

### 3. Install Dependencies

Using `pip`:

```pwsh
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install --upgrade pip
pip install -e .
```

Or using [`uv`](https://github.com/astral-sh/uv) for fast, cached installs:

```pwsh
uv venv
uv pip install -e .
```

### 4. Run

```pwsh
./.venv/Scripts/python.exe main.py
```

Speak after you see the connection establish; the model should greet you first (configurable). Press `Ctrl+C` to end.

---

## 🧠 How It Works

High‑level flow:

1. Connect WebSocket → `wss://<endpoint>/openai/realtime?...`
2. Immediately send `session.update` describing modalities, audio formats, VAD config, transcription request, and initial system instructions.
3. Start three concurrent tasks:
	- Microphone producer: captures float32 frames → converts to PCM16 → base64 → sends `input_audio_buffer.append` events; periodically commits with `input_audio_buffer.commit`.
	- Reader: listens for server events; pushes `response.output_audio.delta` payloads to playback queue; prints transcription events.
	- Playback consumer: writes raw PCM16 bytes to the system audio output stream as they arrive (low latency, no reassembly needed).
4. Server VAD detects end of your turn → model generates response incrementally → audio deltas streamed back.
5. `Ctrl+C` triggers cancellation & resource cleanup.

Event types used (subset):

| Type | Direction | Description |
|------|-----------|-------------|
| `session.update` | → | Configure voice, modalities, VAD, transcription |
| `input_audio_buffer.append` | → | Append base64 PCM16 chunk |
| `input_audio_buffer.commit` | → | Signal a batch of appended audio is ready |
| `conversation.item.audio_transcription.completed` | ← | Whisper transcription of your speech |
| `response.output_audio.delta` | ← | Streaming decoded audio segments from model |
| `response.output_audio.done` | ← | (Optional) Marks end of audio response |
| `response.error` | ← | Error details |

---

## 🎛 Key Tunables (in `main.py`)

| Variable / Field | Meaning | Default |
|------------------|---------|---------|
| `SR` | Sample rate | 16000 |
| `CHUNK_MS` | Capture buffer length (ms) | 100 |
| `commit_every` | How many chunks before commit (~latency vs efficiency) | 8 (~800ms) |
| `turn_detection.threshold` | VAD energy / probability threshold | 0.5 |
| `turn_detection.silence_duration_ms` | Silence to mark turn end | 600 |
| `voice` | Server voice ID | `alloy` |
| `instructions` | System / assistant style guidance | concise helper |

Lowering `commit_every` (e.g. 4) and/or `silence_duration_ms` reduces latency but may produce more partial turns.

---

## 🔄 Customization Examples

### Text‑Only Mode
Remove `"audio"` from `modalities`, drop audio format fields, and skip playback tasks; instead log text deltas.

### Different Voice / Style
Change `"voice": "alloy"` to another supported voice. Update `instructions` to change persona.

### Record Your Audio Locally
Inside the mic producer loop, also write `pcm` chunks to a file opened in binary append mode.

### Enable Debug Event Logging
Uncomment the debug print lines in `reader` to inspect all event types during development.

### Adjusting Latency
Strategies:
1. Decrease `CHUNK_MS` (e.g. 60) – more network messages, lower buffering delay.
2. Decrease `commit_every`.
3. Ensure local CPU scaling isn't throttling (disable power saving).
4. Keep instructions short; large prompts add token latency.

---

## 🧪 Minimal Contract (Conceptual)

Input: base64 PCM16 audio frames (16 kHz mono) batched into commits.
Output: interleaved transcription + streaming PCM16 response audio.
Error Modes: network disconnects, auth (401), unsupported deployment, audio device busy.
Success: continuous half‑duplex style conversation with sub‑second response onset after VAD triggers.

---

## 🛡 Security & Operational Notes

- Keep `AZURE_OPENAI_API_KEY` secret; prefer environment variables or secret managers over hardcoding.
- Consider rotating API keys periodically.
- For production UI, add explicit push‑to‑talk (disable always‑listening VAD) to avoid accidental capture.
- Validate endpoint TLS in environments performing SSL interception.

---

## 🧰 Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `KeyError: 'AZURE_OPENAI_ENDPOINT'` | Missing env vars | Create `.env`, reload shell |
| 401 / auth error | Wrong key or deployment name | Verify Azure portal values |
| No audio playback | Wrong output device / blocked | Specify device in `RawOutputStream(device=...)` |
| `PortAudioError: Error opening InputStream` | Mic in use / permissions | Close other apps; check OS privacy settings |
| Latency feels high | Large commit interval or silence window | Tune `commit_every` & `silence_duration_ms` |
| Transcription absent | Model not configured / event silent | Confirm `input_audio_transcription` block sent |

Add temporary prints inside loops if diagnosing stalls.

---

## 🧩 Extending This Project

Ideas:
- Add text overlay UI (e.g. with `rich` or a small web frontend)
- Persist full conversation history & export to JSON
- Add barge‑in (interrupt model audio when user speaks)
- Integrate hotkey push‑to‑talk (using `keyboard` library; platform caveats)
- Real‑time sentiment or keyword spotting locally before sending upstream

---

## 🗺 Event Flow Snapshot

```text
┌────────────┐        append + commit         ┌─────────────┐
│ Microphone │ ─────────────────────────────▶ │  WebSocket  │
└────────────┘                                 │  (Azure)   │
		 │                                      └─────┬───────┘
		 │ transcription events                        │ audio deltas
		 ▼                                             ▼
  Console log ◀──────── conversation + response ── Playback queue → Speakers
```

---

## 📦 Dependencies

Declared in `pyproject.toml`:

```
dotenv
numpy
sounddevice
websockets
```

These stay intentionally minimal; add others as you extend functionality.

---

## 🧾 License

Specify a license (e.g. MIT, Apache‑2.0). Create a `LICENSE` file if you plan to distribute.

---

## 🙋 FAQ

**Can I switch to 48 kHz?**  Yes—change `SR`, ensure deployment supports that output or resample locally. Higher rates increase bandwidth.

**Why PCM16 vs float32?**  Lower bandwidth & matches typical realtime API expectations.

**Do I need to send `input_audio_buffer.commit`?**  Yes; without commits the server may not process accumulated audio promptly.

**How do I exit cleanly?**  `Ctrl+C` triggers the `stop` event; tasks cancel & audio streams close.

---

## 🤝 Contributing

Open to improvements—add tests, a GUI, or performance metrics. Please keep examples concise.

---

## ✅ At a Glance

| Aspect | Status |
|--------|--------|
| Realtime Streaming | ✔ |
| Transcription | ✔ |
| Audio Playback | ✔ |
| Custom Voice | ✔ (edit session config) |
| Barge‑In | ✔ |
| GUI | ✖ |

---

Enjoy building with Azure OpenAI Realtime! 🚀

