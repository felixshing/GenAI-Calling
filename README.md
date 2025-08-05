# GenAI-Calling

A demo WebRTC application that records user speech, transcribes it with Whisper and replies with a prerecorded audio clip – powered by a fully vendored copy of **aiortc**.

```
📦 repository layout
.
├── src/
│   ├── genai_server/             ← *first-party code*
│   │   ├── __init__.py
│   │   ├── server.py             ← aiohttp + WebRTC demo server
│   │   ├── web/
│   │   │   ├── index.html
│   │   │   └── client.js
│   │   └── media/
│   │       └── audio_clips/ *.wav
│   └── third_party/              ← *vendored dependencies*
│       ├── __init__.py
│       └── aiortc/ …             ← unmodified upstream source
└── tests/                        ← unit tests (unchanged)
```

Highlights
----------
* **Self-contained** – all Python dependencies live inside `src/third_party` so the
  project can run offline or inside hermetic build systems.
* **Single entry-point** – `python -m genai_server` starts the server.
* **Static assets inside the package** – shipped via `importlib.resources` so they
  work after `pip install`.
* **TLS ready** – pass `--cert` / `--key` to serve HTTPS in development. Certificates
  are *not* committed; generate them with something like:

  ```bash
  openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
         -keyout key.pem -out cert.pem -subj '/CN=localhost'
  ```

Quick start
-----------
1.  Create a virtual environment & install editable:

    ```bash
    python -m venv .venv && source .venv/bin/activate
    pip install -e .[dev]  # uses pyproject.toml
    ```

2.  Run the demo server:

    ```bash
    python -m genai_server --host 0.0.0.0 --port 8080
    ```

3.  Open `http://localhost:8080` in Chrome / Firefox and click **Start Call**.
   Speak, click **Stop & Transcribe** and listen for the AI response.

Testing
-------
Unit tests rely on `pytest` and live in the top-level `tests/` directory:

```bash
pytest -q
```

All existing aiortc test-suites still run unchanged thanks to a thin
compatibility stub in `src/aiortc/__init__.py` that re-exports the vendored
`third_party.aiortc` package.

FAQ
---
**Why vendor aiortc?**  To minimise external runtime dependencies and make sure
the exact same WebRTC implementation is used in all environments. Upstream
licence is BSD-3-Clause so redistribution is allowed.

**Can I still `pip install aiortc`?**  Yes – the compatibility shim ensures
`import aiortc` resolves to the vendored copy, but you can remove it and rely on
PyPI if you prefer.
