if (chrome.contextMenus) {

const translations = {
  en: {
    contextMenuTitle: "Fact Check Selection",
    limitReachedExplanation: "You have used your 3 free daily checks. Please login or register for unlimited access!",
  },
  lt: {
    contextMenuTitle: "Fakto Tikrinimas",
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
  await getLang(); // Load current language
	// mock data
	/*
	return {
        verdict: "Mixed Accuracy",
        explanation: "The provided text contains multiple claims. Some are supported by scientific literature, while others are currently debated or unsupported.",
        score: 0.92, // 65% Confidence
        consensus: "Divided",
        articles_used: [
            { title: "Journal of Nutrition 2024", url: "#" },
            { title: "Health Science Review", url: "#" }
        ],
        // This is the specific data structure we just built the UI for
        individual_facts: [
            {
                claim: "Vitamin C prevents 100% of common colds.",
                verdict: "false",
                explanation: "Meta-analyses show Vitamin C may reduce duration but does not prevent infection in the general population."
            },
            {
                claim: "Regular exercise improves cardiovascular health.",
                verdict: "true",
                explanation: "Extensive longitudinal studies confirm a 30% reduction in heart disease risk for active individuals."
            },
            {
                claim: "New herbal supplement 'Healtea' cures insomnia.",
                verdict: "uncertain",
                explanation: "Insufficient clinical trials exist to verify this specific supplement's efficacy."
            }
        ]
    };
    */

    //prod
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

    return {
      verdict: data.final_verdict ?? "unverifiable",
      explanation: data.summary ?? "",
      score: typeof data.agreement_score === "number" ? data.agreement_score : 0,
      consensus: data.consensus ?? "N/A",
      articles_used: data.articles_used ?? [],
	  individual_facts: data.individual_facts ?? data.facts ?? []
	  //individual_results: data.individual_results ?? [] // papildomai
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

}
