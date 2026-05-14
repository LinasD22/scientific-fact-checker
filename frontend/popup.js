const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const inputError = document.getElementById("inputError");
const resultCard = document.getElementById("resultCard");
const authBtnAction = document.getElementById('authBtnAction');
const userInfo = document.getElementById('userInfo');
const themeToggle = document.getElementById("themeToggle");
const languageToggle = document.getElementById("languageToggle");

// ── OCR elements ──────────────────────────────────────────────────────────────
const ocrDropZone   = document.getElementById("ocrDropZone");
const ocrFileInput  = document.getElementById("ocrFileInput");
const ocrBrowseBtn  = document.getElementById("ocrBrowseBtn");
const ocrDropLabel  = document.getElementById("ocrDropLabel");
const ocrFileName   = document.getElementById("ocrFileName");
const ocrSpinner    = document.getElementById("ocrSpinner");
const ocrError      = document.getElementById("ocrError");

//const OCR_API_URL = "https://api.healthfactchecker.site/api/fact-check/ocr";
 const OCR_API_URL = "http://localhost:8000/api/fact-check/ocr"; // local dev

// ── OCR helpers ───────────────────────────────────────────────────────────────
function ocrShowState(state, message = "") {
  ocrDropLabel.style.display = "none";
  ocrFileName.style.display  = "none";
  ocrSpinner.style.display   = "none";
  ocrError.style.display     = "none";

  if (state === "idle") {
    ocrDropLabel.style.display = "inline";
  } else if (state === "file") {
    ocrFileName.textContent    = "📄 " + message;
    ocrFileName.style.display  = "inline";
  } else if (state === "loading") {
    ocrSpinner.style.display   = "inline";
  } else if (state === "error") {
    ocrError.textContent       = "⚠️ " + message;
    ocrError.style.display     = "inline";
  }
}

async function runOCR(file) {
  // Validate type
  if (!["image/png", "image/jpeg"].includes(file.type)) {
    ocrShowState("error", "Only PNG or JPEG images are supported.");
    return;
  }

  ocrShowState("loading");
  ocrDropZone.classList.add("ocr-loading");

  try {
    // Convert file to base64 so it can be passed via chrome.runtime.sendMessage
    // (FormData is not serialisable across the message channel)
    const arrayBuffer = await file.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    const base64 = btoa(binary);

    chrome.runtime.sendMessage(
      { type: "OCR_REQUEST", data: base64, mimeType: file.type, fileName: file.name },
      (response) => {
        ocrDropZone.classList.remove("ocr-loading");
        if (chrome.runtime.lastError) {
          ocrShowState("error", "Extension error. Please reload the page.");
          return;
        }
        if (response && response.error) {
          ocrShowState("error", response.error);
        } else if (response && response.text) {
           claimInput.value = response.text;
           inputError.style.display = "none";
           ocrShowState("file", file.name);
           sendHeight();
         } else {
          ocrShowState("error", "No text found in image.");
        }
      }
    );
  } catch (err) {
    ocrDropZone.classList.remove("ocr-loading");
    ocrShowState("error", err.message || "OCR failed. Please try again.");
  }
}

// Click-to-browse
ocrBrowseBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  ocrFileInput.click();
});

ocrDropZone.addEventListener("click", () => ocrFileInput.click());

ocrFileInput.addEventListener("change", () => {
  const file = ocrFileInput.files[0];
  if (file) runOCR(file);
  ocrFileInput.value = ""; // allow re-selecting the same file
});

// Drag-and-drop events
ocrDropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  ocrDropZone.classList.add("ocr-drag-over");
});

ocrDropZone.addEventListener("dragleave", (e) => {
  if (!ocrDropZone.contains(e.relatedTarget)) {
    ocrDropZone.classList.remove("ocr-drag-over");
  }
});

ocrDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  ocrDropZone.classList.remove("ocr-drag-over");
  const file = e.dataTransfer.files[0];
  if (file) runOCR(file);
});

let lastResponse = null; // Store the latest API response for language switching

