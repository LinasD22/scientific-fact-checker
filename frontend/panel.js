(function () {
  const existing = document.getElementById("factCheckerContainer");
  if (existing) existing.remove();
  injectPanel();
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

function injectPanel() {
  const container = document.createElement("div");
  container.id = "factCheckerContainer";

  const iframe = document.createElement("iframe");
  iframe.id = "factCheckerIframe";
  iframe.src = chrome.runtime.getURL("popup.html");
  // Set a transparent background for the iframe to prevent white flashes
  iframe.style.background = "transparent";

  container.appendChild(iframe);
  document.body.appendChild(container);

  const style = document.createElement("style");

  style.textContent = `
    #factCheckerContainer {
      position: fixed;
      top: 20px;
      right: 20px;
      width: 360px;
      max-height: 600px;
      height: 200px; 
      z-index: 2147483647;
      background: white;
      border-radius: 16px;
      overflow: hidden; 
      box-shadow: 0 10px 25px rgba(0,0,0,0.2);
      border: 1px solid #e2e8f0;
      transition: height 0.3s ease-in-out; 
    }
    #factCheckerIframe {
      width: 100%;
      height: 100%;
      border: none;
      display: block;
    }
	::highlight(fact-verified) {
	background-color: rgba(72, 187, 120, 0.4);
	}

	::highlight(fact-false) {
	background-color: rgba(245, 101, 101, 0.4);
	}
	
	::highlight(fact-neutral) {
	background-color: rgba(255, 255, 0, 0.35);
	}
	`;
  document.head.appendChild(style);

  window.addEventListener("message", (event) => {
    if (event.data?.type === "CLOSE_PANEL") {
      container.remove();
    }
    if (event.data?.type === "RESIZE_PANEL") {
      // Add a 10px buffer to prevent accidental scrollbars
      container.style.height = (event.data.height + 10) + "px";
    }
  });
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