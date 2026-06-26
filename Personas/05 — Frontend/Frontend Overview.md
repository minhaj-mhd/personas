---
title: "Frontend Overview"
type: reference
status: active
updated: 2026-06-25
---

# 🖥️ Frontend Overview (Server-Rendered + HTMX)

The platform's frontend is designed to be lightweight, responsive, and easy to maintain. It uses **FastAPI + Jinja2** templates for server-side HTML rendering, and **HTMX** for dynamic UI interactions. This setup removes the need for complex Node.js build steps, Webpack compilation, or heavyweight JavaScript frameworks.

---

## 🎨 Page Views and Layouts

All views are mapped inside [views.py](file:///c:/Users/loq/Desktop/learn/personas/app/web/views.py) and serve files from the `app/templates` folder:

### 1. Root Dashboard ([index.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/index.html))
- Mapped to `GET /`.
- Shows a grid of all available personas (built-in and custom).
- Includes an HTMX-driven dynamic system health check badge.

### 2. Persona Sessions View ([conversations.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/conversations.html))
- Mapped to `GET /personas/{id}`.
- Lists all past conversation sessions for a specific persona.
- **Knowledge Base Panel**: Drag-and-drop file upload form and raw text paste inputs. These target `/api/personas/{id}/documents` and reload the page on completion to show updated documents.

### 3. Chat Session Layout ([chat.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/chat.html))
- Mapped to `GET /chat/{id}`. Pre-renders messages; initializes [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js) (text chat).
- **Voice V1** (`#mic-btn`, push-to-talk, Web Speech STT + `SpeechSynthesis`).
- **"Go Live"** (`#live-btn`) → [live.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/live.js) `LiveAudioClient` → `/ws/live/{id}` (single-agent Gemini Live full-duplex).

### 4. Custom Persona Prompt Form ([persona_form.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/persona_form.html))
- Mapped to `GET /personas/new` or `GET /personas/{id}/edit`.
- Allows creating/updating custom personas (defining speaking style, personality traits, and goals).

### 5. Voice Panel — Voice L2 ([panel.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/panel.html))
- Mapped to `GET /panel`. Roster picker → live panel (active-speaker chip + transcript).
- [panel.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/panel.js) `PanelAudioClient extends LiveAudioClient`
  (reuses the mic/audio engine; adds `select_roster` handshake + `active_speaker`/`transcript`/`handoff` handling) → `/ws/panel/{id}`.
- See [[05 — Frontend/Live Voice Session]] and [[01 — Architecture/Master Plan — Voice Panel (Host-Led, Subagent-Ready)]].

---

## 🔁 HTMX Dynamic Partial Refreshes

We use **HTMX** to update parts of the page without requiring full browser reloads:
- **Health Badge**: The dashboard runs a deferred check:
  ```html
  <div hx-get="/web/health-badge" hx-trigger="load" hx-swap="outerHTML">
      <!-- Loading Spinner -->
  </div>
  ```
- **Persona Deletion**: Custom personas can be deleted instantly from the dashboard. HTMX sends a `DELETE /api/personas/{id}` request and removes the target persona card from the DOM upon receiving a successful `204 No Content` response.

---

## 🔌 WebSocket Client State Machine (`ws.js`)

Real-time chat interactions are managed by the script [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js), which runs a state machine to control the UI:

```
          ┌──────────────────────────────────────────────┐
          │                    IDLE                      │
          └─────────────┬──────────────────▲─────────────┘
                        │                  │
               User submits message        Message complete / Error
                        │                  │
                        ▼                  │
          ┌──────────────────────────────┐ │
          │                  THINKING    │ │
          └─────────────┬────────────────┘ │
                        │                  │
               First token arrives         │
                        │                  │
                        ▼                  │
          ┌────────────────────────────────┘
          │                 STREAMING      │
          └────────────────────────────────┘
```

### 1. State Details:
- **Idle**: The connection is open. The user can type, and the inputs are enabled.
- **Thinking**: The user has clicked **Send** (or spoken). The input fields are disabled, and a loader indicator shows "Thinking" while waiting for the backend to process embeddings, run vector searches, and fetch the first token from Gemini.
- **Streaming**: The first token has arrived. An assistant bubble is created in the DOM, and tokens are appended to it. The **Interrupt** button is shown.

### 2. Event Payload Parsing:
The client handles JSON events from the server:
- `token`: Appends `data.delta` to the current assistant chat bubble.
- `message_complete`: The assistant has finished speaking. The client saves the message ID, focuses the input field, and resets the state to **Idle**.
- `interrupted`: The generation was stopped. The client appends `[interrupted]` to the text bubble and resets the state to **Idle**.
- `error`: Shows a red warning bubble at the bottom of the chat list with the error details.
