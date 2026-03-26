if (chrome.contextMenus) {
  chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
      id: "factCheckSelection",
      title: "Fact Check Selection",
      contexts: ["selection"]
    });
  });

  chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === "factCheckSelection") {
      const selectedText = info.selectionText || "";

      chrome.storage.local.set({ lastClaim: selectedText }, () => {
        // SAFE INJECTION: Check if URL is a valid web page
        if (tab.url.startsWith("http")) {
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["panel.js"]
          }).catch(err => console.error("Injection failed:", err));
        } else {
          console.warn("Cannot inject scripts into internal chrome:// pages.");
        }
      });
    }
  });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "FACT_CHECK") {
    checkFact(request.claim)
      .then(result => sendResponse(result))
      .catch(err => {
        console.error(err);
        sendResponse({ verdict: "Error", explanation: "Fact check failed." });
      });
    return true; 
  }
});

async function checkFact(claim) {
  const API_URL = "https://api.healthfactchecker.site/api/fact-check/search";
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim: claim })
  });

  const data = await response.json();

  // We return the full object or ensure key fields are mapped
  return {
    verdict: data.final_verdict ?? "unverifiable",
    explanation: data.summary ?? "",
    score: typeof data.agreement_score === "number" ? data.agreement_score : 0,
    consensus: data.consensus ?? "N/A", // Added this
    articles_used: data.articles_used ?? [] // Added this
  };
}

// Simplified action listener
chrome.action.onClicked.addListener((tab) => {
  if (tab.url.startsWith("http")) {
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["panel.js"]
    });
  }
});
