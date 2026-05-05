// Strip common markdown syntax, returning plain text
function stripMarkdown(text) {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    .replace(/~~(.+?)~~/g, "$1")
    .replace(/`{1,3}[^`]*`{1,3}/g, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "")
    .replace(/^[-_*]{3,}\s*$/gm, "")
    .replace(/>\s+/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

if (chrome.contextMenus) {

  const translations = {
    en: {
      contextMenuTitle: "Fact Check Selection (Default: Alt+Shift+F)",
      limitReachedExplanation: "You have used your 3 free daily checks. Please login or register for unlimited access!",
    },
    lt: {
      contextMenuTitle: "Fakto Tikrinimas (Numatytasis: Alt+Shift+F)",
      limitReachedExplanation: "Naudojote 3 nemokamus dienos tikrinimus. Prisijunkite arba užsiregistruokite neribotam naudojimui!",
    },
  };

  let currentLang = "en";

  async function getLang() {
    const data = await chrome.storage.local.get("language");
    if (data.language && ["en", "lt"].includes(data.language)) {
      currentLang = data.language;
    }
  }

  function t(key) {
    const keys = key.split(".");
    let value = translations[currentLang];
    for (const k of keys) {
      if (value && value[k] !== undefined) {
        value = value[k];
      } else {
        return key;
      }
    }
    return value;
  }

  chrome.runtime.onInstalled.addListener(async () => {
    await getLang();
    chrome.contextMenus.removeAll(() => {
      chrome.contextMenus.create({
        id: "factCheckSelection",
        title: t("contextMenuTitle"),
        contexts: ["selection"]
      });
      if (chrome.runtime.lastError) {
        console.log("Menu already exists, skipping...");
      }
    });
  });

  chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    if (info.menuItemId === "factCheckSelection") {
      const selectedText = info.selectionText || "";

      chrome.storage.local.set({ lastClaim: selectedText }, () => {
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

  // Refresh context menu when language changes (optional)
  chrome.storage.onChanged.addListener((changes, namespace) => {
    if (changes.language) {
      getLang().then(() => {
        chrome.contextMenus.removeAll(() => {
          chrome.contextMenus.create({
            id: "factCheckSelection",
            title: t("contextMenuTitle"),
            contexts: ["selection"]
          });
        });
      });
    }
  });

  // Merged Message Listener
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log("Background received message:", request);

    if (request.type === "OCR_REQUEST") {
      const OCR_API_URL = "http://localhost:8000/api/fact-check/ocr"; // local dev
      //const OCR_API_URL = "https://api.healthfactchecker.site/api/fact-check/ocr";
      try {
        // Reconstruct Blob from base64
        const binary = atob(request.data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: request.mimeType });

        const formData = new FormData();
        formData.append("file", blob, request.fileName);

        fetch(OCR_API_URL, { method: "POST", body: formData })
          .then(r => {
            if (!r.ok) return r.json().then(e => { throw new Error(e.detail || `Server error ${r.status}`); });
            return r.json();
          })
          .then(data => {
            const raw = (data.text || "").trim();
            const plain = stripMarkdown(raw);
            sendResponse({ text: plain });
          })
          .catch(err => sendResponse({ error: err.message || "OCR failed." }));
      } catch (err) {
        sendResponse({ error: err.message || "OCR failed." });
      }
      return true; // Keep channel open for async response
    }

    if (request.type === "FACT_CHECK") {
      // Handle fact check request
      checkFact(request.claim)
        .then(result => {
          sendResponse(result);

          chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
            if (tabs[0]) {
              chrome.tabs.sendMessage(tabs[0].id, {
                type: "HIGHLIGHT_TEXT",
                claim: request.claim,
                results: result
              });
            }
          });
        })
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
    await getLang(); // Load current language

    // Determine your URL (use local for testing, ddns for production)
    //server
    //const API_URL = "https://api.healthfactchecker.site/api/fact-check/search";
    //local
    const API_URL = "http://localhost:8000/api/fact-check/search";

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
        await getLang();
        return {
          verdict: "Limit Reached",
          explanation: t("limitReachedExplanation")
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
    const explanation_lt = data.summary_lithuanian || "";

    const mappedFacts = (data.all_results || []).map(res => ({
      claim: res.original_fact || "Unknown Claim",
      exact_quote: res.exact_quote || res.original_fact || "Unknown Claim",
      verdict: res.final_verdict || "unverifiable",
      explanation: res.summary || "",
      explanation_lt: res.summary_lithuanian || "",
      score: typeof res.agreement_score === "number" ? res.agreement_score : 0,
      sources: res.articles_used || [],
      snippets: (res.individual_results || []).map(item => ({
        ...item,
        explanation_lt: item.explanation_lithuanian || ""
      }))
    }));

    // Include individual_results for evidence panel
    const individualResults = (data.individual_results || []).map(item => ({
      ...item,
      // Ensure we have Lithuanian version of explanation if available
      explanation_lt: item.explanation_lithuanian || ""
    }));

    return {
      verdict: data.final_verdict ?? "unverifiable",
      explanation: data.summary ?? "",
      explanation_lt: explanation_lt,
      score: typeof data.agreement_score === "number" ? data.agreement_score : 0,
      consensus: data.consensus ?? "N/A",
      articles_used: data.articles_used ?? [],
      individual_facts: mappedFacts,
      individual_results: individualResults
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

  chrome.commands.onCommand.addListener((command) => {
    if (command === "trigger-fact-check") {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const activeTab = tabs[0];
        if (!activeTab || !activeTab.url.startsWith("http")) return;

        // 1. Get the selected text from the page
        chrome.scripting.executeScript({
          target: { tabId: activeTab.id },
          func: () => window.getSelection().toString()
        }).then(results => {
          const selectedText = results[0].result;
          
          if (selectedText && selectedText.trim().length > 0) {
            // 2. Store it so the panel can find it
            chrome.storage.local.set({ lastClaim: selectedText }, () => {
              // 3. Inject the panel.js to show the UI
              chrome.scripting.executeScript({
                target: { tabId: activeTab.id },
                files: ["panel.js"]
              }).catch(err => console.error("Injection failed:", err));
            });
          }
        });
      });
    }
  });

}