// ── Translations ──────────────────────────────────────────────────────────────
const translations = {
  en: {
    title: "MediCheck",
    appTitle: "MediCheck",
    notLoggedIn: "Not logged in",
    loginOrRegister: "Login or Register",
    claimPlaceholder: "Paste a health claim to verify...",
    clear: "Clear",
    checkFact: "Check Fact",
    checking: "Checking...",
    confidence: "Confidence",
    individualClaims: "Individual Claims",
    sourcesUsedPrefix: "Sources Used",
    evidenceBySource: "Evidence by Source",
    rawJsonResponse: "Raw JSON Response",
    verdict: {
      verified: "VERIFIED",
      false: "FALSE",
      unverifiable: "UNCERTAIN",
      conflicting: "CONFLICTING",
      partially_verified: "PARTIALLY VERIFIED",
      limitReached: "Limit Reached",
      dailyLimitReached: "Daily Limit Reached",
    },
    guestUsage: "Guest: {{count}} uses left today",
    loggedInAs: "Logged in as {{email}}",
    logout: "Logout",
    loginRegister: "Login/Register",
    unknownSource: "Unknown source",
    dateUnknown: "Date Unknown",
    noEvidence: "No evidence details available.",
    noArticles: "No specific articles cited.",
    // Auth page translations
    loginTitle: "Login",
    firstName: "First Name",
    lastName: "Last Name",
    email: "Email",
    password: "Password",
    signIn: "Sign In",
    dontHaveAccount: "Don't have an account?",
    register: "Register",
    alreadyHaveAccount: "Already have an account?",
    createAccount: "Create Account",
    login: "Login",
 	tabCheck: "Check",
    tabHistory: "History",
    historyLoginPrompt: "Login to view your check history",
    historyLoading: "Loading history…",
    backToHistory: "Back to history",
    retry: "Retry",
    historyEmpty: "No checks yet — run your first fact check!",
    // Word count validation
    wordCountMin: "Please enter at least 3 words.",
    wordCountMax: "Please enter no more than 100 words.",

  },
  lt: {
    title: "MediCheck",
    appTitle: "MediCheck",
    notLoggedIn: "Neprisijungęs",
    loginOrRegister: "Prisijungti arba Registruotis",
    claimPlaceholder: "Įdėkite sveikatos teiginį patikrinimui...",
    clear: "Išvalyti",
    checkFact: "Tikrinti faktą",
    checking: "Tikrinama...",
    confidence: "Patikimumas",
    individualClaims: "Atskiri teiginiai",
    sourcesUsedPrefix: "Naudoti šaltiniai",
    evidenceBySource: "Įrodymai pagal šaltinį",
    rawJsonResponse: "Grynas JSON atsakas",
    verdict: {
      verified: "PATVIRINTAS",
      false: "KLAIDINGA",
      unverifiable: "NEAIŠKU",
      conflicting: "KONFLIKTUOJA",
      partially_verified: "DAUGIAU MAŽIAU PATVIRINTAS",
      limitReached: "Limitas pasiektas",
      dailyLimitReached: "Dienos limitas pasiektas",
    },
    guestUsage: "Svečias: liko {{count}} užklausos šiandien",
    loggedInAs: "Prisijungęs kaip {{email}}",
    logout: "Atsijungti",
    loginRegister: "Prisijungti/Registruotis",
    unknownSource: "Nežinomas šaltinis",
    dateUnknown: "Data nežinoma",
    noEvidence: "Įrodymų detalių neprieinama.",
    noArticles: "Necituoti konkretūs straipsniai.",
    // Auth page translations
    loginTitle: "Prisijungimas",
    firstName: "Vardas",
    lastName: "Pavardė",
    email: "El. paštas",
    password: "Slaptažodis",
    signIn: "Prisijungti",
    dontHaveAccount: "Neturite paskyros?",
    register: "Registruotis",
    alreadyHaveAccount: "Jau turite paskyrą?",
    createAccount: "Sukurti paskyrą",
    login: "Prisijungti",
	tabCheck: "Tikrinti",
    tabHistory: "Istorija",
    historyLoginPrompt: "Prisijunkite, kad matytumėte istorija",
    historyLoading: "Kraunama istorija…",
    backToHistory: "Grįžti į istoriją",
    retry: "Bandyti dar",
    historyEmpty: "Dar nėra patikrinimų — patikrinkite pirmą faktą!",
    // Word count validation
    wordCountMin: "Įveskite bent 3 žodžius.",
    wordCountMax: "Įveskite ne daugiau kaip 100 žodžių.",
  },
};

let currentLang = "en";

// ── Explanation Translations (Lithuanian) ─────────────────────────────────────
const explanationTranslations = {
  lt: {
    "The provided source does not support the claim that": "Duomenų šaltinis nepalaiko teiginio, kad",
    "eggs cause immortality": "kiaušiniaí padaro nešmiertelius",
    "The text discusses": "Tekste aptariama",
    "the rarity and difficulty of achieving": "reitės ir sunkumo pasiekimo",
    "cellular immortality in cancer biology": "kelių nešmiertelumas vėžio biologijoje",
    "with no mention of dietary factors like eggs": "nekalbama apie dietinius faktorius, tokius kaip kiaušiniai",
    "No evidence found in the provided sources to support this claim.": "Įrodymai, palaikantys šį teiginį, nėra pateiktuose šaltinyse.",
    "The sources do not provide sufficient information to verify this claim.": "Šaltiniuose nedadieja pakankamai informacijos šio teiginio patikrinimui.",
    "Multiple sources contradict this claim.": "Daug šaltiunių konfliktуoja su šiuo teiginiu.",
    "The claim is partially supported by some evidence, but significant contradictions exist.": "Teiginys dalinai palaikomas įrodaми, tačiau egzistuoja svarbų kontraktų.",
    "Insufficient evidence to reach a definitive conclusion.": "Netęstį įrodymų, kad pasiektų definitivo įvairo.",
  }
};

function t(key, params = {}) {
  const keys = key.split(".");
  let value = translations[currentLang];
  for (const k of keys) {
    if (value && value[k] !== undefined) {
      value = value[k];
    } else {
      // If it's a verdict key from backend (e.g., "verified"), fallback to verdict map
      if (currentLang === "lt" && keys.length === 1 && ["verified", "false", "unverifiable", "conflicting", "partially_verified", "limit", "uncertain"].includes(keys[0])) {
        return translateVerdict(keys[0]);
      }
      return key;
    }
  }
  if (typeof value === "string" && params) {
    Object.keys(params).forEach((p) => {
      value = value.replace(`{{${p}}}`, params[p]);
    });
  }
  return value;
}

function translateVerdict(verdict) {
   const map = {
     en: {
       verified: "VERIFIED",
       false: "FALSE",
       unverifiable: "UNCERTAIN",
       conflicting: "CONFLICTING",
       partially_verified: "PARTIALLY VERIFIED",
       limit: "LIMIT",
       uncertain: "UNCERTAIN",
       "limit reached": "LIMIT REACHED",
       "daily limit reached": "DAILY LIMIT REACHED",
     },
     lt: {
       verified: "PATVIRINTAS",
       false: "KLAIDINGA",
       unverifiable: "NEAIŠKU",
       conflicting: "KONFLIKTUOJA",
       partially_verified: "DAUGIAU MAŽIAU PATVIRINTAS",
       limit: "LIMITAS",
       uncertain: "NEAIŠKU",
       "limit reached": "LIMITAS PASIEKTAS",
       "daily limit reached": "DIENOS LIMITAS PASIEKTAS",
     },
   };
   const key = verdict.toLowerCase();
   return map[currentLang][key] || verdict.toUpperCase();
 }

