#!/usr/bin/env python3
"""Patch index.html with status system, timeout detection, and thinking filter."""

with open("static/index.html", "r") as f:
    html = f.read()

# ─── 1. Add status bar CSS ────────────────────────────────────────────────
status_css = """
.status-bar{display:flex;align-items:center;gap:6px;padding:4px 14px;border-bottom:1px solid var(--b1);background:var(--s1);flex-shrink:0;font-family:var(--mo);font-size:10px}
.status-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.status-dot.idle{background:var(--td)}
.status-dot.thinking{background:var(--am);box-shadow:0 0 6px var(--am);animation:pu 1s infinite}
.status-dot.speaking{background:var(--gr);box-shadow:0 0 6px var(--gr);animation:pu 1s infinite}
.status-dot.listening{background:var(--rd);box-shadow:0 0 6px var(--rd);animation:pu .6s infinite}
.status-dot.error{background:var(--rd);box-shadow:0 0 8px var(--rd)}
.status-dot.delayed{background:var(--am);box-shadow:0 0 8px var(--am)}
.status-label{color:var(--td)}
.status-label.active{color:var(--tx)}
.status-timer{color:var(--td);margin-left:auto;font-size:9px}
.thought-line{font-family:var(--mo);font-size:10px;color:var(--am);opacity:0.5;font-style:italic;padding:0 2px}
"""
html = html.replace("</style>", status_css + "\n</style>")

# ─── 2. Add status bar HTML (below session transcript header) ──────────
old_session_header = '<div class="sl"><span>Session Transcript</span><span class="tg" id="sessionTag">READY</span></div>'
new_session_header = '''<div class="sl"><span>Session Transcript</span><span class="tg" id="sessionTag">READY</span></div>
      <div class="status-bar" id="statusBar">
        <div class="status-dot idle" id="statusDot"></div>
        <span class="status-label" id="statusLabel">Idle</span>
        <span class="status-timer" id="statusTimer"></span>
      </div>'''
html = html.replace(old_session_header, new_session_header)

# ─── 3. Replace the entire <script> block ─────────────────────────────
# Find the script tag and replace everything
script_start = html.index("<script>")
script_end = html.index("</script>") + len("</script>")
old_script = html[script_start:script_end]

