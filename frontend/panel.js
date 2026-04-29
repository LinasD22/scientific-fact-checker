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
  const normalizedClaim = claimText.replace(/\s+/g, ' ').trim();
  
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

	const matchIndex = fullText.replace(/\s+/g, ' ').toLowerCase().indexOf(normalizedClaim.toLowerCase());

	console.log("Full selection text:", fullText.replace(/\s+/g, ' '));
	console.log("Looking for claim:", normalizedClaim);
	console.log("Match Index found:", matchIndex);

  if (matchIndex !== -1) {
    const matchRange = document.createRange();
    let startSet = false;

    for (const item of nodes) {
      const nodeLength = item.text.length;
      if (!startSet && matchIndex < item.start + nodeLength) {
        matchRange.setStart(item.node, Math.max(0, matchIndex - item.start));
        startSet = true;
      }
      if (startSet && (matchIndex + normalizedClaim.length) <= item.start + nodeLength) {
        matchRange.setEnd(item.node, (matchIndex + normalizedClaim.length) - item.start);
        
        // Apply to the correct Highlight group based on verdict
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