// Returns the appropriate language version of an explanation
function getLocalizedExplanation(obj) {
    if (!obj) return "";
    if (currentLang === "lt") {
        return obj.explanation_lt || obj.explanation || "";
    }
    return obj.explanation || "";
}

 function translateExplanation(text) {
   // If not Lithuanian, return original text
   if (currentLang !== "lt") {
     return text;
   }

   // Try to translate using our dictionary
   const translations = explanationTranslations.lt;
   if (translations && text) {
     // Check for exact match first
     if (translations[text]) {
       return translations[text];
     }

     // Try to find and replace known phrases
     let translated = text;
     for (const [english, lithuanian] of Object.entries(translations)) {
       translated = translated.split(english).join(lithuanian);
     }
     return translated;
   }

   return text; // fallback to original
 }

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    el.placeholder = t(key);
  });
  // Translate verdicts that have data-verdict-key
  document.querySelectorAll("[data-verdict-key]").forEach((el) => {
    const key = el.getAttribute("data-verdict-key");
    el.textContent = translateVerdict(key);
  });
  document.documentElement.lang = currentLang;
}

// ── Theme Toggle ───────────────────────────────────────────────────────────────
chrome.storage.local.get(["theme", "language"], (data) => {
   // Theme
   if (data.theme === "dark") {
     document.body.classList.add("dark-mode");
     themeToggle.textContent = "☀️";
   } else {
     themeToggle.textContent = "🌙";
   }

   // Language
   if (data.language && ["en", "lt"].includes(data.language)) {
     currentLang = data.language;
   }
   applyTranslations();
   updateLanguageButtonText();

   // Update UI (which also updates auth button text)
   updateUI();
});

themeToggle.addEventListener("click", () => {
  const isDark = document.body.classList.toggle("dark-mode");
  themeToggle.textContent = isDark ? "☀️" : "🌙";
  chrome.storage.local.set({ theme: isDark ? "dark" : "light" });
});

languageToggle.addEventListener("click", () => {
    currentLang = currentLang === "en" ? "lt" : "en";
    chrome.storage.local.set({ language: currentLang });
    applyTranslations();
    updateLanguageButtonText();
    updateUI(); // Update dynamic UI (guest count, buttons)
    // Retranslate explanations if we have a stored response
    if (lastResponse) {
        retranslateExplanations();
    }
});

// Listen for language changes from other parts of the extension (e.g., background.js)
chrome.storage.onChanged.addListener((changes, namespace) => {
    if (changes.language) {
        currentLang = changes.language.newValue;
        applyTranslations();
        updateLanguageButtonText();
        updateUI(); // Update dynamic UI (guest count, buttons)
        // Retranslate explanations if we have a stored response
        if (lastResponse) {
            retranslateExplanations();
        }
    }
});

// ── Load selected text but DO NOT auto-check ─────────────────────────────────
chrome.storage.local.get("lastClaim", (data) => {
  if (data.lastClaim) {
    claimInput.value = data.lastClaim;
    chrome.storage.local.remove("lastClaim");
    setTimeout(sendHeight, 50);
  }
});

function updateUI() {
  const keysToFetch = ['token', 'userEmail', 'guestUsage', 'plan', 'isActive'];

// This will log if any key is accidentally null/undefined
  keysToFetch.forEach(key => {
      if (typeof key !== 'string') {
          console.error("Found a non-string key:", key);
      }
  });

  chrome.storage.local.get(keysToFetch, (result) => {
      if (chrome.runtime.lastError) {
          console.error("Storage Error:", chrome.runtime.lastError);
      } else {
          console.log("Storage Data retrieved:", result);
      }
  });

	chrome.storage.local.get(['token', 'userEmail', 'guestUsage', 'plan', 'isActive'], (result) => {
		const today = new Date().toLocaleDateString();
		const checkBtn = document.getElementById("checkBtn");
		const btnText = document.getElementById("btnText");
		const LIMIT = 3;
		if (result.token) {
      // Logged in user info
			userInfo.innerText = t("loggedInAs", { email: result.userEmail });
			authBtnAction.innerText = t("logout");

      // 2. Fetch the latest status from your FastAPI server
        fetch('http://127.0.0.1:8000/user-status', {
            headers: {
                'Authorization': `Bearer ${result.token}`}})
        .then(async response => {
          // Session expired
          if (response.status === 401) {
            const errorData = await response.json();
            if (errorData.detail === "SESSION_EXPIRED") {
              handleSessionEnd();
            }
            throw new Error('Unauthorized');
          }
           // Check for other general errors 
          if (!response.ok) {
            throw new Error('Server Error');
          }
          return response.json();
        })
        .then(data => {
          // Update the UI based on the server's real-time data
          const upgradeSection = document.getElementById("upgrade-section");
          const subDetails = document.getElementById("subscription-details");
          const planNameLabel = document.getElementById("plan-name-label");
          const usageCount = document.getElementById("usage-count");
          const renewalInfo = document.getElementById("renewal-info");

          if (data.isActive) {
              // toggle visibility
              upgradeSection.style.display = "none";
              subDetails.style.display = "block";

              // set labels
              planNameLabel.innerText = `${data.plan.toUpperCase()} MEMBER`;
              usageCount.innerText = `${data.queries_performed} queries used`;

              // format the renewal date
              if (data.renewal_time) {
                  const date = new Date(data.renewal_time);
                  renewalInfo.innerText = `Renews on: ${date.toLocaleDateString()}`;
              }
              
              console.log("User is active. UI updated to Pro state.");
          } else {
              // back to Free state
              upgradeSection.style.display = "block";
              subDetails.style.display = "none";
              console.log("User is free. Showing upgrade button.");
          }
        })
        .catch(err => {
            console.error("Failed to verify user status:", err);
            // Hide button if status check fails
            document.getElementById("upgrade-section").style.display = "none";
            // Fallback: show button if we can't confirm they are Pro
            //upgradeSection.style.display = "block";
        });

        // 4. Enable other buttons
        checkBtn.disabled = false;
        checkBtn.style.opacity = "1";
        checkBtn.style.cursor = "pointer";
    }
		 else {
			const count =
				result.guestUsage && result.guestUsage.date === today
					? result.guestUsage.count
					: 0;
			const remaining = Math.max(0, LIMIT - count);

			userInfo.innerText = t("guestUsage", { count: remaining });
			authBtnAction.innerText = t("loginRegister");
			if (remaining <= 0) {
				checkBtn.disabled = true;
				btnText.textContent = t("verdict.dailyLimitReached");
				checkBtn.style.opacity = "0.6";
				checkBtn.style.cursor = "not-allowed";
			} else {
				checkBtn.disabled = false;
				btnText.textContent = t("checkFact");
				checkBtn.style.opacity = "1";
				checkBtn.style.cursor = "pointer";
			}
		}
	});
}
document.getElementById("manage-billing-link").addEventListener("click", (e) => {
    e.preventDefault();

    // 1. Get the token from storage (same way your updateUI function does)
    chrome.storage.local.get(['token'], (result) => {
        if (!result.token) {
            alert("Please log in to manage your billing.");
            return;
        }

        // 2. Call the portal endpoint with the Bearer token
        fetch('http://127.0.0.1:8000/create-portal-session2', {
            headers: {
                'Authorization': `Bearer ${result.token}`
            }
        })
        .then(response => {
            if (!response.ok) throw new Error("Portal request failed");
            return response.json();
        })
        .then(data => {
            if (data.url) {
                // 3. Open Stripe's portal in a new tab
                chrome.tabs.create({ url: data.url });
            }
        })
        .catch(err => {
            console.error("Billing Error:", err);
            alert("Could not open billing portal. Please try again later.");
        });
    });
});

