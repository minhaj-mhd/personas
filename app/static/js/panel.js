// Voice-panel client (P-4). Reuses LiveAudioClient's mic capture + audio playback engine,
// but points at /ws/panel/{id}, does the select_roster handshake, and handles the panel
// message protocol (active_speaker / transcript / handoff). See live.js for the audio engine.

class PanelAudioClient extends LiveAudioClient {
    constructor(config) {
        super();
        this.conversationId = config.conversationId;
        this.personaIds = config.personaIds || [];

        // Panel-specific UI callbacks
        this.onReady = null;          // (roster) => void
        this.onActiveSpeaker = null;  // (personaId, name) => void
        this.onPanelTranscript = null;// (speaker, text, final) => void
        this.onHandoff = null;        // (toName) => void
        this.onTurnComplete = null;   // () => void
    }

    _wsUrl() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}/ws/panel/${this.conversationId}`;
    }

    // Panel handshake: the server expects select_roster as the FIRST message.
    _onWsOpen() {
        this.ws.send(JSON.stringify({ type: "select_roster", persona_ids: this.personaIds }));
    }

    handleJsonMessage(dataStr) {
        let msg;
        try { msg = JSON.parse(dataStr); } catch (e) { console.error("panel parse err", dataStr); return; }

        switch (msg.type) {
            case "ready":
                if (this.onReady) this.onReady(msg.roster || []);
                if (this.onStatus) this.onStatus("live", "");
                this.startAudioIOLoop();
                break;
            case "active_speaker":
                if (this.onActiveSpeaker) this.onActiveSpeaker(msg.persona_id, msg.name);
                break;
            case "transcript":
                if (this.onPanelTranscript) this.onPanelTranscript(msg.speaker, msg.text, msg.final);
                break;
            case "handoff":
                // Floor is switching; stop any in-flight playback from the previous speaker.
                this.flushPlayback();
                if (this.onHandoff) this.onHandoff(msg.to_name);
                break;
            case "interrupted":
                this.flushPlayback();
                break;
            case "turn_complete":
                if (this.onTurnComplete) this.onTurnComplete();
                break;
            case "reconnecting":
                // Upstream Live connection dropped; the server is resuming the current
                // speaker under the same WebSocket. Drop stale playback; leave the mic/
                // audio pipeline running (do NOT call startAudioIOLoop again).
                console.warn(`Panel connection dropped; resuming (attempt ${msg.attempt || 1})...`);
                this.flushPlayback();
                if (this.onStatus) this.onStatus("connecting", "Reconnecting…");
                break;
            case "resumed":
                console.log("Panel session resumed.");
                if (this.onStatus) this.onStatus("live", "");
                break;
            case "error":
                console.error("Panel server error:", msg.detail);
                if (this.onStatus) this.onStatus("error", msg.detail);
                break;
            default:
                break;
        }
    }
}

window.PanelAudioClient = PanelAudioClient;
