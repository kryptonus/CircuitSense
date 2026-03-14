#!/bin/bash
# Fix mic audio encoding in CircuitSense index.html
# Run from ~/circuitsense/

FILE="static/index.html"

# Replace the entire startMic function with fixed version
python3 << 'PYEOF'
import re

with open("static/index.html", "r") as f:
    content = f.read()

# Replace the old startMic function
old_startMic = '''function startMic(){
  if(!isConnected||!ws||ws.readyState!==1){addMsg("sys","Not connected");return;}
  if(processor) return;
  if(!micCtx) micCtx=new(window.AudioContext||window.webkitAudioContext)({sampleRate:16000});
  var resume=micCtx.state==="suspended"?micCtx.resume():Promise.resolve();
  resume.then(function(){
    navigator.mediaDevices.getUserMedia({audio:{sampleRate:16000,channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}})
    .then(function(stream){
      mediaStream=stream;
      var src=micCtx.createMediaStreamSource(stream);
      processor=micCtx.createScriptProcessor(2048,1,1);
      processor.onaudioprocess=function(e){
        if(!ws||ws.readyState!==1||isPlaying) return;
        var f32=e.inputBuffer.getChannelData(0);
        var i16=new Int16Array(f32.length);
        for(var i=0;i<f32.length;i++) i16[i]=Math.max(-32768,Math.min(32767,f32[i]*32768));
        ws.send(JSON.stringify({type:"audio",data:btoa(String.fromCharCode.apply(null,new Uint8Array(i16.buffer)))}));
        drawWave(f32);
      };
      src.connect(processor);
      processor.connect(micCtx.destination);
      document.getElementById("micBtn").classList.add("rec");
      setText("micLabel","Listening...");
      setText("audioTag","REC");
      addTyping();
    })
    .catch(function(err){addMsg("sys","Mic error: "+err.message);});
  });
}'''

new_startMic = '''function pcmToBase64(i16arr){
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
    var s0=f32[idx]||0;
    var s1=f32[Math.min(idx+1,f32.length-1)]||0;
    out[i]=s0+(s1-s0)*frac;
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
      addTyping();
    })
    .catch(function(err){addMsg("sys","Mic error: "+err.message);});
  });
}'''

if old_startMic in content:
    content = content.replace(old_startMic, new_startMic)
    with open("static/index.html", "w") as f:
        f.write(content)
    print("SUCCESS: startMic replaced with fixed version")
else:
    print("ERROR: Could not find old startMic function. Manual edit needed.")
    # Try to check what's there
    idx = content.find("function startMic()")
    if idx >= 0:
        print("Found startMic at position", idx)
        print("Snippet:", repr(content[idx:idx+200]))
    else:
        print("startMic function not found at all!")

PYEOF