// Clear Button Logic
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  inputError.style.display = "none";
  resultCard.classList.add("hidden");
  ocrShowState("idle");
  sendHeight();
});

// Clear error on input
claimInput.addEventListener("input", () => {
  if (inputError.style.display === "block") {
    inputError.style.display = "none";
  }
});

function handleSessionEnd() {
    const statusMsg = document.getElementById("status-message");
    statusMsg.innerText = "Session expired. Please log in.";
    
    // Switch buttons back to Login mode
    authBtnAction.innerText = "Login";
    upgradeSection.style.display = "none";
    
    // Clear the dead token
    chrome.storage.local.remove(['token']);
}

// ── Manual Check Logic ────────────────────────────────────────────────────────
checkBtn.addEventListener("click", autoCheck);

// ... existing code (theme logic, clearBtn, etc.) ...


function autoCheck() {
  const claim = claimInput.value.trim();

  // Word count validation: [3, 100]
  const wordCount = claim.split(/\s+/).filter(w => w.length > 0).length;
  if (wordCount < 3) {
    inputError.textContent = t("wordCountMin");
    inputError.style.display = "block";
    return;
  }
  if (wordCount > 100) {
    inputError.textContent = t("wordCountMax");
    inputError.style.display = "block";
    return;
  }
  inputError.style.display = "none";

  checkBtn.disabled = true;
  btnText.textContent = t("checking");
  resultCard.classList.add("hidden");
  sendHeight();

  chrome.runtime.sendMessage(
    { type: "FACT_CHECK", claim: claim },
    (response) => {
      checkBtn.disabled = false;
      btnText.textContent = t("checkFact");

      if (response.verdict === "Limit Reached") {
        updateUI();
        resultCard.classList.remove("hidden");
        const verdictEl = document.getElementById("finalVerdict");
        verdictEl.textContent = t("verdict.limitReached");
        verdictEl.setAttribute("data-i18n", "verdict.limitReached");
        verdictEl.className = "verdict uncertain";
        const explanationEl = document.getElementById("finalExplanation");
        explanationEl.textContent = translateExplanation(response.explanation);
        // Store response for re-translation when language changes
        lastResponse = response;
        return;
      }

      // --- CONDITIONAL LAYOUT LOGIC ---
      const facts = response.individual_facts || [];
      const factsContainer = document.getElementById("individualFactsContainer");
      const factsList = document.getElementById("individualFactsList");
      const mainScoreSection = document.querySelector(".scoreRingContainer");
      const mainVerdictSection = document.querySelector(".resultHeader");
      const finalExplanation = document.getElementById("finalExplanation");
      const evidenceSection = document.querySelector(".evidence-section");

      factsList.innerHTML = ""; // Clear old results

      if (facts.length > 1) {
        // CASE: MULTIPLE FACTS - Hide Big Ring, Show List
        mainScoreSection.style.display = "none";
        mainVerdictSection.style.display = "none";
        finalExplanation.style.display = "none";
        if (evidenceSection) evidenceSection.style.display = "none";
        factsContainer.style.display = "block";

        facts.forEach(fact => {
          const factDiv = document.createElement("div");
          factDiv.className = "fact-item";

          const vClass = getVerdictClass(fact.verdict || fact.status || "");
          const scorePercent = Math.round((fact.score || 0) * 100);
          const sourcesHtml = generateSourcesHtml(fact.sources || []);

          // Get color based on score for the badge
          let scoreColorClass = "score-mid";
          if (scorePercent >= 70) scoreColorClass = "score-high";
          else if (scorePercent < 40) scoreColorClass = "score-low";

          const snippetsHtml = generateSnippetsHtml(fact.snippets || []);

          factDiv.innerHTML = `
            <div class="fact-top-row">
              <div class="badge-stack">
                <span class="badge-label">${t("confidence")}</span>
                <div class="score-badge ${scoreColorClass}">
                  ${scorePercent}%
                </div>
              </div>
              <div class="fact-claim">"${fact.claim}"</div>
            </div>
            <div style="margin-bottom: 8px;">
              <span class="fact-verdict ${vClass}" data-verdict-key="${fact.verdict || "uncertain"}">${translateVerdict(fact.verdict || "uncertain")}</span>
            </div>
            <div class="fact-explanation">${getLocalizedExplanation(fact)}</div>
            <div class="fact-sources-list">${sourcesHtml}</div>
            ${snippetsHtml ? `<div class="fact-snippets">${snippetsHtml}</div>` : ""}
          `;
          factsList.appendChild(factDiv);
        });
      } else {
        // CASE: SINGLE FACT - Show Big Ring, Hide List
        mainScoreSection.style.display = "block";
        mainVerdictSection.style.display = "block";
        finalExplanation.style.display = "block";
        if (evidenceSection) evidenceSection.style.display = "block";
        factsContainer.style.display = "none";

        // Update the big ring and text
        const verdictEl = document.getElementById("finalVerdict");
        const vClass = getVerdictClass(response.verdict || "unverifiable");

        verdictEl.textContent = translateVerdict(response.verdict || "unverifiable");
        verdictEl.setAttribute("data-verdict-key", response.verdict || "unverifiable");
        verdictEl.className = `verdict ${vClass}`;
        finalExplanation.textContent = getLocalizedExplanation(response);

        updateScoreRing((response.score || 0) * 100);
      }

      // Populate Evidence List (for individual results)
      const evidenceList = document.getElementById("evidenceList");
      if (evidenceList) {
        evidenceList.innerHTML = "";

        if (response.individual_results && response.individual_results.length > 0) {
          response.individual_results.forEach((r) => {
            const verdict = r.result || "unverifiable";
            const verdictClass = getVerdictClass(verdict);
            const explanation = currentLang === 'lt' ? (r.explanation_lt || r.explanation || "") : (r.explanation || "");

            const item = document.createElement("div");
            item.className = "evidence-item";
            item.innerHTML = `
              <div class="evidence-header">
                <span class="evidence-title">${r.source_title || t("unknownSource")}</span>
                <span class="verdict ${verdictClass}" data-verdict-key="${verdict}">${translateVerdict(verdict)}</span>
              </div>
              ${r.source_text ? `<blockquote class="evidence-snippet">${r.source_text}</blockquote>` : ""}
              ${explanation ? `<div class="evidence-explanation">${explanation}</div>` : ""}
              ${r.supporting_evidence?.length ? `<div class="evidence-tag support">✓ ${r.supporting_evidence[0]}</div>` : ""}
              ${r.contradicting_evidence?.length ? `<div class="evidence-tag contra">✗ ${r.contradicting_evidence[0]}</div>` : ""}
            `;
            evidenceList.appendChild(item);
          });
        } else {
          evidenceList.innerHTML = "<p class='article-meta'>" + t("noEvidence") + "</p>";
        }
      }

      // Populate Global Articles (Bottom Section)
      updateArticlesList(response.articles_used || []);

      resultCard.classList.remove("hidden");
      document.getElementById("rawResponse").textContent = JSON.stringify(
        response,
        null,
        2
      );

       setTimeout(sendHeight, 100);

       // Store response for language re-translation
       lastResponse = response;
     }
   );
}

