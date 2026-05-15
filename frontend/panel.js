(function () {
  // Clean up any previous injection
  document.getElementById("factCheckerContainer")?.remove();
  document.getElementById("factCheckerResizeHandle")?.remove();
  document.getElementById("factCheckerStyles")?.remove();
  document.getElementById("factCheckerPagePush")?.remove();

  chrome.storage.local.get(["panelMode", "panelWidth"], (data) => {
    injectPanel(data.panelMode || "float", data.panelWidth || 360);
  });
})();

// Keep track of highlights so we can clear them if needed
if (!window.factHighlights) {
  window.factHighlights = {
    verified: new Highlight(),
    false: new Highlight(),
    neutral: new Highlight()
  };
  CSS.highlights.set("fact-verified", window.factHighlights.verified);
  CSS.highlights.set("fact-false", window.factHighlights.false);
  CSS.highlights.set("fact-neutral", window.factHighlights.neutral);
}

function injectPanel(initialMode, initialWidth) {
  let currentMode  = initialMode;
  let currentWidth = clampWidth(initialWidth);

  // ── 1. Panel container ────────────────────────────────────────────────────
  const container = document.createElement("div");
  container.id = "factCheckerContainer";

  const iframe = document.createElement("iframe");
  iframe.id  = "factCheckerIframe";
  iframe.src = chrome.runtime.getURL("popup.html");

  // Mode-toggle tab (always inside the container, floated on its left edge)
  const modeTab = document.createElement("button");
  modeTab.id = "factCheckerModeTab";

  container.appendChild(iframe);
  container.appendChild(modeTab);
  document.body.appendChild(container);

  // Notify iframe of current mode as soon as it finishes loading
  iframe.addEventListener("load", () => {
    try {
      iframe.contentWindow.postMessage({ type: "MODE_CHANGED", mode: currentMode }, "*");
    } catch (e) {}
  });

  // ── 2. Resize handle — completely independent fixed element ───────────────
  //    Lives directly on <body>, never clipped by the container.
  const handle = document.createElement("div");
  handle.id = "factCheckerResizeHandle";
  handle.innerHTML = `<span class="fc-grip-dots"></span>`;
  document.body.appendChild(handle);

  // ── 3. Host-page style sheet (panel chrome + page-push margin) ────────────
  const panelStyle = document.createElement("style");
  panelStyle.id = "factCheckerStyles";
  document.head.appendChild(panelStyle);

  // Separate sheet just for the html margin so we can update it cheaply
  const pushStyle = document.createElement("style");
  pushStyle.id = "factCheckerPagePush";
  document.head.appendChild(pushStyle);

  const highlightStyle = document.createElement("style");
  highlightStyle.id = "factCheckerHighlightStyles";
  highlightStyle.textContent = `
    ::highlight(fact-verified) { background-color: rgba(72, 187, 120, 0.4); }
    ::highlight(fact-false)    { background-color: rgba(245, 101, 101, 0.4); }
    ::highlight(fact-neutral)  { background-color: rgba(255, 255,   0, 0.35); }
  `;
  document.head.appendChild(highlightStyle);

  // ── Helpers ───────────────────────────────────────────────────────────────
  function clampWidth(w) { return Math.max(280, Math.min(1400, w)); }

  function setPagePush(px) {
    // Push the entire page left so the panel never covers content.
    // Using !important to win over any page-level margin/padding.
    pushStyle.textContent = `
      html {
        margin-right: ${px}px !important;
        box-sizing: border-box !important;
        overflow-x: hidden !important;
      }
    `;
  }

  function clearPagePush() {
    pushStyle.textContent = "";
  }

  // ── Apply / re-render a mode ──────────────────────────────────────────────
  function applyMode(mode, skipSave) {
    currentMode = mode;
    if (!skipSave) chrome.storage.local.set({ panelMode: mode });
    renderStyles();
    // Notify the iframe so its internal viewModeBtn can update its icon
    try {
      iframe.contentWindow.postMessage({ type: "MODE_CHANGED", mode: currentMode }, "*");
    } catch (e) {}
  }

  function renderStyles() {
    if (currentMode === "side") {
      // ── SIDE-PANEL MODE ───────────────────────────────────────────────────
      setPagePush(currentWidth);

      panelStyle.textContent = `
        /* ── Panel container ── */
        #factCheckerContainer {
          position: fixed !important;
          top: 0 !important;
          right: 0 !important;
          width: ${currentWidth}px !important;
          height: 100vh !important;
          z-index: 2147483646;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          background: #ffffff;
          border-left: 1px solid #334155;
          box-shadow: -4px 0 20px rgba(0,0,0,0.18);
        }

        /* ── Iframe fills the panel ── */
        #factCheckerIframe {
          flex: 1 1 auto;
          width: 100%;
          height: 0;
          border: none;
          display: block;
        }

        /* ── Mode-toggle tab sticking out of the left edge ── */
        #factCheckerModeTab {
          position: absolute;
          top: 50%;
          left: -22px;
          transform: translateY(-50%);
          width: 22px;
          height: 56px;
          padding: 0;
          background: #3b82f6;
          border: none;
          border-radius: 8px 0 0 8px;
          cursor: pointer;
          color: #fff;
          font-size: 11px;
          line-height: 1;
          box-shadow: -3px 0 10px rgba(59,130,246,0.4);
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.15s;
        }
        #factCheckerModeTab:hover { background: #2563eb; }

        /* ── Resize handle (fixed, independent) ── */
        #factCheckerResizeHandle {
          position: fixed !important;
          top: 0 !important;
          right: ${currentWidth - 5}px !important;
          width: 10px !important;
          height: 100vh !important;
          z-index: 2147483647;
          cursor: ew-resize !important;
          display: flex !important;
          align-items: center;
          justify-content: center;
          background: transparent;
        }
        #factCheckerResizeHandle:hover .fc-grip-dots,
        #factCheckerResizeHandle.fc-dragging .fc-grip-dots {
          opacity: 1;
          background: #3b82f6;
        }
        .fc-grip-dots {
          pointer-events: none;
          display: block;
          width: 4px;
          height: 36px;
          border-radius: 4px;
          background: #94a3b8;
          opacity: 0.5;
          transition: opacity 0.15s, background 0.15s;
        }
      `;

      modeTab.textContent = "⇔";
      modeTab.title = "Switch to floating panel";
      handle.style.display = "flex";

    } else {
      // ── FLOAT MODE ────────────────────────────────────────────────────────
      clearPagePush();

      // Clear any inline width that may have been set during panel resize
      container.style.removeProperty("width");

      panelStyle.textContent = `
        #factCheckerContainer {
          position: fixed;
          top: 20px;
          right: 20px;
          width: 360px !important;
          min-height: 180px;
          max-height: 90vh;
          z-index: 2147483647;
          background: white;
          border-radius: 16px;
          overflow: hidden;
          box-shadow: 0 10px 25px rgba(0,0,0,0.2);
          border: 1px solid #e2e8f0;
          transition: height 0.2s ease-in-out;
          display: flex;
          flex-direction: column;
        }
        #factCheckerIframe {
          width: 100%;
          flex: 1 1 auto;
          min-height: 180px;
          height: 100%;
          border: none;
          display: block;
          overflow-y: auto;
        }
        #factCheckerModeTab { display: none !important; }
        #factCheckerResizeHandle { display: none !important; }
      `;

      modeTab.textContent = "⇔";
      modeTab.title = "Expand to side panel";
      handle.style.display = "none";
    }
  }

  // ── Mode toggle click ─────────────────────────────────────────────────────
  modeTab.addEventListener("click", () => {
    applyMode(currentMode === "side" ? "float" : "side");
  });

  // ── Resize drag ───────────────────────────────────────────────────────────
  handle.addEventListener("mousedown", startResize);

  function startResize(e) {
    if (currentMode !== "side") return;
    e.preventDefault();
    e.stopPropagation();

    handle.classList.add("fc-dragging");

    // Disable pointer-events on everything except our handle so the drag
    // doesn't get "stolen" by links, iframes, or other fixed elements.
    document.body.style.setProperty("user-select",    "none",       "important");
    document.body.style.setProperty("pointer-events", "none",       "important");
    document.body.style.setProperty("cursor",         "ew-resize",  "important");
    handle.style.setProperty("pointer-events", "auto", "important");
    iframe.style.setProperty("pointer-events", "none", "important");

    function onMouseMove(e) {
      currentWidth = clampWidth(window.innerWidth - e.clientX);

      // 1. Move the panel
      container.style.setProperty("width", currentWidth + "px", "important");

      // 2. Push the page (instant — no CSS transition during drag)
      pushStyle.textContent = `
        html {
          margin-right: ${currentWidth}px !important;
          box-sizing: border-box !important;
          overflow-x: hidden !important;
        }
      `;

      // 3. Move the handle to sit on the new left edge
      handle.style.setProperty("right", (currentWidth - 5) + "px", "important");
    }

    function onMouseUp() {
      handle.classList.remove("fc-dragging");
      document.body.style.removeProperty("user-select");
      document.body.style.removeProperty("pointer-events");
      document.body.style.removeProperty("cursor");
      handle.style.removeProperty("pointer-events");
      iframe.style.removeProperty("pointer-events");

      // Persist and re-render cleanly so all CSS is consistent
      chrome.storage.local.set({ panelWidth: currentWidth });
      renderStyles();

      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup",   onMouseUp);
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup",   onMouseUp);
  }

  // ── Messages from popup iframe ────────────────────────────────────────────
  window.addEventListener("message", (event) => {
    if (!event.data) return;

    if (event.data.type === "SWITCH_TO_FLOAT" || event.data.type === "TOGGLE_PANEL_MODE") {
      applyMode(currentMode === "side" ? "float" : "side");
      return;
    }

    if (event.data.type === "CLOSE_PANEL") {
      clearPagePush();
      container.remove();
      handle.remove();
      panelStyle.remove();
      pushStyle.remove();
      highlightStyle.remove();
    }

    // Only auto-resize height in float mode
    if (event.data.type === "RESIZE_PANEL" && currentMode === "float") {
      const maxH = Math.floor(window.innerHeight * 0.9);
      const h = Math.min(event.data.height + 10, maxH);
      container.style.height = h + "px";
    }
  });

  // ── Initial render ────────────────────────────────────────────────────────
  applyMode(currentMode, true);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "HIGHLIGHT_TEXT") {
    const facts = message.results.individual_facts;

    // Check if we have multiple facts (greater than 1)
    if (facts && facts.length > 1) {
      facts.forEach(fact => {
        // Prioritize the exact_quote for DOM matching
        const textToHighlight = fact.exact_quote ? fact.exact_quote : fact.claim;
        highlightString(textToHighlight, fact.verdict);
      });
    } else {
      // If it's just one claim, highlight the exact original message string
      highlightString(message.claim, message.results.verdict);
    }
  }
});



