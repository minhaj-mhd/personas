class LiveAudioClient {
    constructor() {
        this.ws = null;
        this.inputCtx = null;
        this.outputCtx = null;
        this.processor = null;
        this.mediaStream = null;
        this.activeSources = [];
        this.nextStartTime = 0;
        
        // Screen-share state (continuous frames streamed into the live session)
        this.screenStream = null;
        this.screenInterval = null;

        // Callbacks for UI updates (to be hooked up by WP-4)
        this.onStatus = null;
        this.onInputTranscript = null;
        this.onOutputTranscript = null;
        this.onLevel = null; // (rms: number) -> void, called every mic frame for live level meter
        this.onScreenShare = null; // (active: bool) -> void
    }

    // --- Screen sharing / capture (Gemini Live accepts image frames as visual input) ---

    _sendJson(obj) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(obj));
            return true;
        }
        return false;
    }

    // Draw a media stream's current frame to a canvas, downscaled to bound payload size,
    // and return { mime, data } where data is base64 (no data: prefix).
    _grabFrame(video, quality = 0.6, maxW = 1280) {
        const vw = video.videoWidth || maxW;
        const vh = video.videoHeight || 720;
        const scale = Math.min(1, maxW / vw);
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(vw * scale));
        canvas.height = Math.max(1, Math.round(vh * scale));
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', quality);
        return { mime: 'image/jpeg', data: dataUrl.split(',')[1] };
    }

    async _displayVideo() {
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
        const video = document.createElement('video');
        video.srcObject = stream;
        video.muted = true;
        await video.play();
        return { stream, video };
    }

    // Start streaming the shared screen to the live session at ~1 fps. Requires an
    // active session (frames go over the same WebSocket as a JSON image_frame message).
    async startScreenShare(fps = 1) {
        if (this.screenStream) return true;
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            if (this.onStatus) this.onStatus('error', 'Go live before sharing your screen');
            return false;
        }
        let stream, video;
        try {
            ({ stream, video } = await this._displayVideo());
        } catch (e) {
            console.warn('Screen share cancelled/denied:', e && e.name);
            return false;
        }
        this.screenStream = stream;
        this._screenVideo = video;
        // If the user stops sharing via the browser's own UI, tear down cleanly.
        stream.getVideoTracks()[0].addEventListener('ended', () => this.stopScreenShare());

        this.screenInterval = setInterval(() => {
            try {
                const frame = this._grabFrame(video);
                this._sendJson({ type: 'image_frame', mime: frame.mime, data: frame.data });
            } catch (e) {
                console.warn('frame grab failed', e);
            }
        }, Math.max(200, Math.round(1000 / fps)));

        if (this.onScreenShare) this.onScreenShare(true);
        return true;
    }

    stopScreenShare() {
        if (this.screenInterval) { clearInterval(this.screenInterval); this.screenInterval = null; }
        if (this.screenStream) {
            this.screenStream.getTracks().forEach((t) => t.stop());
            this.screenStream = null;
        }
        this._screenVideo = null;
        if (this.onScreenShare) this.onScreenShare(false);
    }

    // One-shot: capture the current screen as a single JPEG Blob (prompts device picker).
    // Used by the "capture screen" button to upload a snapshot.
    async captureScreenFrame(quality = 0.85) {
        const { stream, video } = await this._displayVideo();
        try {
            // Give the first frame a beat to paint.
            await new Promise((r) => setTimeout(r, 150));
            const { data } = this._grabFrame(video, quality, 1920);
            const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
            return new Blob([bytes], { type: 'image/jpeg' });
        } finally {
            stream.getTracks().forEach((t) => t.stop());
        }
    }

    // Send an already-captured image Blob into the live session (if one is active).
    async sendImageBlobToLive(blob) {
        const buf = await blob.arrayBuffer();
        let binary = '';
        const bytes = new Uint8Array(buf);
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        return this._sendJson({ type: 'image_frame', mime: blob.type || 'image/jpeg', data: btoa(binary) });
    }

    // track.muted can lag for a moment after getUserMedia; wait, then read the real state.
    async _settleMuted(track, ms = 300) {
        await new Promise((r) => setTimeout(r, ms));
        return track.muted;
    }

    // Acquire a microphone that is actually delivering audio. The default device is
    // sometimes handed back MUTED (another tab/app holding the mic under Realtek's
    // exclusive mode, or Chrome defaulting to a muted device). When that happens we
    // scan the other input devices and switch to the first non-muted one automatically.
    async _acquireMic() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const track = stream.getAudioTracks()[0];
        await this._settleMuted(track);
        if (track && !track.muted) {
            console.log("Mic acquired:", track.label);
            return stream;
        }

        console.warn(`Default mic "${track && track.label}" came back muted — scanning other input devices...`);
        let devices = [];
        try { devices = await navigator.mediaDevices.enumerateDevices(); } catch (e) { /* no-op */ }
        const mics = devices.filter((d) => d.kind === "audioinput" && d.deviceId && d.deviceId !== "default");

        for (const m of mics) {
            try {
                const s = await navigator.mediaDevices.getUserMedia({ audio: { deviceId: { exact: m.deviceId } } });
                const t = s.getAudioTracks()[0];
                await this._settleMuted(t);
                console.log(`  candidate "${m.label}" muted=${t && t.muted}`);
                if (t && !t.muted) {
                    stream.getTracks().forEach((x) => x.stop());
                    console.log("Switched to working mic:", m.label);
                    return s;
                }
                s.getTracks().forEach((x) => x.stop());
            } catch (e) {
                console.warn(`  device "${m.label}" failed:`, e.name);
            }
        }

        // Everything came back muted (likely another app/tab owns the mic). Return the
        // default anyway; the mute-detection in start() will tell the user what's wrong.
        console.warn("No un-muted input device found — all candidates muted.");
        return stream;
    }

    // Overridable so subclasses (e.g. the panel) can point at a different endpoint.
    _wsUrl() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}/ws/live/${window.chatConfig.conversationId}`;
    }

    async start() {
        if (this.ws) return;

        try {
            // NOTE: requesting echoCancellation/noiseSuppression explicitly causes this
            // machine's audio driver to hand back a silent track (verified: rms=0 on every
            // frame with those constraints, real signal with plain `audio: true`). Use
            // headphones when testing to avoid speaker->mic feedback since AEC is unavailable.
            this.mediaStream = await this._acquireMic();
            const t0 = this.mediaStream.getAudioTracks()[0];
            if (t0) {
                t0.enabled = true;
                // `track.muted === true` means the OS/hardware is withholding audio (mic
                // mute key, Windows-muted device, or a device with no signal). The browser
                // then streams pure silence (rms=0) with no error — which looks like the
                // session "randomly broke." Surface it instead of failing silently.
                if (t0.muted) {
                    console.warn("Mic track is muted at the OS/hardware level:", t0.label);
                    if (this.onStatus) this.onStatus("error", `Mic "${t0.label}" is muted — unmute it (mic key / Windows Sound settings)`);
                }
                t0.onmute = () => {
                    console.warn("Mic muted mid-session:", t0.label);
                    if (this.onStatus) this.onStatus("error", "Microphone muted — unmute to continue");
                };
                t0.onunmute = () => {
                    console.log("Mic unmuted:", t0.label);
                    if (this.onStatus) this.onStatus("live", "");
                };
            }
        } catch (e) {
            console.error("Microphone access denied or error:", e);
            if (this.onStatus) this.onStatus("error", "Microphone access denied");
            return;
        }

        const wsUrl = this._wsUrl();
        this.ws = new WebSocket(wsUrl);
        this.ws.binaryType = "arraybuffer";

        if (this.onStatus) this.onStatus("connecting");

        this.ws.onopen = () => {
            console.log("Live WS connected.");
            if (this._onWsOpen) this._onWsOpen();
        };

        this.ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                this.handleAudioFrame(event.data);
            } else {
                this.handleJsonMessage(event.data);
            }
        };

        this.ws.onclose = () => {
            console.log("Live WS closed.");
            this.stop();
        };

        this.ws.onerror = (e) => {
            console.error("Live WS error:", e);
        };
    }

    handleJsonMessage(dataStr) {
        let msg;
        try { 
            msg = JSON.parse(dataStr); 
        } catch (e) { 
            console.error("Failed to parse WS message:", dataStr);
            return; 
        }
        
        if (msg.type === "ready") {
            if (this.onStatus) this.onStatus("live", msg.voice || "");
            this.startAudioIOLoop();
        } else if (msg.type === "reconnecting") {
            // Upstream Live connection dropped; the server is resuming it under the same
            // WebSocket. Drop any stale scheduled audio and show a transient status. Do
            // NOT touch the mic/audio pipeline — it stays running across the resume.
            console.warn(`Live connection dropped; resuming (attempt ${msg.attempt || 1})...`);
            this.flushPlayback();
            if (this.onStatus) this.onStatus("connecting", "Reconnecting…");
        } else if (msg.type === "resumed") {
            // Session resumed successfully. The audio loop is already running, so just
            // restore the live status — must NOT call startAudioIOLoop() again.
            console.log("Live session resumed.");
            if (this.onStatus) this.onStatus("live", msg.voice || "");
        } else if (msg.type === "input_transcript") {
            if (this.onInputTranscript) this.onInputTranscript(msg.text, msg.final);
        } else if (msg.type === "output_transcript") {
            if (this.onOutputTranscript) this.onOutputTranscript(msg.text, msg.final);
        } else if (msg.type === "interrupted") {
            this.flushPlayback();
        } else if (msg.type === "turn_complete") {
            // We can handle turn completion if needed by the UI
        } else if (msg.type === "info" || msg.type === "error") {
            console.log(`Live server message (${msg.type}):`, msg.detail);
            if (msg.type === "error" && this.onStatus) {
                this.onStatus("error", msg.detail);
            }
        } else if (msg.type === "go_away") {
            console.warn("Server sent go_away.");
        }
    }

    async startAudioIOLoop() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        // Capture at the hardware-native rate and downsample to 16k ourselves. Forcing a
        // 16k AudioContext is unreliable (many browsers ignore it and run at 48k), which
        // makes Gemini receive mislabeled audio it can't recognize — so it never replies.
        this.inputCtx = new AudioContextClass();
        this.outputCtx = new AudioContextClass({ sampleRate: 24000 });

        // AudioContexts start "suspended" under the autoplay policy; resume or the capture
        // callback never fires and output never plays.
        try { await this.inputCtx.resume(); } catch (e) { /* gesture already occurred */ }
        try { await this.outputCtx.resume(); } catch (e) { /* no-op */ }

        const inRate = this.inputCtx.sampleRate;
        const t = this.mediaStream.getAudioTracks()[0];
        const trackInfo = t ? { label: t.label, enabled: t.enabled, muted: t.muted, state: t.readyState } : null;
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: "client_info", inputRate: inRate, outputRate: this.outputCtx.sampleRate, track: trackInfo }));
        }

        const source = this.inputCtx.createMediaStreamSource(this.mediaStream);
        this.processor = this.inputCtx.createScriptProcessor(4096, 1, 1);

        this.processor.onaudioprocess = (e) => {
            const input = e.inputBuffer.getChannelData(0);

            if (this.onLevel) {
                let sumSq = 0;
                for (let i = 0; i < input.length; i++) sumSq += input[i] * input[i];
                this.onLevel(Math.sqrt(sumSq / input.length));
            }

            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

            // No AEC available on this device/driver combo (see start()), so without
            // headphones the speaker output leaks into the mic and Gemini's VAD reads
            // its own voice as a user interruption, cutting playback off mid-sentence.
            // Gate mic uplink while assistant audio is scheduled to play, to prevent that;
            // this trades barge-in (on speakers) for actually being able to hear replies.
            // Use the playback clock (nextStartTime vs now) rather than the activeSources
            // array so a missed `onended` can never wedge the mic shut permanently.
            if (this.outputCtx && this.nextStartTime > this.outputCtx.currentTime + 0.05) return;

            const down = this.downsampleTo16k(input, inRate);
            const intData = new Int16Array(down.length);
            for (let i = 0; i < down.length; i++) {
                let s = Math.max(-1, Math.min(1, down[i]));
                intData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            this.ws.send(intData.buffer);
        };

        // Keep the processing graph alive without routing the mic to the speakers
        // (a muted gain node) — avoids hearing yourself / feedback into the mic.
        const mute = this.inputCtx.createGain();
        mute.gain.value = 0;
        source.connect(this.processor);
        this.processor.connect(mute);
        mute.connect(this.inputCtx.destination);
    }

    downsampleTo16k(buffer, inRate) {
        if (inRate === 16000) return buffer;
        const ratio = inRate / 16000;
        const newLen = Math.floor(buffer.length / ratio);
        const result = new Float32Array(newLen);
        for (let i = 0; i < newLen; i++) {
            result[i] = buffer[Math.floor(i * ratio)];
        }
        return result;
    }

    handleAudioFrame(arrayBuffer) {
        if (!this.outputCtx) return;
        if (this.outputCtx.state === "suspended") this.outputCtx.resume();

        const intData = new Int16Array(arrayBuffer);
        const floatData = new Float32Array(intData.length);
        
        // Convert Int16 to Float32
        for (let i = 0; i < intData.length; i++) {
            floatData[i] = intData[i] / 32768.0;
        }

        const audioBuffer = this.outputCtx.createBuffer(1, floatData.length, 24000);
        audioBuffer.getChannelData(0).set(floatData);

        const source = this.outputCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.outputCtx.destination);

        // Gapless playback scheduling
        if (this.nextStartTime < this.outputCtx.currentTime) {
            this.nextStartTime = this.outputCtx.currentTime;
        }

        source.start(this.nextStartTime);
        this.nextStartTime += audioBuffer.duration;
        
        this.activeSources.push(source);
        source.onended = () => {
            this.activeSources = this.activeSources.filter(s => s !== source);
        };
    }

    flushPlayback() {
        this.activeSources.forEach(s => {
            try { s.stop(); } catch (e) {}
        });
        this.activeSources = [];
        this.nextStartTime = this.outputCtx ? this.outputCtx.currentTime : 0;
    }

    stop() {
        this.stopScreenShare();
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.inputCtx) {
            this.inputCtx.close();
            this.inputCtx = null;
        }
        if (this.outputCtx) {
            this.outputCtx.close();
            this.outputCtx = null;
        }
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(t => t.stop());
            this.mediaStream = null;
        }
        if (this.ws) {
            if (this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: "audio_end" }));
                this.ws.send(JSON.stringify({ type: "stop" }));
                this.ws.close();
            }
            this.ws = null;
        }
        this.flushPlayback();
        if (this.onStatus) this.onStatus("ended");
    }
}

window.LiveAudioClient = LiveAudioClient;