// --- HELPER FUNCTIONS ---

function getVerdictClass(verdict) {
  const vText = (verdict || "").toLowerCase();
  if (vText.includes("supported") || vText.includes("true") || vText.includes("verified") || vText.includes("accurate"))
    return "true";
  if (vText.includes("refuted") || vText.includes("false") || vText.includes("inaccurate") || vText.includes("misleading"))
    return "false";
  return "uncertain";
}

function generateSnippetsHtml(snippets) {
  if (!snippets || snippets.length === 0) return "";
  const items = snippets.map(s => {
    const verdict = s.result || "unverifiable";
    const vClass = getVerdictClass(verdict);
    const text = s.source_text || "";
    const title = s.source_title || t("unknownSource");
    const explanation = currentLang === "lt" ? (s.explanation_lt || s.explanation || "") : (s.explanation || "");
    return `
      <div class="evidence-item">
        <div class="evidence-header">
          <span class="evidence-title">${title}</span>
          <span class="verdict ${vClass}" data-verdict-key="${verdict}">${translateVerdict(verdict)}</span>
        </div>
        ${text ? `<blockquote class="evidence-snippet">${text}</blockquote>` : ""}
        ${explanation ? `<div class="evidence-explanation">${explanation}</div>` : ""}
        ${s.supporting_evidence?.length ? `<div class="evidence-tag support">✓ ${s.supporting_evidence[0]}</div>` : ""}
        ${s.contradicting_evidence?.length ? `<div class="evidence-tag contra">✗ ${s.contradicting_evidence[0]}</div>` : ""}
      </div>
    `;
  }).join("");
  return `
    <details class="fact-snippets-details">
      <summary class="fact-snippets-summary">
        <span>${t("evidenceBySource")}</span>
        <span class="fact-snippets-count">${snippets.length}</span>
      </summary>
      <div class="fact-snippets-body">${items}</div>
    </details>
  `;
}

function generateSourcesHtml(sources) {
  if (!sources || sources.length === 0)
    return `<span class="no-sources">${t("noSourcesFound")}</span>`;
  return `
    <div style="font-size: 10px; font-weight: 700; margin-bottom: 4px; color: var(--text-muted);">${t("sources")}</div>
    ${sources.map(s => `<a href="${s.url}" target="_blank" class="mini-source">📄 ${s.title}</a>`).join('')}
  `;
}

