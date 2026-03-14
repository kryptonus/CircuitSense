import asyncio, base64, json, os
from pathlib import Path
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types

load_dotenv()
app = FastAPI()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Live API model for voice
LIVE_MODEL = "gemini-2.5-flash-native-audio-latest"
# Fast text model for structured analysis
TEXT_MODEL = "gemini-2.5-flash"

SYSTEM = """You are CircuitSense, an expert electronics lab partner.
You know ESP32, Arduino, STM32, MPU6050, nRF24L01, HC-SR04, LD2410C, I2C, SPI, UART, drone electronics, PCB design, soldering, and general electronics.
When you see hardware: identify it, give pinout, spot faults. Be concise and direct.
RULES:
- Keep replies to 2-3 sentences max. Users can ask follow-ups.
- Always note physical condition of visible hardware (damage, bent pins, burn marks, cold solder joints, corrosion).
- Never narrate your reasoning process. Just answer directly.
- If you cannot hear the user, say so briefly."""

ANALYSIS_PROMPT = """Analyze this electronics image and return ONLY a JSON object (no markdown, no backticks, no explanation). Use this exact format:
{
  "components": [
    {
      "name": "Component Name",
      "type": "microcontroller|sensor|module|passive|connector|other",
      "health": "good|damaged|unknown",
      "health_detail": "brief reason",
      "pins_visible": true,
      "notes": "any observation"
    }
  ],
  "board_type": "name of main board if identifiable",
  "protocols_detected": ["I2C","SPI","UART"],
  "safety_warnings": ["any safety concern"],
  "project_ideas": ["idea 1","idea 2","idea 3"],
  "complexity_score": "beginner|intermediate|advanced",
  "estimated_bom_usd": 0.00,
  "datasheet_keywords": ["search term for main component datasheet"],
  "wiring_notes": "any visible wiring observations",
  "overall_health": "good|needs_attention|damaged"
}
If no electronics visible, return: {"components":[],"board_type":"none","protocols_detected":[],"safety_warnings":[],"project_ideas":[],"complexity_score":"unknown","estimated_bom_usd":0,"datasheet_keywords":[],"wiring_notes":"","overall_health":"unknown"}"""


@app.get("/")
async def root():
    p = Path("static/index.html")
    return HTMLResponse(p.read_text() if p.exists() else "<h1>missing index.html</h1>")


async def analyze_image(image_b64: str) -> dict:
    """Run structured analysis on a camera frame using fast text model."""
    try:
        response = await client.aio.models.generate_content(
            model=TEXT_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                data=base64.b64decode(image_b64),
                                mime_type="image/jpeg",
                            )
                        ),
                        types.Part(text=ANALYSIS_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        )
        text = response.text.strip()
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        try:
            text = response.text.strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            text = re.sub(r',\s*}', '}', text)
            text = re.sub(r',\s*]', ']', text)
            return json.loads(text)
        except Exception:
            print(f"JSON parse failed, raw: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"Analysis error: {e}")
        return None


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text=SYSTEM)]
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        ),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    stop_event = asyncio.Event()
    ai_responding = asyncio.Event()
    analysis_lock = asyncio.Lock()
    last_analysis_time = 0

    try:
        async with client.aio.live.connect(
            model=LIVE_MODEL, config=config
        ) as session:
            print("Gemini session open")

            async def keepalive():
                try:
                    while not stop_event.is_set():
                        await asyncio.sleep(15)
                        try:
                            await websocket.send_json({"type": "ping"})
                        except Exception:
                            break
                except asyncio.CancelledError:
                    pass

            async def from_gemini():
                try:
                    while not stop_event.is_set():
                        async for resp in session.receive():
                            if stop_event.is_set():
                                return
                            if resp.server_content:
                                sc = resp.server_content
                                if sc.model_turn:
                                    ai_responding.set()
                                    for part in sc.model_turn.parts:
                                        if (
                                            part.inline_data
                                            and part.inline_data.data
                                        ):
                                            await websocket.send_json({
                                                "type": "audio",
                                                "data": base64.b64encode(
                                                    part.inline_data.data
                                                ).decode(),
                                            })
                                        if part.text:
                                            await websocket.send_json({
                                                "type": "thinking",
                                                "data": part.text,
                                            })
                                if sc.turn_complete:
                                    ai_responding.clear()
                                    await websocket.send_json({
                                        "type": "turn_complete"
                                    })
                            elif resp.data:
                                ai_responding.set()
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": base64.b64encode(
                                        resp.data
                                    ).decode(),
                                })
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Gemini error: {e}")
                    stop_event.set()

            async def from_browser():
                nonlocal last_analysis_time
                try:
                    while not stop_event.is_set():
                        raw = await websocket.receive_text()
                        msg = json.loads(raw)

                        if msg["type"] == "audio":
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=base64.b64decode(msg["data"]),
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )

                        elif msg["type"] == "image":
                            image_data = msg["data"]

                            # Send to Live API (skip if AI is responding)
                            if not ai_responding.is_set():
                                await session.send_realtime_input(
                                    video=types.Blob(
                                        data=base64.b64decode(image_data),
                                        mime_type="image/jpeg",
                                    )
                                )

                            # Run structured analysis every 15 seconds
                            import time
                            now = time.time()
                            if now - last_analysis_time > 30:
                                last_analysis_time = now
                                # Run analysis in background
                                asyncio.create_task(
                                    run_analysis(websocket, image_data)
                                )

                        elif msg["type"] == "text":
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user",
                                    parts=[types.Part(text=msg["data"])],
                                ),
                                turn_complete=True,
                            )

                        elif msg["type"] == "analyze":
                            # Manual analysis request
                            if msg.get("image"):
                                asyncio.create_task(
                                    run_analysis(websocket, msg["image"])
                                )

                        elif msg["type"] == "pong":
                            pass

                except WebSocketDisconnect:
                    print("Browser disconnected")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Browser error: {e}")
                finally:
                    stop_event.set()

            async def run_analysis(ws, image_b64):
                """Run structured analysis and send results."""
                async with analysis_lock:
                    result = await analyze_image(image_b64)
                    if result:
                        try:
                            await ws.send_json({
                                "type": "analysis",
                                "data": result,
                            })
                        except Exception:
                            pass

            tasks = [
                asyncio.create_task(from_gemini()),
                asyncio.create_task(from_browser()),
                asyncio.create_task(keepalive()),
            ]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            stop_event.set()
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except Exception as e:
        print(f"Session error: {e}")
        try:
            await websocket.send_json({
                "type": "error", "data": str(e)
            })
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        ws="wsproto",
        log_level="info",
    )