new_script = r"""<script>
var ws=null, isConnected=false, cameraActive=false;
var mediaStream=null, processor=null, micCtx=null;
var playCtx=null, nextPlayTime=0, isPlaying=false, playbackQueue=[];
var frameInterval=null, aiMsgEl=null, typingEl=null, currentAIText="";
var aiState="idle", stateStartTime=0, stateTimerInterval=null;
var turnTimeoutId=null;

// ── STATUS SYSTEM ─────────────────────────────────────────────────────
function setAIState(state, detail){
  aiState=state;
  stateStartTime=Date.now();
  var dot=document.getElementById("statusDot");
  var label=document.getElementById("statusLabel");
  var timer=document.getElementById("statusTimer");
  dot.className="status-dot "+state;
  var labels={
    idle:"Idle — ready for input",
    thinking:"Processing your input...",
    speaking:"AI is speaking",
    listening:"Listening to you",
    delayed:"Response delayed — still waiting...",
    error:"Connection issue"
  };
  label.textContent=detail||labels[state]||state;
  label.className="status-label"+(state!=="idle"?" active":"");
  if(stateTimerInterval) clearInterval(stateTimerInterval);
  if(state!=="idle"){
    stateTimerInterval=setInterval(function(){
      var elapsed=Math.floor((Date.now()-stateStartTime)/1000);
      timer.textContent=elapsed+"s";
    },1000);
  } else {
    timer.textContent="";
    stateTimerInterval=null;
  }

  // Auto-timeout: if thinking for >45s, mark as delayed
  if(turnTimeoutId) clearTimeout(turnTimeoutId);
  if(state==="thinking"){
    turnTimeoutId=setTimeout(function(){
      if(aiState==="thinking"){
        setAIState("delayed","Response taking longer than expected...");
        // After 90s total, assume stuck
        turnTimeoutId=setTimeout(function(){
          if(aiState==="delayed"){
            setAIState("error","AI appears stuck. Try sending another message.");
            rmTyping();
            aiMsgEl=null; currentAIText="";
          }
        },45000);
      }
    },45000);
  }
}

// ── FILTER THINKING from display text ─────────────────────────────────
function filterThinking(text){
  // Remove **Thinking Header** blocks — they're Gemini's internal chain-of-thought
  return text.replace(/\*\*[A-Z][^*]{3,60}\*\*/g, "").replace(/\s{2,}/g," ").trim();
}

function extractThinkingHeaders(text){
  var matches=text.match(/\*\*[A-Z][^*]{3,60}\*\*/g);
  return matches?matches.map(function(m){return m.replace(/\*\*/g,"");}):[];
}

// ── WEBSOCKET ─────────────────────────────────────────────────────────
function connect(){
  var proto=location.protocol==="https:"?"wss:":"ws:";
  ws=new WebSocket(proto+"//"+location.host+"/ws");
  ws.onopen=function(){
    isConnected=true;
    dot("wsDot","g");
    setText("wsStatus","CONNECTED");
    document.getElementById("connectBtn").classList.add("act");
    setText("sessionTag","LIVE");
    isPlaying=false; playbackQueue=[];
    setAIState("idle");
    addMsg("sys","Session open. Hold Mic to speak, release to hear reply.");
  };
  ws.onmessage=function(e){
    var m=JSON.parse(e.data);
    if(m.type==="ping"){ws.send(JSON.stringify({type:"pong"}));return;}
    if(m.type==="audio"){
      enqueue(m.data);
      if(aiState!=="speaking") setAIState("speaking");
    }
    else if(m.type==="text"){
      if(!aiMsgEl){rmTyping();aiMsgEl=addMsg("ai","");}
      currentAIText+=m.data;
      // Show filtered text in transcript, but track thinking
      var display=filterThinking(currentAIText);
      var thoughts=extractThinkingHeaders(currentAIText);
      aiMsgEl.querySelector(".mc").textContent=display;
      // Show latest thinking step in status bar
      if(thoughts.length>0) setAIState("thinking",thoughts[thoughts.length-1]);
      updateAnalysis(currentAIText);
      scrollT();
    }
    else if(m.type==="turn_complete"){
      aiMsgEl=null; currentAIText=""; rmTyping();
      setAIState("idle");
      if(turnTimeoutId){clearTimeout(turnTimeoutId);turnTimeoutId=null;}
    }
    else if(m.type==="error"){
      addMsg("sys","Error: "+m.data);
      setAIState("error",m.data);
    }
  };
  ws.onclose=function(){
    isConnected=false;
    dot("wsDot","");
    setText("wsStatus","DISCONNECTED");
    document.getElementById("connectBtn").classList.remove("act");
    setText("sessionTag","ENDED");
    setAIState("error","Disconnected — reconnecting...");
    setTimeout(function(){if(!isConnected)connect();},3000);
  };
  ws.onerror=function(){addMsg("sys","WS error");setAIState("error","WebSocket error");};
}
function disconnect(){
  if(ws){
    ws.onclose=null;
    ws.close();
    isConnected=false;
    dot("wsDot","");
    setText("wsStatus","DISCONNECTED");
    document.getElementById("connectBtn").classList.remove("act");
    setAIState("idle");
  }
}
function toggleConnect(){isConnected?disconnect():connect();}

// ── PLAYBACK ──────────────────────────────────────────────────────────
function enqueue(b64){
  playbackQueue.push(Uint8Array.from(atob(b64),function(c){return c.charCodeAt(0);}));
  if(!isPlaying) schedulePump();
}
function schedulePump(){
  if(!playCtx) playCtx=new(window.AudioContext||window.webkitAudioContext)({sampleRate:24000});
  if(playCtx.state==="suspended") playCtx.resume().then(function(){doPump();});
  else doPump();
}
function doPump(){
  isPlaying=true;
  setAIState("speaking");
  var now=playCtx.currentTime;
  if(nextPlayTime<now+0.05) nextPlayTime=now+0.05;
  while(playbackQueue.length>0){
    var bytes=playbackQueue.shift();
    var i16=new Int16Array(bytes.buffer);
    var f32=new Float32Array(i16.length);
    for(var i=0;i<i16.length;i++) f32[i]=i16[i]/32768;
    var buf=playCtx.createBuffer(1,f32.length,24000);
    buf.copyToChannel(f32,0);
    var src=playCtx.createBufferSource();
    src.buffer=buf;
    src.connect(playCtx.destination);
    src.start(nextPlayTime);
    nextPlayTime+=buf.duration;
    drawWave(f32);
  }
  var waitMs=(nextPlayTime-playCtx.currentTime)*1000-80;
  setTimeout(function(){
    if(playbackQueue.length>0) doPump();
    else{isPlaying=false; setText("audioTag","IDLE"); if(aiState==="speaking") setAIState("idle");}
  },Math.max(30,waitMs));
}

// ── MIC (push-to-talk) ───────────────────────────────────────────────
function pcmToBase64(i16arr){
  var bytes=new Uint8Array(i16arr.buffer);
  var binary="";
  for(var i=0;i<bytes.length;i+=512){
    var chunk=bytes.subarray(i,Math.min(i+512,bytes.length));
    binary+=String.fromCharCode.apply(null,chunk);
  }
  return btoa(binary);
}
function resample(f32,fromRate,toRate){
  if(fromRate===toRate) return f32;
  var ratio=fromRate/toRate;
  var newLen=Math.round(f32.length/ratio);
  var out=new Float32Array(newLen);
  for(var i=0;i<newLen;i++){
    var srcIdx=i*ratio;
    var idx=Math.floor(srcIdx);
    var frac=srcIdx-idx;
    out[i]=(f32[idx]||0)+((f32[Math.min(idx+1,f32.length-1)]||0)-(f32[idx]||0))*frac;
  }
  return out;
}
function startMic(){
  if(!isConnected||!ws||ws.readyState!==1){addMsg("sys","Not connected");return;}
  if(processor) return;
  if(!micCtx) micCtx=new(window.AudioContext||window.webkitAudioContext)();
  var resume=micCtx.state==="suspended"?micCtx.resume():Promise.resolve();
  resume.then(function(){
    navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}})
    .then(function(stream){
      mediaStream=stream;
      var nativeRate=micCtx.sampleRate;
      console.log("Mic native sample rate:",nativeRate);
      var src=micCtx.createMediaStreamSource(stream);
      processor=micCtx.createScriptProcessor(4096,1,1);
      processor.onaudioprocess=function(e){
        if(!ws||ws.readyState!==1) return;
        var f32=e.inputBuffer.getChannelData(0);
        var resampled=resample(f32,nativeRate,16000);
        var i16=new Int16Array(resampled.length);
        for(var i=0;i<resampled.length;i++) i16[i]=Math.max(-32768,Math.min(32767,resampled[i]*32768));
        ws.send(JSON.stringify({type:"audio",data:pcmToBase64(i16)}));
        drawWave(f32);
      };
      src.connect(processor);
      processor.connect(micCtx.destination);
      document.getElementById("micBtn").classList.add("rec");
      setText("micLabel","Listening...");
      setText("audioTag","REC");
      setAIState("listening");
      addTyping();
    })
    .catch(function(err){addMsg("sys","Mic error: "+err.message);});
  });
}
function stopMic(){
  if(processor){processor.disconnect();processor=null;}
  if(mediaStream){mediaStream.getTracks().forEach(function(t){t.stop();});mediaStream=null;}
  document.getElementById("micBtn").classList.remove("rec");
  setText("micLabel","Hold Mic");
  if(!isPlaying) setText("audioTag","IDLE");
  if(aiState==="listening") setAIState("thinking","Waiting for AI response...");
}

// ── CAMERA ────────────────────────────────────────────────────────────
function toggleCamera(){cameraActive?stopCam():startCam();}
function startCam(){
  navigator.mediaDevices.getUserMedia({video:{width:640,height:480}})
  .then(function(s){
    window._cs=s;
    var v=document.getElementById("ve");
    v.srcObject=s; v.style.display="block";
    document.getElementById("vp").style.display="none";
    document.getElementById("vo").classList.add("act");
    document.getElementById("vw").classList.add("sc");
    document.getElementById("camBtn").classList.add("act");
    dot("camDot","g"); setText("camStatus","CAM ON"); setText("visionTag","ACTIVE");
    cameraActive=true;
    frameInterval=setInterval(function(){
      if(!ws||ws.readyState!==1) return;
      var c=document.createElement("canvas"); c.width=320; c.height=240;
      c.getContext("2d").drawImage(v,0,0,320,240);
      ws.send(JSON.stringify({type:"image",data:c.toDataURL("image/jpeg",.7).split(",")[1]}));
    },6000);
  })
  .catch(function(err){addMsg("sys","Camera error: "+err.message);});
}
function stopCam(){
  if(frameInterval){clearInterval(frameInterval);frameInterval=null;}
  if(window._cs) window._cs.getTracks().forEach(function(t){t.stop();});
  var v=document.getElementById("ve"); v.srcObject=null; v.style.display="none";
  document.getElementById("vp").style.display="flex";
  document.getElementById("vo").classList.remove("act");
  document.getElementById("vw").classList.remove("sc");
  document.getElementById("camBtn").classList.remove("act");
  dot("camDot",""); setText("camStatus","CAM OFF"); setText("visionTag","INACTIVE");
  cameraActive=false;
}

// ── TEXT ───────────────────────────────────────────────────────────────
function sendText(){
  var el=document.getElementById("ti"), t=el.value.trim();
  if(!t||!ws||ws.readyState!==1) return;
  addMsg("user",t);
  ws.send(JSON.stringify({type:"text",data:t}));
  el.value=""; addTyping();
  setAIState("thinking","Processing: "+t.substring(0,40)+(t.length>40?"...":""));
}

// ── UI HELPERS ────────────────────────────────────────────────────────
function addMsg(role,text){
  var t=document.getElementById("tr"), d=document.createElement("div");
  d.className="msg "+role;
  var ic={user:"YOU",ai:"AI",sys:"SYS"};
  d.innerHTML='<div class="mi">'+(ic[role]||"SYS")+'</div><div class="mc">'+text+"</div>";
  t.appendChild(d); scrollT(); return d;
}
function addTyping(){
  if(typingEl) return;
  var t=document.getElementById("tr");
  typingEl=document.createElement("div"); typingEl.className="msg ai";
  typingEl.innerHTML='<div class="mi">AI</div><div class="mc"><span class="td1"></span><span class="td1"></span><span class="td1"></span></div>';
  t.appendChild(typingEl); scrollT();
}
function rmTyping(){if(typingEl){typingEl.remove();typingEl=null;}}
function scrollT(){document.getElementById("tr").scrollTop=99999;}
function dot(id,cls){document.getElementById(id).className="dot"+(cls?" "+cls:"");}
function setText(id,v){document.getElementById(id).textContent=v;}

function updateAnalysis(text){
  document.getElementById("es").style.display="none";
  var body=document.getElementById("ab");
  var kw=["ESP32","Arduino","MPU6050","nRF24L01","HC-SR04","MOSFET","I2C","SPI","UART","GPIO","STM32","LD2410C","NodeMCU","DevKit","resistor","capacitor","LED","OLED","servo","motor","buzzer","relay","transistor","diode","voltage regulator","crystal","antenna"];
  var found=kw.filter(function(k){return text.toLowerCase().indexOf(k.toLowerCase())>=0;});
  var card=document.getElementById("analysisCard");
  if(!card){card=document.createElement("div");card.id="analysisCard";card.className="ac";body.appendChild(card);}
  card.innerHTML='<div class="act2">Detected Components</div>'+(found.length?found.map(function(c){return'<span class="ct">'+c+"</span>";}).join(""):'<span style="color:var(--td);font-size:11px">Analysing...</span>');
  var sc=document.getElementById("statsCard");
  if(!sc){sc=document.createElement("div");sc.id="statsCard";sc.className="ac";body.appendChild(sc);}
  sc.innerHTML='<div class="act2">Session</div><div class="mr"><span class="mk">Model</span><span class="mv">Live 2.5 Flash</span></div><div class="mr"><span class="mk">Vision</span><span class="mv">'+(cameraActive?"ACTIVE":"OFF")+"</span></div>";
}

function drawWave(f32){
  var c=document.getElementById("wc"), ctx=c.getContext("2d");
  ctx.clearRect(0,0,c.width,c.height);
  ctx.beginPath(); ctx.strokeStyle="#00ff88"; ctx.lineWidth=1.5;
  ctx.shadowColor="#00ff88"; ctx.shadowBlur=3;
  var step=Math.max(1,Math.floor(f32.length/c.width));
  for(var i=0;i<c.width;i++){
    var v=f32[i*step]||0;
    var y=(v*.8+1)*c.height/2;
    if(i===0) ctx.moveTo(i,y); else ctx.lineTo(i,y);
  }
  ctx.stroke();
}
drawWave(new Float32Array(330));

document.addEventListener("click",function(){
  if(playCtx&&playCtx.state==="suspended") playCtx.resume();
  if(micCtx&&micCtx.state==="suspended") micCtx.resume();
});
</script>"""

html = html[:script_start] + new_script + html[script_end:]

with open("static/index.html", "w") as f:
    f.write(html)

print("SUCCESS — index.html patched with:")
print("  ✓ Status bar (thinking/speaking/listening/delayed/error)")
print("  ✓ Live timer showing seconds elapsed per state")
print("  ✓ Auto-timeout detection (45s → delayed, 90s → stuck)")
print("  ✓ Thinking text filtered from transcript")
print("  ✓ Thinking headers shown in status bar instead")
print("  ✓ Fixed mic audio encoding (resample + chunked base64)")
print("  ✓ Expanded component keyword list")
