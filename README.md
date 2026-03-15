<p align="center">
  <img src="https://img.shields.io/badge/Gemini_Live_API-2.5_Flash-blue?style=for-the-badge" alt="Gemini"/>
  <img src="https://img.shields.io/badge/Google_Cloud-Run-green?style=for-the-badge" alt="Cloud Run"/>
  <img src="https://img.shields.io/badge/Python-FastAPI-yellow?style=for-the-badge" alt="Python"/>
</p>

# ⚡ CircuitSense — AI Electronics Lab Partner

> Point your camera. Talk to your hardware. Fix anything.

CircuitSense is a real-time AI lab assistant that **sees your electronics through your camera**, identifies components, detects faults, generates wiring diagrams, and provides expert analysis — all through natural voice and text conversation.

**Built for the [Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/) #GeminiLiveAgentChallenge**

🔗 **[Live Demo](https://circuitsense-657058316571.europe-west1.run.app)** · 📝 **[Blog Post](https://dev.to/kryptonus_vicky/building-circuitsense-how-i-built-a-dual-engine-ai-lab-partner-that-sees-your-hardware-3mfs)** · 🎥 **Demo Video** (coming soon)

---

## 🎯 What It Does

| Feature | Description |
|---------|------------|
| 🔍 **SCAN Mode** | Identifies all visible components, checks physical condition |
| 🔧 **DIAGNOSE Mode** | Hunts for faults: burnt traces, cold solder, bent pins, swollen caps |
| 🔌 **WIRE Mode** | Generates ASCII wiring diagrams for component connections |
| 📚 **LEARN Mode** | Explains each component in beginner-friendly language |
| 📊 **Health Score** | Real-time health percentage (e.g., "94% healthy") |
| 📦 **Component Inventory** | Auto-populated table with health badges and timestamps |
| 🔗 **Datasheet Links** | Direct links to datasheets for detected components |
| 💡 **Project Ideas** | AI-generated suggestions based on visible hardware |
| 📋 **Session Export** | Download a complete lab report as .txt |

---

## 🏗️ Architecture — Dual-Engine Design

CircuitSense runs **two Gemini models simultaneously** for the best of both worlds:

```
┌─────────────────────────────────────────────────────────────┐
│                    BROWSER (Frontend)                        │
│  Camera (1 FPS) + Microphone (16kHz PCM) + Rich Sidebar     │
└──────────────────────┬──────────────────────────────────────┘
                       │ WebSocket
┌──────────────────────▼──────────────────────────────────────┐
│               FASTAPI SERVER (Cloud Run)                     │
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │  Engine 1: Live API  │  │  Engine 2: Gemini 2.5 Flash  │  │
│  │  Voice + Vision      │  │  Structured JSON Analysis     │  │
│  │  Real-time audio     │  │  Every 15 seconds             │  │
│  │  streaming           │  │  Component inventory + health │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Engine 1** (Gemini Live API) handles real-time voice conversation with camera vision context.

**Engine 2** (Gemini 2.5 Flash) runs structured analysis every 15 seconds, producing JSON with component inventory, health assessments, protocol detection, and project ideas — populating the sidebar independently.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- [Google Cloud account](https://cloud.google.com/free) with Gemini API access
- Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/kryptonus/CircuitSense.git
cd CircuitSense

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your API key
echo "GEMINI_API_KEY=your_key_here" > .env

# Run
python main.py
```

Open `http://localhost:8080` in your browser. Click **Connect → Cam → point at electronics**.

### Deploy to Google Cloud Run

```bash
# One-command deployment
chmod +x deploy.sh
export GEMINI_API_KEY=your_key_here
./deploy.sh
```

Or manually:

```bash
gcloud run deploy circuitsense \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=$GEMINI_API_KEY \
  --port 8080 \
  --memory 512Mi \
  --timeout 300
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Voice AI** | Gemini 2.5 Flash Native Audio (Live API) |
| **Vision AI** | Gemini 2.5 Flash (structured JSON output) |
| **Backend** | Python 3.11, FastAPI, WebSocket (wsproto) |
| **Frontend** | Vanilla JS, Web Audio API, HTML5 Canvas |
| **Cloud** | Google Cloud Run, Cloud Build, Artifact Registry |
| **SDK** | Google GenAI SDK (`google-genai`) |
| **Deployment** | Docker, automated `deploy.sh` |

---

## 📁 Project Structure

```
CircuitSense/
├── main.py              # FastAPI server, dual-engine logic
├── static/
│   └── index.html       # Complete frontend (single file)
├── Dockerfile           # Container configuration
├── requirements.txt     # Python dependencies
├── deploy.sh            # Automated Cloud Run deployment
├── .env                 # API key (not committed)
└── README.md
```

---

## 🧪 What CircuitSense Detects

Tested successfully on:

- **Development boards** — ESP32, Arduino, STM32, NodeMCU
- **Sensors** — MPU6050 IMU, HC-SR04 ultrasonic, LD2410C radar
- **Complex PCBs** — set-top boxes, control boards, custom designs
- **Physical faults** — bent pins, oxidized contacts, ribbon cable damage
- **Protocols** — I2C, SPI, UART, USB, HDMI, Ethernet, Bluetooth

---

## 📸 Screenshots

| Scanning Hardware | Component Diagram | Wiring Diagram |
|:-:|:-:|:-:|
| Sidebar fills with detected components | ASCII box diagram with health checkmarks | ESP32 → MPU6050 I2C connection |

---

## 🔑 Key Technical Decisions

1. **Dual-engine architecture** — One model can't do real-time voice AND structured analysis well. Running both simultaneously solves this.
2. **`response_mime_type="application/json"`** — Forces valid JSON output from the analysis engine, preventing truncation and markdown wrapping.
3. **Camera frame pausing** — Frames are not sent to the Live API while it's generating a response, preventing mid-thought interruptions.
4. **Client-side audio resampling** — 48kHz → 16kHz linear interpolation in JavaScript for Gemini compatibility.

---

## 🏆 Hackathon Submission

- **Category:** Live Agents
- **Challenge:** Gemini Live Agent Challenge
- **Cloud:** Google Cloud Run (europe-west1)
- **Blog:** https://dev.to/kryptonus_vicky/building-circuitsense-how-i-built-a-dual-engine-ai-lab-partner-that-sees-your-hardware-3mf4

---
<p align="center">
  Built with ❤️ for the <a href="https://geminiliveagentchallenge.devpost.com/">Gemini Live Agent Challenge</a><br/>
  <strong>#GeminiLiveAgentChallenge</strong>
</p>
