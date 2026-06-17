(function() {
    // Check config
    if (!window.chatConfig) {
        console.error("Chat configuration is missing!");
        return;
    }

    const { conversationId, personaName, isBuiltin } = window.chatConfig;

    // DOM Elements
    const connectionStatus = document.getElementById("connection-status");
    const actionStatus = document.getElementById("action-status");
    const statusText = document.getElementById("status-text");
    const interruptBtn = document.getElementById("interrupt-btn");
    const messagesContainer = document.getElementById("messages-container");
    const chatForm = document.getElementById("chat-form");
    const messageInput = document.getElementById("message-input");
    const sendBtn = document.getElementById("send-btn");
    const emptyState = document.getElementById("chat-empty-state");

    const micBtn = document.getElementById("mic-btn");

    let ws = null;
    let currentAssistantBubble = null;
    let currentAssistantTextNode = null;

    // SpeechRecognition Setup
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';
    } else {
        console.warn("SpeechRecognition is not supported in this browser.");
        if (micBtn) {
            micBtn.classList.add("hidden");
            micBtn.disabled = true;
        }
    }

    // Setup WebSocket connection
    function connect() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/ws/chat/${conversationId}`;

        updateConnectionState("connecting");

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket connection established.");
            updateConnectionState("connected");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWSMessage(data);
            } catch (err) {
                console.error("Error parsing WebSocket message:", err);
            }
        };

        ws.onclose = () => {
            console.warn("WebSocket connection closed. Retrying in 3 seconds...");
            updateConnectionState("disconnected");
            setTimeout(connect, 3000);
        };

        ws.onerror = (err) => {
            console.error("WebSocket error:", err);
            updateConnectionState("disconnected");
        };
    }

    function updateConnectionState(state) {
        if (!connectionStatus) return;
        connectionStatus.className = "w-2.5 h-2.5 rounded-full transition-all duration-300";
        if (state === "connected") {
            connectionStatus.classList.add("bg-emerald-500", "shadow-lg", "shadow-emerald-500/50");
            connectionStatus.title = "Connected";
            enableChat();
        } else if (state === "connecting") {
            connectionStatus.classList.add("bg-amber-500", "animate-pulse");
            connectionStatus.title = "Connecting...";
            disableChat();
        } else {
            connectionStatus.classList.add("bg-rose-500", "shadow-lg", "shadow-rose-500/50");
            connectionStatus.title = "Disconnected";
            disableChat();
        }
    }

    function disableChat() {
        if (messageInput) messageInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
    }

    function enableChat() {
        if (messageInput) messageInput.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
    }

    function showActionStatus(type) {
        if (!actionStatus || !statusText) return;
        actionStatus.classList.remove("hidden");
        statusText.innerText = type === "thinking" ? "Thinking" : "Streaming";
    }

    function hideActionStatus() {
        if (actionStatus) actionStatus.classList.add("hidden");
    }

    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    // Format current time as HH:MM AM/PM
    function getFormattedTime() {
        const now = new Date();
        let hours = now.getHours();
        let minutes = now.getMinutes();
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12; // the hour '0' should be '12'
        minutes = minutes < 10 ? '0'+minutes : minutes;
        return `${hours}:${minutes} ${ampm}`;
    }

    // Append a user chat bubble to DOM
    function appendUserBubble(text) {
        if (emptyState) {
            emptyState.classList.add("hidden");
        }

        const flexWrapper = document.createElement("div");
        flexWrapper.className = "flex justify-end";

        const bubble = document.createElement("div");
        bubble.className = "chat-bubble bg-brand-600 text-white rounded-2xl rounded-tr-none px-4 py-3 shadow-md";

        const content = document.createElement("p");
        content.className = "text-sm font-light leading-relaxed whitespace-pre-wrap";
        content.innerText = text;

        const timestamp = document.createElement("span");
        timestamp.className = "block text-[9px] text-brand-200 font-mono text-right mt-1.5";
        timestamp.innerText = getFormattedTime();

        bubble.appendChild(content);
        bubble.appendChild(timestamp);
        flexWrapper.appendChild(bubble);

        // Insert before streaming anchor
        const anchor = document.getElementById("live-streaming-anchor");
        messagesContainer.insertBefore(flexWrapper, anchor);
        scrollToBottom();
    }

    // Create and append assistant bubble for stream
    function createAssistantBubble() {
        const flexWrapper = document.createElement("div");
        flexWrapper.className = "flex justify-start";

        const bubble = document.createElement("div");
        bubble.className = "chat-bubble bg-slate-900 border border-slate-850 text-slate-100 rounded-2xl rounded-tl-none px-4 py-3 shadow-md";

        const content = document.createElement("p");
        content.className = "text-sm font-light leading-relaxed whitespace-pre-wrap";
        
        const timestamp = document.createElement("span");
        timestamp.className = "block text-[9px] text-slate-500 font-mono mt-1.5";
        timestamp.innerText = getFormattedTime();

        bubble.appendChild(content);
        bubble.appendChild(timestamp);
        flexWrapper.appendChild(bubble);

        const anchor = document.getElementById("live-streaming-anchor");
        messagesContainer.insertBefore(flexWrapper, anchor);

        currentAssistantBubble = bubble;
        currentAssistantTextNode = content;
        scrollToBottom();
    }

    // Process incoming WS Messages
    function handleWSMessage(data) {
        if (data.type === "token") {
            // First token of the response
            if (!currentAssistantBubble) {
                createAssistantBubble();
                showActionStatus("streaming");
                if (interruptBtn) {
                    interruptBtn.classList.remove("hidden");
                    interruptBtn.disabled = false;
                }
            }

            // Append chunk
            currentAssistantTextNode.textContent += data.delta;
            scrollToBottom();

        } else if (data.type === "message_complete") {
            // Stream complete
            resetUIState();
            scrollToBottom();
            speakText(data.text);

        } else if (data.type === "interrupted") {
            // Stream was interrupted
            if (currentAssistantTextNode) {
                currentAssistantTextNode.textContent += " [interrupted]";
            }
            resetUIState();
            scrollToBottom();
            window.speechSynthesis.cancel();

        } else if (data.type === "error") {
            console.error("Server error:", data.detail);
            resetUIState();
            
            // Append error bubble
            const flexWrapper = document.createElement("div");
            flexWrapper.className = "flex justify-start";
            const bubble = document.createElement("div");
            bubble.className = "chat-bubble bg-rose-950/20 border border-rose-900/30 text-rose-400 rounded-2xl rounded-tl-none px-4 py-3 shadow-md text-xs font-mono";
            bubble.innerText = `Error: ${data.detail}`;
            flexWrapper.appendChild(bubble);
            
            const anchor = document.getElementById("live-streaming-anchor");
            messagesContainer.insertBefore(flexWrapper, anchor);
            scrollToBottom();

        } else if (data.type === "info") {
            console.log("Server info:", data.detail);
        }
    }

    function resetUIState() {
        hideActionStatus();
        if (interruptBtn) {
            interruptBtn.classList.add("hidden");
            interruptBtn.disabled = true;
        }
        currentAssistantBubble = null;
        currentAssistantTextNode = null;
        enableChat();
        if (messageInput) {
            messageInput.focus();
        }
    }

    // Send message helper
    function sendMessage(text) {
        const trimmed = text.trim();
        if (!trimmed) return;

        if (!ws || ws.readyState !== WebSocket.OPEN) {
            console.error("Cannot send message. WebSocket is not open.");
            return;
        }

        // Clear input & disable UI
        if (messageInput) {
            messageInput.value = "";
        }
        disableChat();
        showActionStatus("thinking");

        // Render user message instantly
        appendUserBubble(trimmed);

        // Send via WebSocket
        ws.send(JSON.stringify({
            type: "user_message",
            text: trimmed
        }));
    }

    // Form submission handler
    if (chatForm) {
        chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            if (messageInput) {
                sendMessage(messageInput.value);
            }
        });
    }

    // Interrupt button click handler
    if (interruptBtn) {
        interruptBtn.addEventListener("click", () => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: "interrupt"
                }));
                interruptBtn.disabled = true;
            }
            window.speechSynthesis.cancel();
        });
    }

    // Push to Talk implementation
    function startRecording() {
        window.speechSynthesis.cancel();

        // Trigger interrupt-btn click if active to cancel ongoing server generation
        if (interruptBtn && !interruptBtn.classList.contains("hidden") && !interruptBtn.disabled) {
            interruptBtn.click();
        }

        // Change button style: add bg-rose-600 text-white, remove bg-slate-900 text-slate-400
        if (micBtn) {
            micBtn.classList.remove("bg-slate-900", "text-slate-400");
            micBtn.classList.add("bg-rose-600", "text-white");
        }

        if (messageInput) {
            messageInput.placeholder = 'Listening...';
            messageInput.value = '';
        }

        if (recognition && !isRecording) {
            try {
                recognition.start();
                isRecording = true;
            } catch (err) {
                console.error("Failed to start SpeechRecognition:", err);
            }
        }
    }

    function stopRecording() {
        // Reset button style
        if (micBtn) {
            micBtn.classList.remove("bg-rose-600", "text-white");
            micBtn.classList.add("bg-slate-900", "text-slate-400");
        }

        if (messageInput) {
            messageInput.placeholder = 'Type your message here...';
        }

        if (recognition && isRecording) {
            try {
                recognition.stop();
            } catch (err) {
                console.error("Failed to stop SpeechRecognition:", err);
            }
            isRecording = false;
        }
    }

    // Speech Recognition Event Handlers
    if (recognition) {
        recognition.onresult = (event) => {
            let fullTranscript = '';
            for (let i = 0; i < event.results.length; i++) {
                fullTranscript += event.results[i][0].transcript;
            }
            if (messageInput) {
                messageInput.value = fullTranscript;
            }
        };

        recognition.onend = () => {
            isRecording = false;
            // Reset style and placeholder in case of automatic stop
            if (micBtn) {
                micBtn.classList.remove("bg-rose-600", "text-white");
                micBtn.classList.add("bg-slate-900", "text-slate-400");
            }
            if (messageInput) {
                messageInput.placeholder = 'Type your message here...';
                const text = messageInput.value.trim();
                if (text) {
                    sendMessage(text);
                }
            }
        };

        recognition.onerror = (event) => {
            console.error("SpeechRecognition error:", event.error);
            stopRecording();
        };
    }

    // PTT Event Listeners on Mic Button
    if (micBtn && recognition) {
        micBtn.addEventListener("mousedown", (e) => {
            e.preventDefault();
            startRecording();
        });

        micBtn.addEventListener("touchstart", (e) => {
            e.preventDefault();
            startRecording();
        });

        micBtn.addEventListener("mouseup", (e) => {
            if (isRecording) {
                e.preventDefault();
                stopRecording();
            }
        });

        micBtn.addEventListener("mouseleave", (e) => {
            if (isRecording) {
                e.preventDefault();
                stopRecording();
            }
        });

        micBtn.addEventListener("touchend", (e) => {
            if (isRecording) {
                e.preventDefault();
                stopRecording();
            }
        });
    }

    // Keyboard Event Listeners
    document.addEventListener("keydown", (e) => {
        if (e.code === "Space" || e.key === " ") {
            if (document.activeElement !== messageInput) {
                if (recognition && !isRecording) {
                    e.preventDefault();
                    startRecording();
                }
            }
        }
    });

    document.addEventListener("keyup", (e) => {
        if (e.code === "Space" || e.key === " ") {
            if (isRecording) {
                e.preventDefault();
                stopRecording();
            }
        }
    });

    // Browser Speech Synthesis for TTS
    function cleanTextForSpeech(text) {
        if (!text) return "";
        let cleaned = text.replace(/[*_`]/g, '');
        cleaned = cleaned.replace(/\[interrupted\]/gi, '');
        return cleaned.trim();
    }

    function speakText(text) {
        window.speechSynthesis.cancel();

        const cleanedText = cleanTextForSpeech(text);
        if (!cleanedText) return;

        const utterance = new SpeechSynthesisUtterance(cleanedText);

        const voices = window.speechSynthesis.getVoices();
        let selectedVoice = null;

        function selectVoice(voiceList) {
            let voice = voiceList.find(v => v.name.includes("Google") && (v.lang.startsWith("en-") || v.lang.startsWith("en_")));
            if (!voice) {
                voice = voiceList.find(v => v.lang.startsWith("en-") || v.lang.startsWith("en_"));
            }
            return voice;
        }

        selectedVoice = selectVoice(voices);
        if (selectedVoice) {
            utterance.voice = selectedVoice;
        }

        window.speechSynthesis.speak(utterance);
    }

    if (window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = () => {
            window.speechSynthesis.getVoices();
        };
    }

    // Start WebSocket connection
    connect();
    
    // Initial scroll to bottom to show recent history
    setTimeout(scrollToBottom, 100);

})();
