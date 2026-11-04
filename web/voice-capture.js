// Issue #41: producer voice-note capture. Records raw 16 kHz PCM (AudioWorklet)
// so bytes stream straight into Amazon Transcribe. producer_id comes from the
// server's login session; the client never sends it.

const TARGET_RATE = 16000;
const MAX_SECONDS = 60;
const B64_BLOCK = 24576; // block-wise btoa; 24576 % 3 === 0, so only the final block carries '=' padding

const workletCode = `
registerProcessor('capture-processor', class extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
});
`;

function pcm16From(chunk, sourceRate) {
  // Always emit little-endian PCM16 bytes at any context rate (raw Float32 bytes are floats, not PCM16).
  const ratio = sourceRate / TARGET_RATE;
  const out = new Int16Array(ratio === 1 ? chunk.length : Math.floor(chunk.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const sample = Math.max(-1, Math.min(1, chunk[Math.min(Math.floor(i * ratio), chunk.length - 1)]));
    out[i] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
  }
  return out;
}

function toBase64(bytes) {
  let out = '';
  for (let i = 0; i < bytes.length; i += B64_BLOCK) out += btoa(String.fromCharCode(...bytes.subarray(i, i + B64_BLOCK)));
  return out;
}

export class VoiceNoteRecorder {
  constructor(objectURL) {
    this.endpoint = objectURL;  // POST target for the 16 kHz PCM
    this.conversationId = null; // set by the chat; server scopes the store path
    this._result = null;        // first stop() wins; later calls return it
    this.chunks = null;
  }

  async _start() {
    let workletURL;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({audio: true});
      this.ctx = new AudioContext();
      this.sourceRate = this.ctx.sampleRate;
      workletURL = URL.createObjectURL(new Blob([workletCode], {type: 'application/javascript'}));
      await this.ctx.audioWorklet.addModule(workletURL);
      this.node = new AudioWorkletNode(this.ctx, 'capture-processor');
      this.chunks = [];
      this.node.port.onmessage = (e) => this.chunks?.push(e.data);
      this.source = this.ctx.createMediaStreamSource(this.stream);
      this.source.connect(this.node);
      this._timer = setTimeout(() => { this.stop().catch(() => {}); }, MAX_SECONDS * 1000); // hard cap
    } catch (error) {
      this.chunks = null;
      await this._cleanup();
      throw error;
    } finally {
      if (workletURL) URL.revokeObjectURL(workletURL);
    }
  }

  async _cleanup() {
    clearTimeout(this._timer);
    this._timer = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.source?.disconnect();
    this.source = null;
    if (this.node) {
      this.node.port.onmessage = null;
      this.node.disconnect();
      this.node = null;
    }
    const ctx = this.ctx;
    this.ctx = null;
    if (ctx) {
      try {
        await ctx.close();
      } catch {
        // Tracks are already stopped; a close failure must not mask the start error.
      }
    }
  }

  /** Idempotently ends capture; resolves once, with the VoiceTurn echoed by the backend. */
  async stop() {
    if (this._result) return this._result;   // auto-stop and manual stop share one POST
    if (!this.chunks) throw new Error('voice capture was never started');
    const captured = this.chunks;
    this.chunks = null;
    return (this._result = this._cleanup().then(() => this._post(captured)));
  }

  async _post(captured) {
    const merged = new Float32Array(captured.reduce((n, c) => n + c.length, 0));
    let offset = 0;
    for (const c of captured) { merged.set(c, offset); offset += c.length; }
    const pcm = pcm16From(merged, this.sourceRate);
    const body = {conversation_id: this.conversationId, media_encoding: 'pcm', sample_rate: TARGET_RATE};
    const res = await fetch(this.endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...body, pcm_b64: toBase64(new Uint8Array(pcm.buffer))})});
    if (!res.ok) throw new Error(`voice ingest failed: ${res.status}`);
    return res.json(); // the VoiceTurn: {transcript, language_code, confidence, audio_key}
  }
}
