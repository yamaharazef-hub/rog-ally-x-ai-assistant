/* R • ROG Ally X Assistant — browser client. No external libraries. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const DEFAULT_QUICK = [
    { id: "youtube", label: "YouTube", glyph: "▶", action: { type: "open_url", value: "https://www.youtube.com/", label: "YouTube" } },
    { id: "arena", label: "Arena Agent", glyph: "✦", action: { type: "open_url", value: "https://arena.ai/agent", label: "Arena Agent" } },
    { id: "status", label: "System status", glyph: "▤", action: { type: "terminal", value: "status", label: "system status" } },
    { id: "battery", label: "Battery", glyph: "▰", action: { type: "terminal", value: "battery", label: "battery" } },
  ];

  const state = {
    cfg: null,
    history: [],
    busy: false,
    listening: false,
    recording: false,
    recognition: null,
    recorder: null,
    stream: null,
    chunks: [],
    recordTimer: null,
    sttMode: localStorage.getItem("r.sttMode") || "browser",
    speakReplies: localStorage.getItem("r.speakReplies") !== "0",
    persistentWarning: "",
  };

  function api(path, options = {}) {
    return fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    }).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.error || `HTTP ${response.status}`);
        error.hint = data.hint || "";
        throw error;
      }
      return data;
    });
  }

  function toast(message) {
    const node = $("toast");
    node.textContent = message;
    node.classList.remove("hidden");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => node.classList.add("hidden"), 3600);
  }

  function showWarning(message) {
    const node = $("warningBanner");
    if (!message) {
      node.classList.add("hidden");
      return;
    }
    node.textContent = message;
    node.classList.remove("hidden");
  }

  function setStatus(text, kind = "") {
    $("statusText").textContent = text;
    $("statusDot").className = "dot" + (kind ? " " + kind : "");
  }

  function setMicActive(active) {
    state.listening = active || state.recording;
    $("micBtn").classList.toggle("listening", active);
    $("micBtn").setAttribute("aria-pressed", String(active));
    $("avatarStage").classList.toggle("listening", active);
    $("micCaption").textContent = active ? "Stop listening" : "Click & speak";
    if (active) setStatus("Listening…", "listening");
  }

  function appendMessage(role, text, meta = "") {
    const row = document.createElement("div");
    row.className = "message " + role;
    const prefix = document.createElement("div");
    prefix.className = "prefix";
    prefix.textContent = role === "user" ? "you@ally-x:~$" : role === "system" ? "system:~$" : "R@arena:~$";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const body = document.createElement("span");
    body.textContent = text;
    bubble.appendChild(body);
    if (meta) {
      const small = document.createElement("span");
      small.className = "meta";
      small.textContent = meta;
      bubble.appendChild(small);
    }
    if (role === "user") {
      row.appendChild(bubble);
      row.appendChild(prefix);
    } else {
      row.appendChild(prefix);
      row.appendChild(bubble);
    }
    const log = $("chatLog");
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return row;
  }

  function appendThinking() {
    const row = appendMessage("assistant", "");
    const bubble = row.querySelector(".bubble");
    bubble.className = "bubble thinking";
    bubble.innerHTML = "R is thinking<span>.</span><span>.</span><span>.</span>";
    return row;
  }

  function renderTerminal(entries) {
    const log = $("terminalLog");
    (entries || []).forEach((entry) => {
      const item = document.createElement("div");
      item.className = "term-entry" + (entry.ok === false ? " not-ok" : " ok");
      const command = document.createElement("div");
      command.className = "term-command";
      command.textContent = entry.command || "(no command)";
      item.appendChild(command);
      if (entry.note) {
        const note = document.createElement("div");
        note.className = "term-note";
        note.textContent = entry.note + (entry.simulated ? " • simulated" : "");
        item.appendChild(note);
      }
      if (entry.stdout) {
        const out = document.createElement("pre");
        out.className = "term-out";
        out.textContent = entry.stdout;
        item.appendChild(out);
      }
      if (entry.stderr) {
        const err = document.createElement("pre");
        err.className = "term-err";
        err.textContent = entry.stderr;
        item.appendChild(err);
      }
      log.appendChild(item);
    });
    log.scrollTop = log.scrollHeight;
  }

  function updateBrainBadge(provider, model) {
    const badge = $("brainBadge");
    const name = provider || (state.cfg && state.cfg.provider) || "loading";
    const label = model || (state.cfg && state.cfg.model) || "";
    badge.textContent = name === "demo" ? "DEMO BRAIN" : `${name.toUpperCase()} • ${label}`;
    badge.classList.toggle("demo", name === "demo");
  }

  function speak(text) {
    if (!state.speakReplies || !("speechSynthesis" in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = (state.cfg && state.cfg.speechLang) || "en-US";
      utterance.rate = 1.02;
      utterance.pitch = 1.06;
      const stage = $("avatarStage");
      utterance.onstart = () => stage.classList.add("speaking");
      utterance.onend = () => stage.classList.remove("speaking");
      utterance.onerror = () => stage.classList.remove("speaking");
      window.speechSynthesis.speak(utterance);
    } catch (_) {
      $("avatarStage").classList.remove("speaking");
    }
  }

  async function sendText(text, fromVoice = false) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    state.busy = true;
    $("sendBtn").disabled = true;
    appendMessage("user", text);
    const thinking = appendThinking();
    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ text, history: state.history.slice(-12) }),
      });
      thinking.remove();
      appendMessage("assistant", data.reply, `${data.provider.name} • ${data.provider.model}`);
      state.history.push({ role: "user", content: text }, { role: "assistant", content: data.reply });
      updateBrainBadge(data.provider.name, data.provider.model);
      const warnings = [...new Set([state.persistentWarning, data.warning].filter(Boolean))];
      showWarning(warnings.join(" "));
      renderTerminal(data.terminal || []);
      if (state.speakReplies || fromVoice) speak(data.reply);
    } catch (error) {
      thinking.remove();
      appendMessage("assistant", `I could not reach the assistant service: ${error.message}`, "error");
      renderTerminal([{ command: "$ r.chat --send", ok: false, stderr: error.message, note: "Local service error" }]);
      toast(error.message);
    } finally {
      state.busy = false;
      $("sendBtn").disabled = false;
      $("textInput").focus();
    }
  }

  async function runAction(action, label) {
    appendMessage("user", label || action.label || "Quick action");
    try {
      const data = await api("/api/action", { method: "POST", body: JSON.stringify({ action }) });
      appendMessage("assistant", data.reply, "guarded action");
      renderTerminal(data.terminal || []);
    } catch (error) {
      appendMessage("assistant", `That action was refused: ${error.message}`, "error");
      toast(error.message);
    }
  }

  function renderQuickActions(items) {
    const host = $("quickActions");
    host.textContent = "";
    (items || DEFAULT_QUICK).forEach((item) => {
      const button = document.createElement("button");
      button.className = "quick-btn";
      button.type = "button";
      const glyph = document.createElement("span");
      glyph.className = "quick-glyph";
      glyph.textContent = item.glyph || "•";
      const label = document.createElement("span");
      label.textContent = item.label;
      button.appendChild(glyph);
      button.appendChild(label);
      button.addEventListener("click", () => runAction(item.action, `Quick action: ${item.label}`));
      host.appendChild(button);
    });
  }

  function clearChat() {
    $("chatLog").textContent = "";
    state.history = [];
    appendMessage("assistant", "R online. Say “open YouTube”, ask for battery status, or tap the microphone.", "boot");
    renderTerminal([{ command: "$ r.session --reset", ok: true, stdout: "Conversation cleared. System action log remains below." }]);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy") ? resolve() : reject(new Error("Clipboard unavailable"));
      } catch (error) {
        reject(error);
      } finally {
        area.remove();
      }
    });
  }

  async function arenaHandoff() {
    const last = [...state.history].reverse().find((item) => item.role === "user");
    const prompt = last ? last.content : "Help me with my ROG Ally X assistant project.";
    const url = (state.cfg && state.cfg.arenaAgentUrl) || "https://arena.ai/agent";
    try {
      await copyText(prompt);
      toast("Arena Agent opened. Your last prompt was copied — paste it there.");
    } catch (_) {
      toast("Arena Agent opened. Copy your prompt from the chat if needed.");
    }
    await runAction({ type: "open_url", value: url, label: "Arena Agent" }, "Hand off to Arena Agent");
  }

  function stopBrowserSTT() {
    if (state.recognition) {
      try { state.recognition.stop(); } catch (_) { /* already stopped */ }
      setStatus("Processing speech…");
    }
    if (state.recordTimer) clearTimeout(state.recordTimer);
  }

  function startBrowserSTT() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast("Browser speech recognition is not available. Switch to Local Whisper or use Chromium/Edge.");
      return;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    const recognition = new SpeechRecognition();
    recognition.lang = (state.cfg && state.cfg.speechLang) || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    let finalText = "";
    let failed = false;
    state.recognition = recognition;
    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += piece + " ";
        else interim += piece;
      }
      $("micHint").textContent = (finalText + interim).trim() || "Listening…";
    };
    recognition.onerror = (event) => {
      failed = true;
      const messages = {
        "not-allowed": "Microphone permission was denied. Allow mic access for localhost.",
        "no-speech": "I didn't hear anything. Try again or type your request.",
        "network": "Browser speech service is unreachable. Switch to Local Whisper or type.",
      };
      const message = messages[event.error] || `Speech error: ${event.error}`;
      setStatus("Mic error", "error");
      $("micHint").textContent = message;
      toast(message);
    };
    recognition.onend = () => {
      clearTimeout(state.recordTimer);
      state.recognition = null;
      setMicActive(false);
      if (!failed && finalText.trim()) {
        setStatus("Got it");
        sendText(finalText.trim(), true);
        $("micHint").textContent = "Click the microphone to speak again.";
      } else if (!failed) {
        setStatus("R is online");
        $("micHint").textContent = "No speech detected. Tap the mic or type below.";
      }
    };
    try {
      recognition.start();
      setMicActive(true);
      $("micHint").textContent = "Listening… say “open YouTube” or ask a question.";
      state.recordTimer = setTimeout(() => { if (state.recognition) stopBrowserSTT(); }, 12000);
    } catch (error) {
      failed = true;
      setMicActive(false);
      toast(`Could not start the microphone: ${error.message}`);
    }
  }

  function decodeAudio(ctx, arrayBuffer) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const ok = (buffer) => { if (!settled) { settled = true; resolve(buffer); } };
      const bad = (error) => { if (!settled) { settled = true; reject(error); } };
      try {
        const promise = ctx.decodeAudioData(arrayBuffer, ok, bad);
        if (promise && typeof promise.then === "function") promise.then(ok, bad);
      } catch (error) {
        bad(error);
      }
    });
  }

  function encodeWav(buffer) {
    const channels = buffer.numberOfChannels;
    const length = buffer.length;
    const sampleRate = buffer.sampleRate;
    const dataSize = length * 2;
    const view = new DataView(new ArrayBuffer(44 + dataSize));
    const write = (offset, text) => { for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i)); };
    write(0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    write(8, "WAVE");
    write(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, "data");
    view.setUint32(40, dataSize, true);
    const channelData = [];
    for (let c = 0; c < channels; c += 1) channelData.push(buffer.getChannelData(c));
    for (let i = 0; i < length; i += 1) {
      let sample = 0;
      for (let c = 0; c < channels; c += 1) sample += channelData[c][i];
      sample = Math.max(-1, Math.min(1, sample / channels));
      view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return view.buffer;
  }

  async function blobToWav(blob) {
    const arrayBuffer = await blob.arrayBuffer();
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error("Web Audio is not supported in this browser");
    const ctx = new AudioCtx();
    try {
      const audio = await decodeAudio(ctx, arrayBuffer);
      return new Blob([encodeWav(audio)], { type: "audio/wav" });
    } finally {
      try { await ctx.close(); } catch (_) { /* ignore */ }
    }
  }

  async function transcribeWav(wavBlob) {
    $("micHint").textContent = "Transcribing locally…";
    setStatus("Transcribing…");
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "audio/wav" },
      body: wavBlob,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.hint = data.hint || "";
      throw error;
    }
    return data.text || "";
  }

  async function startWhisperSTT() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      toast("MediaRecorder is unavailable. Use Chromium/Edge or switch back to Browser STT.");
      return;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      state.stream = stream;
      state.chunks = [];
      const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
      const mimeType = types.find((type) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      state.recorder = recorder;
      recorder.ondataavailable = (event) => { if (event.data && event.data.size) state.chunks.push(event.data); };
      recorder.onerror = () => {
        state.recording = false;
        setMicActive(false);
        stream.getTracks().forEach((track) => track.stop());
        toast("Recording failed. Try Browser STT or type your request.");
      };
      recorder.onstop = async () => {
        clearTimeout(state.recordTimer);
        state.recording = false;
        setMicActive(false);
        stream.getTracks().forEach((track) => track.stop());
        try {
          if (!state.chunks.length) throw new Error("No audio was captured");
          const blob = new Blob(state.chunks, { type: mimeType || "audio/webm" });
          const wav = await blobToWav(blob);
          const text = await transcribeWav(wav);
          if (text.trim()) {
            setStatus("Got it");
            sendText(text.trim(), true);
            $("micHint").textContent = "Click the microphone to speak again.";
          } else {
            setStatus("R is online");
            $("micHint").textContent = "No speech detected. Tap the mic or type below.";
          }
        } catch (error) {
          setStatus("Transcription error", "error");
          $("micHint").textContent = error.hint || error.message;
          toast(error.message);
          renderTerminal([{ command: "$ r.stt --whisper", ok: false, stderr: error.message, note: error.hint || "Local Whisper error" }]);
        }
      };
      recorder.start();
      state.recording = true;
      setMicActive(true);
      $("micHint").textContent = "Recording locally… tap again to stop (max 10 seconds).";
      state.recordTimer = setTimeout(() => {
        if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
      }, 10000);
    } catch (error) {
      state.recording = false;
      setMicActive(false);
      toast(`Microphone unavailable: ${error.message}`);
    }
  }

  function stopWhisperSTT() {
    if (state.recorder && state.recorder.state !== "inactive") {
      state.recorder.stop();
      setStatus("Processing speech…");
    }
  }

  function onMicClick() {
    if (state.listening || state.recording) {
      if (state.sttMode === "whisper") stopWhisperSTT();
      else stopBrowserSTT();
      return;
    }
    if (state.sttMode === "whisper") startWhisperSTT();
    else startBrowserSTT();
  }

  function syncSettings() {
    $("sttMode").value = state.sttMode;
    $("speakReplies").checked = state.speakReplies;
    $("settingsSttMode").textContent = state.sttMode === "whisper" ? "Local Whisper" : "Browser STT";
    if (state.cfg) {
      $("settingsBrain").textContent = `${state.cfg.provider} / ${state.cfg.model}`;
      $("settingsMode").textContent = state.cfg.permissionMode;
      $("settingsDryRun").textContent = state.cfg.dryRun ? "on (simulated)" : "off (live)";
      $("settingsWhisper").textContent = state.cfg.whisperModel;
    }
  }

  async function exportTranscript() {
    try {
      const data = await api("/api/transcript");
      const blob = new Blob([JSON.stringify(data.records || [], null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "r-assistant-transcript.json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("Transcript exported.");
    } catch (error) {
      toast(error.message);
    }
  }

  function bind() {
    $("micBtn").addEventListener("click", onMicClick);
    $("composer").addEventListener("submit", (event) => {
      event.preventDefault();
      const value = $("textInput").value;
      $("textInput").value = "";
      sendText(value);
    });
    $("quickActions").addEventListener("click", (event) => event.preventDefault());
    $("clearChat").addEventListener("click", clearChat);
    $("clearTerminal").addEventListener("click", () => { $("terminalLog").textContent = ""; });
    $("exportBtn").addEventListener("click", exportTranscript);
    $("arenaBtn").addEventListener("click", arenaHandoff);
    $("settingsBtn").addEventListener("click", () => $("settingsPanel").classList.toggle("hidden"));
    $("closeSettings").addEventListener("click", () => $("settingsPanel").classList.add("hidden"));
    $("sttMode").addEventListener("change", (event) => {
      state.sttMode = event.target.value;
      localStorage.setItem("r.sttMode", state.sttMode);
      $("micHint").textContent = state.sttMode === "whisper"
        ? "Local Whisper selected. First use may download a model."
        : "Browser speech selected. Chromium/Edge recommended.";
      syncSettings();
    });
    $("speakReplies").addEventListener("change", (event) => {
      state.speakReplies = event.target.checked;
      localStorage.setItem("r.speakReplies", state.speakReplies ? "1" : "0");
      if (!state.speakReplies && "speechSynthesis" in window) window.speechSynthesis.cancel();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        $("settingsPanel").classList.add("hidden");
        if (state.listening) onMicClick();
      }
    });
  }

  async function init() {
    bind();
    syncSettings();
    appendMessage("assistant", "R online. Say “open YouTube”, ask for battery status, or tap the microphone.", "boot");
    renderTerminal([{ command: '$ r.boot --device "ROG Ally X" --os "Bazzite"', ok: true, stdout: "Guarded action dispatcher ready.\nArena brain adapter ready.", note: "local service" }]);
    try {
      const cfg = await api("/api/config");
      state.cfg = cfg;
      updateBrainBadge(cfg.provider, cfg.model);
      renderQuickActions(cfg.quickActions);
      syncSettings();
      const warnings = [];
      if (cfg.dryRun) warnings.push("Preview dry-run mode: system actions are shown in the terminal panel but not executed. On your Ally X, run without --dry-run.");
      if (!cfg.brainConfigured || cfg.provider === "demo") warnings.push("Demo brain is active. Add ARENA_API_KEY to .env and restart the service for full Arena AI replies.");
      state.persistentWarning = warnings.join(" ");
      showWarning(state.persistentWarning);
    } catch (error) {
      updateBrainBadge("offline", "");
      renderQuickActions(DEFAULT_QUICK);
      showWarning(`Could not load /api/config: ${error.message}`);
    }
    $("textInput").focus();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