function highlightString(claimText, verdict) {
  const selection = window.getSelection();
  if (!selection.rangeCount) return;

  const mainRange = selection.getRangeAt(0);
  const container = mainRange.commonAncestorContainer;

  // 1. Gather all text nodes within the selection
  const walker = document.createTreeWalker(
    container.nodeType === Node.TEXT_NODE ? container.parentNode : container,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode: (node) => selection.containsNode(node, true) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
    }
  );

  let fullText = "";
  let nodes = [];
  let node;
  while (node = walker.nextNode()) {
    nodes.push({ node: node, start: fullText.length, text: node.textContent });
    fullText += node.textContent;
  }

  // --- NEW ADDITION: FUZZY MATCHING LOGIC ---

  // Normalize both strings: remove all non-alphanumeric characters and collapse spaces
  const fuzzyClean = (str) => str.toLowerCase().replace(/[^a-z0-9]/g, '').trim();

  const cleanFullText = fuzzyClean(fullText);
  const cleanClaim = fuzzyClean(claimText);

  const cleanMatchIndex = cleanFullText.indexOf(cleanClaim);

  console.log("Fuzzy Search Result:", cleanMatchIndex !== -1 ? "FOUND" : "NOT FOUND");

  if (cleanMatchIndex !== -1) {
    // 2. Map the "clean" index back to the "real" index in the original text
    let realStartIndex = -1;
    let realEndIndex = -1;
    let cleanCounter = 0;

    // Iterate through original text to find where the clean version starts and ends
    for (let i = 0; i < fullText.length; i++) {
      const char = fullText[i].toLowerCase();
      if (/[a-z0-9]/.test(char)) {
        if (cleanCounter === cleanMatchIndex) realStartIndex = i;
        cleanCounter++;
        if (cleanCounter === cleanMatchIndex + cleanClaim.length) {
          realEndIndex = i + 1;
          break;
        }
      }
    }

    if (realStartIndex !== -1 && realEndIndex !== -1) {
      const matchRange = document.createRange();
      let startSet = false;

      // 3. Map the real character indices back to the actual DOM Nodes
      for (const item of nodes) {
        const nodeLength = item.text.length;
        const nodeEnd = item.start + nodeLength;

        // Check if the start of our match falls within this text node
        if (!startSet && realStartIndex < nodeEnd) {
          matchRange.setStart(item.node, realStartIndex - item.start);
          startSet = true;
        }

        // Check if the end of our match falls within this text node
        if (startSet && realEndIndex <= nodeEnd) {
          matchRange.setEnd(item.node, realEndIndex - item.start);

          // 4. Apply to the correct Highlight group based on verdict
          const v = verdict.toLowerCase();
          if (v.includes("verified") || v.includes("true")) {
            window.factHighlights.verified.add(matchRange);
          } else if (v.includes("false") || v.includes("refuted")) {
            window.factHighlights.false.add(matchRange);
          } else {
            window.factHighlights.neutral.add(matchRange);
          }
          break;
        }
      }
    }
  }
}