function updateArticlesList(articles) {
  const articlesList = document.getElementById("articlesList");
  const sourceCount = document.getElementById("sourceCount");
  articlesList.innerHTML = "";

  if (articles && articles.length > 0) {
    sourceCount.textContent = articles.length;
    articles.forEach(article => {
      const item = document.createElement("div");
      item.className = "article-item";
      item.innerHTML = `
        <a href="${article.url}" target="_blank" class="article-title">${article.title}</a>
        <div class="article-meta">${article.source} • ${article.published_date || t("dateUnknown")}</div>
      `;
      articlesList.appendChild(item);
    });
  } else {
    sourceCount.textContent = "0";
    articlesList.innerHTML = "<p class='article-meta'>" + t("noArticles") + "</p>";
  }
}

function sendHeight() {
  // Use the container's scrollHeight (the true content height, unclipped)
  // so that float-mode can resize to fit all content without scrolling.
  const containerEl = document.querySelector(".container");
  const height = containerEl ? containerEl.scrollHeight + 16 : document.body.scrollHeight;
  window.parent.postMessage({ type: "RESIZE_PANEL", height: height }, "*");
}

window.addEventListener("load", sendHeight);

function updateScoreRing(score) {
  const ring = document.getElementById("ringProgress");
  if (!ring) return;

  // Ensure score is a rounded integer
  const roundedScore = Math.round(score || 0);

  const radius = ring.r.baseVal.value;
  const circumference = 2 * Math.PI * radius;

  ring.style.strokeDasharray = `${circumference} ${circumference}`;
  const offset = circumference - (roundedScore / 100) * circumference;
  ring.style.strokeDashoffset = offset;

  // Color logic
  if (roundedScore >= 70) {
    ring.style.stroke = "var(--score-high)";
  } else if (roundedScore >= 40) {
    ring.style.stroke = "var(--score-mid)";
  } else {
    ring.style.stroke = "var(--score-low)";
  }

  animateScoreText(roundedScore);
}

function animateScoreText(targetScore) {
  const scoreText = document.getElementById("scoreValue");

  if (targetScore === undefined || targetScore === null || isNaN(targetScore)) {
    scoreText.textContent = "0"; // Changed from "!" to "0" for cleaner look
    return;
  }

  // Ensure target is an integer
  const finalTarget = Math.round(targetScore);
  let current = 0;

  if (window.scoreInterval) clearInterval(window.scoreInterval);

  window.scoreInterval = setInterval(() => {
    // Incrementing logic
    const step = Math.ceil(finalTarget / 20) || 1;
    current += step;

    if (current >= finalTarget) {
      current = finalTarget;
      clearInterval(window.scoreInterval);
    }

    // Display as integer
    scoreText.textContent = current;
  }, 30);
}

function retranslateExplanations() {
    if (!lastResponse) return;

    // Retranslate main explanation
    const explanationEl = document.getElementById("finalExplanation");
    if (explanationEl) {
        explanationEl.textContent = getLocalizedExplanation(lastResponse);
    }

    // Retranslate individual fact explanations
    const factsList = document.getElementById("individualFactsList");
    if (factsList && lastResponse.individual_facts) {
        const factItems = factsList.getElementsByClassName("fact-item");
        for (let i = 0; i < factItems.length && i < lastResponse.individual_facts.length; i++) {
            const factExplanationEl = factItems[i].querySelector(".fact-explanation");
            if (factExplanationEl) {
                factExplanationEl.textContent = getLocalizedExplanation(lastResponse.individual_facts[i]);
            }
        }
    }

    // Retranslate evidence explanations
    const evidenceList = document.getElementById("evidenceList");
    if (evidenceList && lastResponse.individual_results) {
        const evidenceItems = evidenceList.getElementsByClassName("evidence-item");
        for (let i = 0; i < evidenceItems.length && i < lastResponse.individual_results.length; i++) {
            const evidenceExplanationEl = evidenceItems[i].querySelector(".evidence-explanation");
            if (evidenceExplanationEl) {
                evidenceExplanationEl.textContent = getLocalizedExplanation(lastResponse.individual_results[i]);
            }
        }
    }
}

function updateLanguageButtonText() {
    const languageToggle = document.getElementById("languageToggle");
    // Show the opposite language: if current is EN, show LT to switch to LT; if current is LT, show EN to switch to EN
    languageToggle.textContent = currentLang === "en" ? "LT" : "EN";
}

document.getElementById("closePanelBtn").addEventListener("click", () => {
  window.parent.postMessage({ type: "CLOSE_PANEL" }, "*");
});

document.getElementById("viewModeBtn").addEventListener("click", () => {
  window.parent.postMessage({ type: "TOGGLE_PANEL_MODE" }, "*");
});

// Listen for mode changes from parent (panel.js) to update button tooltip
window.addEventListener("message", (event) => {
  if (event.data && event.data.type === "MODE_CHANGED") {
    const btn = document.getElementById("viewModeBtn");
    if (btn) {
      btn.textContent = "⇔";
      btn.title = event.data.mode === "side" ? "Switch to floating panel" : "Dock to side panel";
    }
    // Toggle float-mode so CSS can remove max-height clamping
    document.body.classList.toggle("float-mode", event.data.mode === "float");
    sendHeight();
  }
});

// ── Auth Button ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  authBtnAction.addEventListener("click", () => {
    chrome.storage.local.get(["token"], (result) => {
      if (result.token) {
        chrome.storage.local.remove(["token", "userEmail"], () => {
          updateUI();
        });
      } else {
        chrome.runtime.sendMessage({ type: "OPEN_AUTH" });
      }
    });
  });

  updateUI();
});

