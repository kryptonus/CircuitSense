# CircuitSense — AI Electronics Lab Partner

Real-time AI assistant that sees, hears, and speaks about your electronics hardware.

## Features
- Real-time voice conversation via Gemini Live API
- Camera-based component detection and health analysis
- Component inventory with health status tracking
- Automatic datasheet/manual links
- Protocol detection (I2C, SPI, UART)
- Safety warnings and wiring guidance
- Project ideas based on detected components

## Tech Stack
- **Backend:** Python, FastAPI, WebSocket
- **AI:** Gemini 2.5 Flash Native Audio (Live API) + Gemini 2.5 Flash (Vision Analysis)
- **Frontend:** Vanilla JS, Web Audio API
- **Cloud:** Google Cloud Run

## Architecture
```
Browser (Mic/Camera) --> WebSocket --> FastAPI Server
                                        |-- Gemini Live API (voice)
                                        |-- Gemini 2.5 Flash (structured analysis)
```

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn python-dotenv google-genai wsproto
echo "GEMINI_API_KEY=your_key" > .env
python main.py
```

Open http://localhost:8080

## Built for
Gemini Live Agent Challenge — #GeminiLiveAgentChallenge
