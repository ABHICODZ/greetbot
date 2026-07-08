# GreetBot 🤖

An interactive, hands-free companion robot featuring a glowing **EVE-style (Wall-E) animated LED anime face** rendered in Pygame, voice activity detection (VAD), local faster-whisper speech-to-text, and a dual-backend reasoning brain (Groq Cloud / Local Ollama).

---

## Key Features

*   **EVE-Style LED Anime Visor**: Dynamic $800 \times 480$ Pygame interface displaying glowing cyan LED capsule eyes that animate based on 5 emotion states (`NEUTRAL`, `HAPPY`, `SAD`, `SURPRISED`, `THINKING`) with scanlines and randomized natural blinking.
*   **VAD-Based Audio Capture**: Energy-based Voice Activity Detection dynamically records natural speech and pauses rather than relying on fixed-length buffers.
*   **Three-Tier Reasoning Engine**:
    1.  *Instant Python Shortcuts*: For real-time, non-hallucinatory information (date, time, day, bot identity).
    2.  *Keyword KB Lookup*: Querying `knowledge_base.json` for deterministic factual answers (college details, personnel bios, placement figures).
    3.  *LLM Fallback*: Using cloud API (Groq) or local 3B model (Ollama) for general chat.
*   **Raspberry Pi 5 Optimization**: Out-of-the-box configurations for sub-5 second local processing on the Pi, including RAM-disk directories for temporary audio, thread locks, context window limits, and a system governor script.
*   **Global REST API**: FastAPI server exposing queries via `POST /ask`.

---

## File Structure

*   `brain.py`: Shared reasoning module. The single source of truth for bot logic and KB lookups.
*   `robo_head_mac.py`: macOS entry point utilizing CoreAudio (`sounddevice` streams) and macOS `say` fallbacks.
*   `robo_head.py`: Raspberry Pi entry point utilizing PipeWire (`pw-record` and `paplay` playback) and memory-disk storage (`/dev/shm`).
*   `pi_optimizer.sh`: Hardware and scheduling prioritization optimizer for Raspberry Pi.
*   `api_server.py`: FastAPI server for remote/global API queries.
*   `knowledge_base.json`: Local factual database (college details, club info, placement stats).

---

## Configuration

GreetBot is configured using environment variables:

| Variable | Description | Default (Mac) | Default (Pi) |
| :--- | :--- | :--- | :--- |
| `BRAIN_BACKEND` | LLM backend to run (`groq` or `ollama`) | `groq` | `ollama` |
| `GROQ_API_KEY` | Your Groq Cloud API Key | *None* | *N/A* |
| `WHISPER_MODEL` | Size of Whisper model for STT (`tiny.en` / `base.en`) | `base.en` | `tiny.en` |
| `VAD_SPEECH_THRESHOLD` | Sensitivity of Voice Activity Detection | `350` | `350` |

---

## Setup & Running Guide

### 💻 macOS (Development & Testing)

1.  **Activate virtual environment & install dependencies**:
    ```bash
    source venv/bin/activate
    pip install numpy pygame sounddevice requests faster-whisper
    ```
2.  **Run with Groq Backend**:
    ```bash
    export GROQ_API_KEY="your_groq_key_here"
    export BRAIN_BACKEND="groq"
    python3 robo_head_mac.py
    ```

---

### 🍓 Raspberry Pi 5 (Local Model Target)

1.  **Install dependencies**:
    ```bash
    sudo apt update
    sudo apt install pipewire-utils espeak
    python3 -m venv venv
    source venv/bin/activate
    pip install numpy pygame requests faster-whisper
    ```
2.  **Run Ollama in Docker**:
    ```bash
    docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
    docker exec -it ollama ollama run llama3.2:3b
    ```
3.  **Optimize the System**:
    ```bash
    sudo ./pi_optimizer.sh
    ```
4.  **Run GreetBot**:
    ```bash
    export BRAIN_BACKEND="ollama"
    python3 robo_head.py
    ```

---

## Customizing Facts (`knowledge_base.json`)
You can edit the `knowledge_base.json` next to `brain.py` at any time. Changes to college officials, placement stats, and club descriptions are reloaded **dynamically** in real time without restarting the GreetBot script or API server.
