/*
 * support-widget.js — drop-in chat widget for Clear Impact Scorecard and Compyle.
 *
 * Embed in your app with:
 *   <script src="https://your-cdn/support-widget.js"
 *           data-endpoint="https://your-backend/chat"
 *           data-product="scorecard"          // or "compyle"
 *           data-accent="#2563eb"></script>
 *
 * The widget never sees your Gemini key — it only calls YOUR backend (/chat).
 * Bot answers are rendered as Markdown (bold, bullets, numbered steps); verified
 * article links are shown in a "Learn More" section the backend supplies.
 */
(function () {
  const script = document.currentScript;
  const ENDPOINT = script.getAttribute("data-endpoint") || "/chat";
  const PRODUCT = script.getAttribute("data-product") || "scorecard";
  const ACCENT = script.getAttribute("data-accent") || "#2563eb";
  const TITLE = script.getAttribute("data-title") || "Support Assistant";

  const history = [];

  // ---- styles -------------------------------------------------------------
  const css = `
    .sb-launch{position:fixed;bottom:24px;right:24px;width:56px;height:56px;border-radius:50%;
      background:${ACCENT};color:#fff;border:none;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.2);
      font-size:24px;z-index:2147483000;display:flex;align-items:center;justify-content:center}
    .sb-panel{position:fixed;bottom:92px;right:24px;width:380px;max-width:calc(100vw - 32px);
      height:560px;max-height:calc(100vh - 120px);background:#fff;border-radius:14px;
      box-shadow:0 12px 40px rgba(0,0,0,.22);display:none;flex-direction:column;overflow:hidden;
      z-index:2147483000;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
    .sb-panel.open{display:flex}
    .sb-head{background:${ACCENT};color:#fff;padding:14px 16px;font-weight:600;font-size:15px;
      display:flex;justify-content:space-between;align-items:center}
    .sb-close{background:none;border:none;color:#fff;cursor:pointer;font-size:20px;line-height:1}
    .sb-log{flex:1;overflow-y:auto;padding:16px;background:#f7f8fa}
    .sb-msg{margin-bottom:14px;display:flex}
    .sb-msg.user{justify-content:flex-end}
    .sb-bubble{max-width:84%;padding:10px 13px;border-radius:12px;font-size:14px;line-height:1.5;
      word-wrap:break-word;overflow-wrap:anywhere}
    .sb-msg.bot .sb-bubble{background:#fff;border:1px solid #e6e8eb;color:#1a1a1a}
    .sb-msg.user .sb-bubble{background:${ACCENT};color:#fff;white-space:pre-wrap}
    /* Markdown rendering inside bot bubbles */
    .sb-bubble p{margin:0 0 8px}
    .sb-bubble p:last-child{margin-bottom:0}
    .sb-bubble ul,.sb-bubble ol{margin:4px 0 8px;padding-left:20px}
    .sb-bubble li{margin:2px 0}
    .sb-bubble code{background:#eef0f2;padding:1px 4px;border-radius:4px;font-size:13px}
    .sb-bubble .sb-h{font-weight:700;margin:8px 0 4px}
    .sb-bubble strong{font-weight:700}
    .sb-learn{margin-top:10px;padding-top:8px;border-top:1px solid #eee;font-size:12.5px}
    .sb-learn-title{font-weight:700;margin-bottom:4px}
    .sb-learn a{display:block;color:${ACCENT};text-decoration:none;margin-top:3px}
    .sb-learn a:hover{text-decoration:underline}
    .sb-foot{border-top:1px solid #eee;padding:10px;display:flex;gap:8px;background:#fff}
    .sb-input{flex:1;border:1px solid #d6d9dd;border-radius:8px;padding:9px 11px;font-size:14px;outline:none}
    .sb-input:focus{border-color:${ACCENT}}
    .sb-send{background:${ACCENT};color:#fff;border:none;border-radius:8px;padding:0 16px;cursor:pointer;font-size:14px}
    .sb-send:disabled{opacity:.5;cursor:default}
    .sb-typing{font-size:13px;color:#888;font-style:italic}
  `;
  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // ---- tiny, safe Markdown renderer --------------------------------------
  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
  function inlineMd(escaped) {
    // operates on already-HTML-escaped text
    return escaped
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
               '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }
  function renderMarkdown(md) {
    const lines = (md || "").split(/\r?\n/);
    let html = "", i = 0;
    const bullet = (l) => /^\s*[-*]\s+/.test(l);
    const number = (l) => /^\s*\d+\.\s+/.test(l);
    const heading = (l) => /^\s*#{1,6}\s+/.test(l);
    while (i < lines.length) {
      const line = lines[i];
      if (bullet(line)) {
        html += "<ul>";
        while (i < lines.length && bullet(lines[i])) {
          html += "<li>" + inlineMd(escapeHtml(lines[i].replace(/^\s*[-*]\s+/, ""))) + "</li>";
          i++;
        }
        html += "</ul>";
      } else if (number(line)) {
        html += "<ol>";
        while (i < lines.length && number(lines[i])) {
          html += "<li>" + inlineMd(escapeHtml(lines[i].replace(/^\s*\d+\.\s+/, ""))) + "</li>";
          i++;
        }
        html += "</ol>";
      } else if (heading(line)) {
        html += '<div class="sb-h">' +
          inlineMd(escapeHtml(line.replace(/^\s*#{1,6}\s+/, ""))) + "</div>";
        i++;
      } else if (line.trim() === "") {
        i++;
      } else {
        const para = [];
        while (i < lines.length && lines[i].trim() !== "" &&
               !bullet(lines[i]) && !number(lines[i]) && !heading(lines[i])) {
          para.push(inlineMd(escapeHtml(lines[i])));
          i++;
        }
        html += "<p>" + para.join("<br>") + "</p>";
      }
    }
    return html;
  }

  // ---- DOM ----------------------------------------------------------------
  const launch = document.createElement("button");
  launch.className = "sb-launch";
  launch.innerHTML = "&#128172;";
  launch.setAttribute("aria-label", "Open support assistant");

  const panel = document.createElement("div");
  panel.className = "sb-panel";
  panel.innerHTML = `
    <div class="sb-head">${TITLE}<button class="sb-close" aria-label="Close">&times;</button></div>
    <div class="sb-log"></div>
    <div class="sb-foot">
      <input class="sb-input" type="text" placeholder="Ask a question..." />
      <button class="sb-send">Send</button>
    </div>`;

  // The snippet may be placed in the page <head> (HubSpot KB articles only offer
  // a Head HTML field), which runs before <body> exists — so defer insertion.
  function mountWidget() {
    document.body.appendChild(launch);
    document.body.appendChild(panel);
  }
  if (document.body) {
    mountWidget();
  } else {
    document.addEventListener("DOMContentLoaded", mountWidget);
  }

  const log = panel.querySelector(".sb-log");
  const input = panel.querySelector(".sb-input");
  const send = panel.querySelector(".sb-send");

  function addMessage(role, text, sources) {
    const row = document.createElement("div");
    row.className = "sb-msg " + (role === "user" ? "user" : "bot");
    const bubble = document.createElement("div");
    bubble.className = "sb-bubble";

    if (role === "user") {
      bubble.textContent = text;
    } else {
      bubble.innerHTML = renderMarkdown(text);
      if (sources && sources.length) {
        const learn = document.createElement("div");
        learn.className = "sb-learn";
        learn.innerHTML = '<div class="sb-learn-title">Learn More</div>';
        sources.forEach((s) => {
          const a = document.createElement("a");
          a.href = s.url;
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = s.title;
          learn.appendChild(a);
        });
        bubble.appendChild(learn);
      }
    }
    row.appendChild(bubble);
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function setTyping(on) {
    let t = log.querySelector(".sb-typing-row");
    if (on && !t) {
      t = document.createElement("div");
      t.className = "sb-msg bot sb-typing-row";
      t.innerHTML = `<div class="sb-bubble sb-typing">Looking that up...</div>`;
      log.appendChild(t);
      log.scrollTop = log.scrollHeight;
    } else if (!on && t) {
      t.remove();
    }
  }

  async function ask() {
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    send.disabled = true;
    addMessage("user", message);
    history.push({ role: "user", text: message });
    setTyping(true);

    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, product: PRODUCT, history: history.slice(0, -1) }),
      });
      const data = await res.json();
      setTyping(false);
      addMessage("bot", data.answer, data.sources);
      history.push({ role: "model", text: data.answer });
    } catch (e) {
      setTyping(false);
      addMessage("bot", "Sorry, something went wrong. Please try again.");
    } finally {
      send.disabled = false;
      input.focus();
    }
  }

  launch.addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      if (!log.children.length) {
        var pname = PRODUCT === "compyle" ? "Compyle"
                  : PRODUCT === "suite" ? "Clear Impact"
                  : "Clear Impact Scorecard";
        addMessage("bot", "Hi! Ask me anything about " + pname +
          " and I'll answer from our help documentation.");
      }
      input.focus();
    }
  });
  panel.querySelector(".sb-close").addEventListener("click", () => panel.classList.remove("open"));
  send.addEventListener("click", ask);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
})();
