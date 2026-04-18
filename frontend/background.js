if (chrome.contextMenus) {

chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.removeAll(() => {
        chrome.contextMenus.create({
            id: "factCheckSelection",
            title: "Fact Check Selection",
            contexts: ["selection"]
        });
        if (chrome.runtime.lastError) {
            console.log("Menu already exists, skipping...");
        }
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

// Merged Message Listener
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log("Background received message:", request);

    if (request.type === "FACT_CHECK") {
        // Handle fact check request
        checkFact(request.claim)
            .then(result => sendResponse(result))
            .catch(err => {
                console.error("Fact check error:", err);
                sendResponse({ verdict: "Error", explanation: "Fact check failed." });
            });
        return true; // Keep channel open for async response
    }

    if (request.type === "OPEN_AUTH") {
        // Handle opening the login tab
        chrome.tabs.create({ url: "auth.html" });
        return true;
    }
});

// Updated checkFact function with Token Support
async function checkFact(claim) {
    // Determine your URL (use local for testing, ddns for production)
    const API_URL = "https://api.healthfactchecker.site/api/fact-check/search";
    //local
    //const API_URL = "http://localhost:8080/api/fact-check/search";

    // Retrieve the token from storage
    const { token } = await chrome.storage.local.get("token");

    if (!token) {
        const LIMIT = 3; // Max daily uses for guests
        const today = new Date().toLocaleDateString(); // e.g., "4/16/2026"

        let { guestUsage } = await chrome.storage.local.get("guestUsage");

        // Reset counter if it's a new day or doesn't exist
        if (!guestUsage || guestUsage.date !== today) {
            guestUsage = { date: today, count: 0 };
        }

        if (guestUsage.count >= LIMIT) {
            return {
                verdict: "Limit Reached",
                explanation: "You have used your 3 free daily checks. Please login or register for unlimited access!"
            };
        }

        // Increment and save guest usage
        guestUsage.count++;
        await chrome.storage.local.set({ guestUsage });
    }

    const response = await fetch(API_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...(token && { "Authorization": `Bearer ${token}` }) // Only add header if token exists
        },
        body: JSON.stringify({ claim: claim })
    });

    if (!response.ok) {
        throw new Error(`Server responded with ${response.status}`);
    }

    const data = await response.json();

    const mappedFacts = (data.all_results || []).map(res => ({
        claim: res.original_fact || "Unknown Claim",
        verdict: res.final_verdict || "unverifiable",
        explanation: res.summary || "",
        score: typeof res.agreement_score === "number" ? res.agreement_score : 0,
        sources: res.articles_used || []
    }));

    return {
      verdict: data.final_verdict ?? "unverifiable",
      explanation: data.summary ?? "",
      score: typeof data.agreement_score === "number" ? data.agreement_score : 0,
      consensus: data.consensus ?? "N/A",
      articles_used: data.articles_used ?? [],
      // Use the mapped array here
      individual_facts: mappedFacts
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
