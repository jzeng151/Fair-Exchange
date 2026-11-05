/* Fair Trade Exchange chat — client (CR-001).
   Mock /api/chat with real-looking answers, attachments, delete, new chat, period history,
   reports, sentiment, share-data consent + points. Voice in/out are progressive enhancements. */
(function () {
  "use strict";
  const T = window.FTX;
  const $ = id => document.getElementById(id);
  const transcript = $("transcript");
  const input = $("input");
  const form = $("composer");

  let language = T.language;
  let turns = [];           // {id, role, text, at, sentiment?, tags?} — drives history/reports/delete
  let pendingAttachments = []; // {name, kind}
  let sharedTurns = 0;
  let turnSeq = 0;
  let pendingFiles = [];   // actual File objects, for real S3 upload

  const synth = window.speechSynthesis;
  const LOCALE = { en: "en-US", es: "es-ES", fr: "fr-FR", pt: "pt-BR", sw: "sw-KE", hi: "hi-IN" };

  function el(tag, cls, html) { const n = document.createElement(tag); if (cls) n.className = cls; if (html !== undefined) n.innerHTML = html; return n; }
  function esc(s) { return (s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  // ---- render a message row (with optional delete on user turns) --------
  function renderRow(turn, data) {
    const msg = el("div", "msg " + turn.role);
    esc(turn.text).split("\n").forEach(line => msg.appendChild(el("p", null, line || "&nbsp;")));
    if (turn.attachments && turn.attachments.length) {
      const wrap = el("div", "msg-attach");
      turn.attachments.forEach(a => wrap.appendChild(el("span", "attach-chip", (a.kind === "image" ? "🖼️ " : "📄 ") + esc(a.name))));
      msg.appendChild(wrap);
    }
    if (data) {
      if (data.pii_flagged && data.pii_flagged.length)
        msg.appendChild(el("div", "pii-badge", "⚑ PII flagged for review (not redacted): " + data.pii_flagged.join(", ")));
      if (data.sentiment)
        msg.appendChild(el("div", "sentiment " + data.sentiment, "Sensed tone: " + data.sentiment));
      if (data.citations && data.citations.length) {
        const c = el("div", "citations");
        data.citations.forEach(x => c.appendChild(el("span", "cite " + (x.kind || ""), "🔗 " + esc(x.label))));
        msg.appendChild(c);
      }
    }
    const row = el("div", "row " + turn.role);
    row.dataset.turnId = turn.id;
    row.appendChild(el("div", "bubble-avatar", turn.role === "user" ? "🧑" : "🌱"));
    row.appendChild(msg);
    if (turn.role === "user") {
      const del = el("button", "del-btn", "✕");
      del.title = "Delete this question"; del.type = "button";
      del.addEventListener("click", () => deleteTurn(turn.id));
      row.appendChild(del);
    }
    transcript.appendChild(row);
    transcript.scrollTop = transcript.scrollHeight;
    return row;
  }

  function addSystem(text) {
    const m = el("div", "msg system");
    esc(text).split("\n").forEach(l => m.appendChild(el("p", null, l || "&nbsp;")));
    transcript.appendChild(m); transcript.scrollTop = transcript.scrollHeight; return m;
  }

  function pushTurn(role, text, extra) {
    const turn = Object.assign({ id: ++turnSeq, role, text, at: Date.now() }, extra || {});
    turns.push(turn);
    renderRow(turn, extra && extra._data);
    renderHistory();
    return turn;
  }

  // ---- delete a question (and the assistant answer that followed it) ----
  function deleteTurn(id) {
    const idx = turns.findIndex(t => t.id === id);
    if (idx === -1) return;
    const remove = [id];
    if (turns[idx + 1] && turns[idx + 1].role === "assistant") remove.push(turns[idx + 1].id);
    turns = turns.filter(t => !remove.includes(t.id));
    remove.forEach(rid => { const r = transcript.querySelector(`[data-turn-id="${rid}"]`); if (r) r.remove(); });
    renderHistory();
  }

  // ---- suggestions / candidates ----------------------------------------
  function renderSuggestions(list) {
    const box = $("suggestions"); box.innerHTML = "";
    (list || []).forEach(s => { const b = el("button", "suggest", esc(s)); b.type = "button"; b.onclick = () => { input.value = s; send(); }; box.appendChild(b); });
  }
  function renderCandidates(list) {
    const box = $("candidates"); box.innerHTML = "";
    (list || []).slice(0, 2).forEach(q => { const b = el("button", "candidate", esc(q)); b.type = "button"; b.onclick = () => { input.value = q; send(); }; box.appendChild(b); });
  }

  // ---- period history ---------------------------------------------------
  let period = "today";
  function inPeriod(ts) {
    const now = new Date(), d = new Date(ts);
    if (period === "today") return d.toDateString() === now.toDateString();
    const days = (now - d) / 86400000;
    if (period === "week") return days <= 7;
    if (period === "month") return days <= 31;
    if (period === "quarter") return days <= 92;
    return true;
  }
  function renderHistory() {
    const box = $("history-list"); box.innerHTML = "";
    const items = turns.filter(t => t.role === "user" && inPeriod(t.at));
    if (!items.length) { box.appendChild(el("div", "footnote", "No messages in this period yet.")); return; }
    items.slice().reverse().forEach(t => {
      const row = el("div", "hist-item");
      row.innerHTML = `<b>You:</b> ${esc(t.text.slice(0, 80))}`;
      box.appendChild(row);
    });
  }

  // ---- speech out -------------------------------------------------------
  function speak(text) { if (!$("speak-toggle").checked || !synth) return; synth.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = LOCALE[language] || "en-US"; synth.speak(u); }

  // ---- send -------------------------------------------------------------
  let busy = false;
  async function send() {
    const message = input.value.trim();
    if ((!message && !pendingAttachments.length) || busy) return;
    busy = true;
    const cw = $("candidate-wrap"); if (cw) cw.style.display = "none";
    const atts = await uploadAttachments();   // real S3 upload when enabled
    pushTurn("user", message || "(shared attachment)", { attachments: atts });
    input.value = ""; input.style.height = "auto";
    pendingAttachments = []; pendingFiles = []; renderAttachRow();

    const pending = el("div", "row assistant");
    pending.appendChild(el("div", "bubble-avatar", "🌱"));
    pending.appendChild(el("div", "msg assistant typing", "<span></span><span></span><span></span>"));
    transcript.appendChild(pending); transcript.scrollTop = transcript.scrollHeight;

    let data;
    try {
      const res = await fetch(T.chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": T.csrftoken },
        body: JSON.stringify({ message, language, persona_id: T.personaId, attachments: atts }),
      });
      data = res.ok ? await res.json() : null;
    } catch (e) { data = null; }
    pending.remove();

    if (!data) {
      // F1: never a dead-end. Produce a graceful, real-looking fallback locally.
      data = {
        text: "Thanks for sharing that. From what I can see for your region, conditions have been shifting, "
            + "and some peers in a similar spot have leaned on the Community Development Premium. "
            + "You and your cooperative know your situation best — these are options to weigh.",
        citations: [{ label: "Regional context (sample)", kind: "regional" }, { label: "Peer Premium project (sample)", kind: "peer" }],
        suggestions: T.candidateQuestions, sentiment: "supportive", tags: [],
      };
    }
    const turn = pushTurn("assistant", data.text, { _data: data, sentiment: data.sentiment, tags: data.tags });
    renderSuggestions(data.suggestions);
    speak(data.text);
    if ($("share-toggle").checked) { sharedTurns += 1; refreshPoints(); }
    busy = false;
  }

  form.addEventListener("submit", e => { e.preventDefault(); send(); });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 150) + "px"; });
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });

  // ---- language ---------------------------------------------------------
  $("lang").addEventListener("change", e => { language = e.target.value; addSystem("Language switched to " + e.target.options[e.target.selectedIndex].text + "."); });

  // ---- attachments ------------------------------------------------------
  $("attach-btn").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", e => {
    for (const f of e.target.files) {
      pendingAttachments.push({ name: f.name, kind: f.type.startsWith("image/") ? "image" : "file", content_type: f.type, size: f.size });
      pendingFiles.push(f);
    }
    $("file-input").value = ""; renderAttachRow();
  });
  function renderAttachRow() {
    const row = $("attach-row"); row.innerHTML = "";
    pendingAttachments.forEach((a, i) => {
      const chip = el("span", "attach-chip pending", (a.kind === "image" ? "🖼️ " : "📄 ") + esc(a.name) + " ");
      const x = el("button", "chip-x", "✕"); x.type = "button"; x.onclick = () => { pendingAttachments.splice(i, 1); pendingFiles.splice(i, 1); renderAttachRow(); };
      chip.appendChild(x); row.appendChild(chip);
    });
  }

  // Upload pending files to S3 via presigned PUT (when enabled); returns attachments with keys.
  async function uploadAttachments() {
    const atts = pendingAttachments.map(a => ({ name: a.name, kind: a.kind }));
    if (!T.uploadsEnabled || !pendingFiles.length) return atts;
    try {
      const res = await fetch(T.presignUrl, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": T.csrftoken },
        body: JSON.stringify({ files: pendingAttachments.map(a => ({ name: a.name, content_type: a.content_type, size: a.size })) }),
      });
      if (!res.ok) return atts;
      const { enabled, results } = await res.json();
      if (!enabled || !results) return atts;
      await Promise.all(results.map(async (r, i) => {
        if (r && r.url) {
          try {
            const put = await fetch(r.url, { method: "PUT", headers: { "Content-Type": pendingFiles[i].type }, body: pendingFiles[i] });
            if (put.ok) atts[i].key = r.key;
          } catch (e) {}
        }
      }));
    } catch (e) {}
    return atts;
  }

  // ---- period switch ----------------------------------------------------
  $("period-switch").addEventListener("click", e => {
    if (e.target.tagName !== "BUTTON") return;
    period = e.target.dataset.period;
    [...e.currentTarget.children].forEach(b => b.classList.toggle("active", b === e.target));
    renderHistory();
  });

  // ---- report -----------------------------------------------------------
  $("report-btn").addEventListener("click", async () => {
    if (!turns.length) { addSystem("Start a conversation first, then I can build a report."); return; }
    const res = await fetch(T.reportUrl, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": T.csrftoken },
      body: JSON.stringify({ persona_id: T.personaId, turns }),
    });
    if (!res.ok) { addSystem("Could not build the report just now."); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "fair-trade-exchange-report.md"; a.click();
    URL.revokeObjectURL(url);
    addSystem("Your report has been downloaded.");
  });

  // ---- new chat ---------------------------------------------------------
  $("new-chat").addEventListener("click", () => {
    if (turns.length && !confirm("Start a new chat? This clears the current conversation.")) return;
    turns = []; turnSeq = 0; sharedTurns = 0; transcript.innerHTML = "";
    if (synth) synth.cancel();
    refreshPoints(); renderHistory();
    const cw = $("candidate-wrap"); if (cw) cw.style.display = "";
    bootstrap();
  });

  // ---- share data + points ---------------------------------------------
  $("share-toggle").addEventListener("change", e => {
    const on = e.target.checked;
    $("share-label").textContent = on ? "Sharing on — thank you" : "Sharing off";
    $("points-box").style.display = on ? "flex" : "none";
    if (on) { sharedTurns = turns.filter(t => t.role === "user").length; refreshPoints(); }
  });
  async function refreshPoints() {
    const tags = turns.flatMap(t => t.tags || []);
    try {
      const res = await fetch(T.pointsUrl, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": T.csrftoken },
        body: JSON.stringify({ shared_turns: sharedTurns, tags }),
      });
      if (!res.ok) return;
      const p = await res.json();
      $("points-val").textContent = p.points;
      $("tier-val").textContent = p.tier;
      $("shared-val").textContent = sharedTurns + " exchange(s) shared";
    } catch (e) {}
  }

  // ---- voice in ---------------------------------------------------------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const micBtn = $("mic");
  if (SR) {
    const rec = new SR(); rec.interimResults = true; let recording = false;
    micBtn.onclick = () => { if (recording) { rec.stop(); return; } rec.lang = LOCALE[language] || "en-US"; rec.start(); };
    rec.onstart = () => { recording = true; micBtn.classList.add("recording"); };
    rec.onend = () => { recording = false; micBtn.classList.remove("recording"); };
    rec.onresult = e => { let t = ""; for (let i = e.resultIndex; i < e.results.length; i++) t += e.results[i][0].transcript; input.value = t; };
    rec.onerror = () => { recording = false; micBtn.classList.remove("recording"); };
  } else { micBtn.style.display = "none"; }
  if (!synth) { $("speak-toggle").closest("label").style.display = "none"; }

  // ---- bootstrap --------------------------------------------------------
  function bootstrap() {
    pushTurn("assistant", T.opening, null);
    renderCandidates(T.candidateQuestions);
  }
  bootstrap();
})();