// ── History API base URL ──────────────────────────────────────────────────────
const HISTORY_API = "https://api.healthfactchecker.site/history";
//const HISTORY_API = "http://localhost:8000/history";
 
// ── Tab switching ─────────────────────────────────────────────────────────────
const tabCheck   = document.getElementById("tabCheck");
const tabHistory = document.getElementById("tabHistory");
const checkView  = document.getElementById("checkView");
const historyView = document.getElementById("historyView");
 
tabCheck.addEventListener("click", () => {
  tabCheck.classList.add("active");
  tabHistory.classList.remove("active");
  checkView.style.display = "block";
  historyView.style.display = "none";
  sendHeight();
});
 
tabHistory.addEventListener("click", () => {
  tabHistory.classList.add("active");
  tabCheck.classList.remove("active");
  checkView.style.display = "none";
  historyView.style.display = "block";
  loadHistory();
  sendHeight();
});
 
// ── Helper: show only one sub-state inside historyView ────────────────────────
function showHistoryState(state) {
  // state: "empty" | "loading" | "error" | "list" | "detail"
  document.getElementById("historyEmpty").style.display  = state === "empty"   ? "flex" : "none";
  document.getElementById("historyLoading").style.display = state === "loading" ? "flex" : "none";
  document.getElementById("historyError").style.display  = state === "error"   ? "flex" : "none";
  document.getElementById("historyList").style.display   = state === "list"    ? "block" : "none";
  document.getElementById("historyDetail").style.display = state === "detail"  ? "block" : "none";
  setTimeout(sendHeight, 80);
}
 
// ── Verdict dot color helper (reuses your existing getVerdictClass) ───────────
function verdictDotClass(verdict) {
  return getVerdictClass(verdict); // returns "true", "false", or "uncertain"
}
 
// ── Format date for display ───────────────────────────────────────────────────
function formatHistoryDate(dateStr) {
  if (!dateStr) return "";
  try {
    return new Date(dateStr).toLocaleDateString(currentLang === "lt" ? "lt-LT" : "en-GB", {
      day: "numeric", month: "short", year: "numeric"
    });
  } catch {
    return dateStr;
  }
}
 
