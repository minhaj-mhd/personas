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

    let ws = null;
    let currentAssistantBubble = null;
    let currentAssistantTextNode = null;

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

        } else if (data.type === "interrupted") {
            // Stream was interrupted
            if (currentAssistantTextNode) {
                currentAssistantTextNode.textContent += " [interrupted]";
            }
            resetUIState();
            scrollToBottom();

        } else if (data.type === "error") {
            console.error("Server error:", data.detail);
            hideActionStatus();
            enableChat();
            
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

    // Form submission handler
    if (chatForm) {
        chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                console.error("Cannot send message. WebSocket is not open.");
                return;
            }

            const text = messageInput.value.trim();
            if (!text) return;

            // Clear input & disable UI
            messageInput.value = "";
            disableChat();
            showActionStatus("thinking");

            // Render user message instantly
            appendUserBubble(text);

            // Send via WebSocket
            ws.send(JSON.stringify({
                type: "user_message",
                text: text
            }));
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
        });
    }

    // Start WebSocket connection
    connect();
    
    // Initial scroll to bottom to show recent history
    setTimeout(scrollToBottom, 100);

})();
