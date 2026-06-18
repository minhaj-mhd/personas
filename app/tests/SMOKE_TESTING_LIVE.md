# Manual Chrome Smoke Notes (Gemini Live)

To perform a manual smoke test for the Live WebSocket and audio components in Chrome:

1. **Hardware Setup**: **USE HEADPHONES.** This is critical to prevent echo, as an open microphone and speakers will continuously trigger Voice Activity Detection (VAD) loops on the Gemini Live side.
2. **Access the Chat**: Open the Chrome browser and navigate to the persona's chat interface (`http://localhost:8000/...`).
3. **Permissions**: Click the "Go Live" button. When Chrome prompts for microphone access, explicitly click **Allow**.
4. **Speak & Listen**: Speak naturally into your microphone. Verify that:
   - Your speech is picked up and a user text transcript is displayed.
   - The Assistant replies with audible playback and a corresponding text transcript.
5. **Interrupt/Barge-in**: While the Assistant is actively speaking, start talking. Verify that the playback stops immediately (gapless flush) and the Assistant begins handling your new input.
6. **Disconnect**: Stop the live session and verify that the session disconnects cleanly, triggering the rolling summarizer background task.

**Additional Notes**:
- Missing playback may occur due to Chrome `AudioContext` autoplay policies. Ensure you initiate the "Live" session strictly via a direct user click.
- Audio capture relies on 16kHz PCM mono sampling. Downsampling is done within the `ScriptProcessor` or `AudioWorklet`. Ensure you check the console for any script/processor errors.