// ── Load history list ─────────────────────────────────────────────────────────
async function loadHistory() {
  showHistoryState("loading");
 
  const { token, userId } = await chrome.storage.local.get(["token", "userId"]);
 
  if (!token || !userId) {
    showHistoryState("empty");
    // wire up the login button inside the empty state
    document.getElementById("historyLoginBtn").onclick = () => {
      chrome.runtime.sendMessage({ type: "OPEN_AUTH" });
    };
    return;
  }
 
  try {
    const res = await fetch(`${HISTORY_API}/user/${userId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
 
    if (!res.ok) {
      throw new Error(`Server error ${res.status}`);
    }
 
    const data = await res.json();
    const queries = data.queries || [];
 
    const container = document.getElementById("historyItems");
    container.innerHTML = "";
 
    if (queries.length === 0) {
      // Show empty state with a different message (logged in but no checks yet)
      const emptyIcon = document.querySelector(".history-empty-icon");
      const emptyText = document.querySelector(".history-empty-text");
      if (emptyIcon) emptyIcon.textContent = "📋";
      if (emptyText) emptyText.textContent = t("historyEmpty");
      document.getElementById("historyLoginBtn").style.display = "none";
      showHistoryState("empty");
      return;
    }
 
    queries.forEach(q => {
      const dotClass = verdictDotClass(q.final_verdict || "unverifiable");
      const verdictLabel = translateVerdict(q.final_verdict || "unverifiable");
      const dateLabel = formatHistoryDate(q.claim_date);
 
      const item = document.createElement("div");
      item.className = "history-item";
      item.innerHTML = `
        <div class="history-item-verdict ${dotClass}"></div>
        <div class="history-item-body">
          <div class="history-item-claim">${escapeHtml(q.claim)}</div>
          <div class="history-item-meta">
            <span>${verdictLabel}</span>
            <span class="history-item-meta-dot"></span>
            <span>${dateLabel}</span>
          </div>
        </div>
        <span class="history-item-chevron">›</span>
      `;
      item.addEventListener("click", () => loadHistoryDetail(userId, q.query_id, token, q.claim));
      container.appendChild(item);
    });
 
    showHistoryState("list");
 
  } catch (err) {
    console.error("History load failed:", err);
    document.getElementById("historyErrorMsg").textContent =
      "Could not load history. " + (err.message || "");
    document.getElementById("historyRetryBtn").onclick = loadHistory;
    showHistoryState("error");
  }
}
 
// ── Load detail for a single history item ─────────────────────────────────────
async function loadHistoryDetail(userId, queryId, token, claimText) {
  showHistoryState("loading");
 
  try {
    const res = await fetch(`${HISTORY_API}/user/${userId}/query/${queryId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
 
    if (!res.ok) {
      throw new Error(`Server error ${res.status}`);
    }
 
    const data = await res.json();
 
    // The detail response matches the same shape as a live fact-check response
    // so we can render it with your existing helpers.
    renderHistoryDetail(data, claimText);
 
  } catch (err) {
    console.error("History detail failed:", err);
    document.getElementById("historyErrorMsg").textContent =
      "Could not load details. " + (err.message || "");
    document.getElementById("historyRetryBtn").onclick = () =>
      loadHistoryDetail(userId, queryId, token, claimText);
    showHistoryState("error");
  }
}
 
// ── Render a history detail using the same card HTML as live results ──────────
function renderHistoryDetail(response, claimText) {
  const detailContent = document.getElementById("historyDetailContent");
 
  // Build the same card structure your live result uses
  const vClass = getVerdictClass(response.final_verdict || "unverifiable");
  const verdictLabel = translateVerdict(response.final_verdict || "unverifiable");
  const scorePercent = Math.round((response.facts?.[0]?.agreement_score || 0) * 100);
  const explanation = currentLang === "lt"
    ? (response.facts?.[0]?.summary_lithuanian || response.facts?.[0]?.summary || "")
    : (response.facts?.[0]?.summary || "");
 
  // Build articles HTML from the nested facts structure
  const articles = response.facts?.flatMap(f => f.articles_used || []) || [];
  const articlesHtml = articles.length > 0
    ? articles.map(a => `
        <div class="article-item">
          <a href="${escapeHtml(a.url)}" target="_blank" class="article-title">${escapeHtml(a.title || "")}</a>
          <div class="article-meta">${escapeHtml(a.source || "")} · ${a.published_date || t("dateUnknown")}</div>
        </div>`).join("")
    : `<p class="article-meta">${t("noArticles")}</p>`;
 
  detailContent.innerHTML = `
    <div class="resultCard" style="margin-top: 0;">
      <div style="font-size:12px; color:var(--text-muted); text-align:left; margin-bottom:12px; font-style:italic; line-height:1.4;">
        "${escapeHtml(claimText || "")}"
      </div>
 
      <div class="scoreRingContainer">
        <svg class="progressRing" width="120" height="120">
          <circle class="ringTrack" cx="60" cy="60" r="52"></circle>
          <circle class="ringProgress" id="historyRingProgress" cx="60" cy="60" r="52"></circle>
        </svg>
        <div class="scoreCenter">
          <span id="historyScoreValue">0</span>
          <span class="scoreLabel">${t("confidence")}</span>
        </div>
      </div>
 
      <div class="resultHeader">
        <div class="verdict ${vClass}">${verdictLabel}</div>
      </div>
 
      <div class="explanation">${escapeHtml(explanation)}</div>
 
      <hr class="divider">
 
      <details class="evidence-section">
        <summary>
          <span>${t("sourcesUsedPrefix")}</span>: <span>${articles.length}</span>
        </summary>
        <div class="articles-container">${articlesHtml}</div>
      </details>
    </div>
  `;
 
  showHistoryState("detail");
 
  // Animate the score ring (same logic as your main updateScoreRing)
  const ring = detailContent.querySelector("#historyRingProgress");
  const scoreEl = detailContent.querySelector("#historyScoreValue");
  if (ring && scoreEl) {
    const radius = 52;
    const circumference = 2 * Math.PI * radius;
    ring.style.strokeDasharray = `${circumference} ${circumference}`;
    ring.style.strokeDashoffset = circumference;
 
    if (scorePercent >= 70)      ring.style.stroke = "var(--score-high)";
    else if (scorePercent >= 40) ring.style.stroke = "var(--score-mid)";
    else                         ring.style.stroke = "var(--score-low)";
 
    const offset = circumference - (scorePercent / 100) * circumference;
    // Small timeout so the CSS transition fires after the element is in the DOM
    setTimeout(() => {
      ring.style.strokeDashoffset = offset;
    }, 50);
 
    let current = 0;
    const interval = setInterval(() => {
      current += Math.ceil(scorePercent / 20) || 1;
      if (current >= scorePercent) { current = scorePercent; clearInterval(interval); }
      scoreEl.textContent = current;
    }, 30);
  }
}

// ── Payment API base URL ──────────────────────────────────────────────────────
//const PAYMENT_API = "https://api.healthfactchecker.site";
const PAYMENT_API = "http://localhost:8000";

async function checkLoginStatus() {
    const upgradeSection = document.getElementById('upgrade-section');
    const loginNotice = document.getElementById('login-notice');

    // Match the key "token" from auth.js
    const result = await chrome.storage.local.get(['token', 'userEmail', 'isActive']);
    const token = result.token;

    if (!token) {
        showLoggedOut();
        return;
    }

    // Backend call to verify token and get subscription status
    try {
        const response = await fetch('${PAYMENT_API}/user-status', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const status = await response.json();
            
            // Toggle visibility based on subscription status
            if (!status.is_active) {
                upgradeSection.style.display = 'block';
                loginNotice.style.display = 'none';
            } else {
                upgradeSection.style.display = 'none';
                loginNotice.innerHTML = "<p>⭐ Basic Account Active</p>";
                loginNotice.style.display = 'block';
            }
        } else {
            showLoggedOut();
        }
    } catch (error) {
        console.error("Backend unreachable", error);
        showLoggedOut();
    }
}
function showLoggedOut() {
    document.getElementById('upgrade-section').style.display = 'none';
    document.getElementById('login-notice').style.display = 'block';
}

// THE MAIN ENTRY POINT
document.addEventListener('DOMContentLoaded', () => {
    // Run the login/subscription check
    checkLoginStatus();

    // button listener
    const upgradeBtn = document.getElementById("upgrade-button");
    upgradeBtn.addEventListener("click", async () => {
        const data = await chrome.storage.local.get(["token", "userEmail"]);
        
        if (!data.userEmail) {
            alert("Email not found. Please log in again.");
            return;
        }

        try {
            const response = await fetch(`${PAYMENT_API}/create-checkout-session?email=${data.userEmail}`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${data.token}` }
            });
            
            const session = await response.json();
            if (session.url) {
                window.open(session.url, "_blank"); 
            }
        } catch (err) {
            console.error("Stripe session failed:", err);
            alert("Failed to start checkout.");
        }
    });
});
 
// ── Back button ───────────────────────────────────────────────────────────────
document.getElementById("historyBackBtn").addEventListener("click", () => {
  showHistoryState("list");
});
 
// ── Simple HTML escape to avoid XSS from server data ─────────────────────────
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
