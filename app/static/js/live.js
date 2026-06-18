class LiveAudioClient {
    constructor() {
        this.ws = null;
        this.inputCtx = null;
        this.outputCtx = null;
        this.processor = null;
        this.mediaStream = null;
        this.activeSources = [];
        this.nextStartTime = 0;
        
        // Callbacks for UI updates (to be hooked up by WP-4)
        this.onStatus = null;
        this.onInputTranscript = null;
        this.onOutputTranscript = null;
    }

    async start() {
        if (this.ws) return;
        
        try {
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
            });
        } catch (e) {
            console.error("Microphone access denied or error:", e);
            if (this.onStatus) this.onStatus("Mic Error", "error");
            return;
        }

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/live/${window.chatConfig.conversationId}`;
        this.ws = new WebSocket(wsUrl);
        this.ws.binaryType = "arraybuffer";

        if (this.onStatus) this.onStatus("Connecting...", "info");

        this.ws.onopen = () => {
            console.log("Live WS connected.");
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
            if (this.onStatus) this.onStatus(`Live (${msg.voice || 'Unknown'})`, "ready");
            this.startAudioIOLoop();
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
                this.onStatus(msg.detail, "error");
            }
        } else if (msg.type === "go_away") {
            console.warn("Server sent go_away.");
        }
    }

    async startAudioIOLoop() {
        // Create audio contexts with specific sample rates per the shared contract
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        this.inputCtx = new AudioContextClass({ sampleRate: 16000 });
        this.outputCtx = new AudioContextClass({ sampleRate: 24000 });
        
        const source = this.inputCtx.createMediaStreamSource(this.mediaStream);
        
        // Use ScriptProcessorNode (deprecated but widely supported, or switch to AudioWorklet if required later)
        this.processor = this.inputCtx.createScriptProcessor(4096, 1, 1);
        
        this.processor.onaudioprocess = (e) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
            const floatData = e.inputBuffer.getChannelData(0);
            const intData = new Int16Array(floatData.length);
            
            // Convert Float32 to Int16
            for (let i = 0; i < floatData.length; i++) {
                let s = Math.max(-1, Math.min(1, floatData[i]));
                intData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            
            this.ws.send(intData.buffer);
        };

        source.connect(this.processor);
        this.processor.connect(this.inputCtx.destination);
    }

    handleAudioFrame(arrayBuffer) {
        if (!this.outputCtx) return;
        
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
        if (this.onStatus) this.onStatus("Disconnected", "ended");
    }
}

window.LiveAudioClient = LiveAudioClient;
