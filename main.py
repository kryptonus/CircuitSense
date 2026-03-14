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

SYSTEM = SYSTEM = """You are CircuitSense, an expert electronics lab partner.
You know ESP32, Arduino, STM32, MPU6050, nRF24L01, HC-SR04, LD2410C, I2C, SPI, UART, drone electronics, PCB design, soldering, and general electronics.
When you see hardware: identify it, give pinout, spot faults. Be concise and direct.
RULES:
- Keep replies to 2-3 sentences max. Users can ask follow-ups.
- Always note physical condition of visible hardware (damage, bent pins, burn marks, cold solder joints, corrosion).
- Never narrate your reasoning process. Just answer directly.
- If you cannot hear the user, say so briefly.
- When asked about wiring or connections, include a simple ASCII diagram like:
  ESP32          MPU6050
  GPIO21 (SDA) ----> SDA
  GPIO22 (SCL) ----> SCL
  3.3V -----------> VCC
  GND ------------> GND
- Keep ASCII diagrams compact and clear."""

ANALYSIS_PROMPT = ANALYSIS_PROMPT =ANALYSIS_PROMPT = ANALYSIS_PROMPT = """Look at this electronics image. Return ONLY valid JSON:
{"components":[{"name":"string","health":"good|damaged|unknown","detail":"short"}],"board":"string","protocols":["I2C"],"warnings":[],"ideas":["idea1","idea2","idea3"],"complexity":"beginner|intermediate|advanced","health":"good|needs_attention|damaged","wiring":"string","datasheet_keywords":["keyword"]}
Keep component names SHORT (max 4 words). Max 8 components. No long descriptions."""

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
                max_output_tokens=4096,
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

async def text_answer(question: str, image_b64: str = None) -> str:
    """Get a text answer from the fast model, with optional image context."""
    try:
        parts = []
        if image_b64:
            parts.append(types.Part(
                inline_data=types.Blob(
                    data=base64.b64decode(image_b64),
                    mime_type="image/jpeg",
                )
            ))
        parts.append(types.Part(text=question))
        response = await client.aio.models.generate_content(
            model=TEXT_MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )
        return response.text.strip()
    except Exception as e:
        print(f"Text answer error: {e}")
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
                            if now - last_analysis_time > 15:
                                last_analysis_time = now
                                # Run analysis in background
                                asyncio.create_task(
                                    run_analysis(websocket, image_data)
                                )

                        elif msg["type"] == "text":
                            user_text = msg["data"]
                            # Send to Live API for voice response
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user",
                                    parts=[types.Part(text=user_text)],
                                ),
                                turn_complete=True,
                            )
                            # Also get text response for display
                            asyncio.create_task(
                                send_text_reply(websocket, user_text)
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
            async def send_text_reply(ws, question):
                """Send text reply with optional image context."""
                answer = await text_answer(question)
                if answer:
                    try:
                        await ws.send_json({
                            "type": "text_reply",
                            "data": answer
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
