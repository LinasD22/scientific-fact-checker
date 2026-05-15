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

const OCR_API_URL = "https://api.healthfactchecker.site/api/fact-check/ocr";
 //const OCR_API_URL = "http://localhost:8000/api/fact-check/ocr"; // local dev

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
    verdictBreakdown: "Verdict Breakdown",
    individualClaims: "Individual Claims",
    sourcesUsedPrefix: "Sources Used",
    evidenceBySource: "Evidence by Source",
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
    verdictBreakdown: "Verdikto Paskirstymas",
    individualClaims: "Atskiri teiginiai",
    sourcesUsedPrefix: "Naudoti šaltiniai",
    evidenceBySource: "Įrodymai pagal šaltinį",
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

  // ── Payment API base URL ──────────────────────────────────────────────────────
const PAYMENT_API = "https://api.healthfactchecker.site";
//const PAYMENT_API = "http://localhost:8000";

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
        fetch(`${PAYMENT_API}/user-status`, {
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
        fetch(`${PAYMENT_API}/create-portal-session2`, {
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

  // Show the result card immediately with a spinning ring animation
  resultCard.classList.remove("hidden");
  resultCard.classList.add("checking");
  document.getElementById("scoreValue").textContent = "…";
  document.getElementById("finalVerdict").textContent = "";
  document.getElementById("finalExplanation").textContent = "";
  document.getElementById("individualFactsContainer").style.display = "none";
  const _evSecLoading = document.querySelector(".evidence-section");
  if (_evSecLoading) _evSecLoading.style.display = "none";
  document.querySelector(".scoreRingContainer").style.display = "block";
  document.querySelector(".resultHeader").style.display = "flex";
  document.getElementById("finalExplanation").style.display = "block";
  sendHeight();

  chrome.runtime.sendMessage(
    { type: "FACT_CHECK", claim: claim },
    (response) => {
      checkBtn.disabled = false;
      btnText.textContent = t("checkFact");
      // Remove the loading spinner state before rendering results
      resultCard.classList.remove("checking");

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

        renderVerdictDistributionChart(facts);

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

        renderVerdictDistributionChart([]);

        // Update the big ring and text
        const verdictEl = document.getElementById("finalVerdict");
        const vClass = getVerdictClass(response.verdict || "unverifiable");

        verdictEl.textContent = translateVerdict(response.verdict || "unverifiable");
        verdictEl.setAttribute("data-verdict-key", response.verdict || "unverifiable");
        verdictEl.className = `verdict ${vClass}`;
        finalExplanation.textContent = getLocalizedExplanation(response);

        updateScoreRing((response.score || 0) * 100, response.verdict);
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

function normalizeVerdictForChart(raw) {
  const text = (raw || "").toLowerCase();
  if (text.includes("partially") || text.includes("partially_verified")) return "partially_verified";
  if (text.includes("conflicting")) return "conflicting";
  if (text.includes("supported") || text.includes("true") || text.includes("verified") || text.includes("accurate")) return "verified";
  if (text.includes("refuted") || text.includes("false") || text.includes("inaccurate") || text.includes("misleading")) return "false";
  return "unverifiable"; // default / uncertain
}

function aggregateVerdictCounts(facts) {
  const counts = {
    verified: 0,
    false: 0,
    unverifiable: 0,
    conflicting: 0,
    partially_verified: 0
  };
  
  for (const fact of facts) {
    const canonical = normalizeVerdictForChart(fact.verdict || fact.status || "");
    counts[canonical]++;
  }
  return counts;
}

function renderVerdictDistributionChart(facts) {
  const container = document.getElementById("verdictDistribution");
  const svg = document.getElementById("verdictDonutSvg");
  const legend = document.getElementById("verdictDonutLegend");
  const centerText = document.getElementById("donutCenterText");
  
  if (!facts || facts.length <= 1) {
    if (container) container.style.display = "none";
    if (svg) svg.innerHTML = "";
    if (legend) legend.innerHTML = "";
    return;
  }
  
  if (container) container.style.display = "block";
  
  const counts = aggregateVerdictCounts(facts);
  const total = facts.length;
  
  if (centerText) {
    centerText.textContent = total;
  }
  
  const classMap = {
    verified: "donut-slice-true",
    false: "donut-slice-false",
    unverifiable: "donut-slice-uncertain",
    conflicting: "donut-slice-conflicting",
    partially_verified: "donut-slice-partially"
  };
  
  // Draw SVG
  if (svg) {
    svg.innerHTML = "";
    
    const ariaLabel = Object.entries(counts)
      .filter(([key, count]) => count > 0)
      .map(([key, count]) => `${count} ${translateVerdict(key)}`)
      .join(", ");
    svg.setAttribute("aria-label", `Verdict distribution: ${ariaLabel}`);
    
    let currentAngle = 0;
    const cx = 60;
    const cy = 60;
    const r = 52;
    const innerR = 30;
    
    // Filter out zero counts
    const slices = Object.entries(counts).filter(([key, count]) => count > 0);
    
    slices.forEach(([key, count]) => {
      const sliceAngle = (count / total) * 360;
      
      // If it's a full circle
      if (sliceAngle === 360) {
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${r} ${r} 0 1 1 ${cx} ${cy - r} M ${cx} ${cy - innerR} A ${innerR} ${innerR} 0 1 0 ${cx} ${cy + innerR} A ${innerR} ${innerR} 0 1 0 ${cx} ${cy - innerR}`);
        path.setAttribute("class", `donut-slice ${classMap[key]}`);
        svg.appendChild(path);
      } else {
        const startAngleRad = (currentAngle - 90) * Math.PI / 180;
        const endAngleRad = (currentAngle + sliceAngle - 90) * Math.PI / 180;
        
        const x1 = cx + r * Math.cos(startAngleRad);
        const y1 = cy + r * Math.sin(startAngleRad);
        const x2 = cx + r * Math.cos(endAngleRad);
        const y2 = cy + r * Math.sin(endAngleRad);
        
        const ix1 = cx + innerR * Math.cos(startAngleRad);
        const iy1 = cy + innerR * Math.sin(startAngleRad);
        const ix2 = cx + innerR * Math.cos(endAngleRad);
        const iy2 = cy + innerR * Math.sin(endAngleRad);
        
        const largeArcFlag = sliceAngle > 180 ? 1 : 0;
        
        const d = [
          `M ${x1} ${y1}`,
          `A ${r} ${r} 0 ${largeArcFlag} 1 ${x2} ${y2}`,
          `L ${ix2} ${iy2}`,
          `A ${innerR} ${innerR} 0 ${largeArcFlag} 0 ${ix1} ${iy1}`,
          "Z"
        ].join(" ");
        
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", d);
        path.setAttribute("class", `donut-slice ${classMap[key]}`);
        svg.appendChild(path);
      }
      
      currentAngle += sliceAngle;
    });
  }
  
  // Draw Legend
  if (legend) {
    legend.innerHTML = "";
    
    // Sort by count descending
    const sortedKeys = Object.entries(counts)
      .filter(([key, count]) => count > 0)
      .sort((a, b) => b[1] - a[1]);
      
    sortedKeys.forEach(([key, count]) => {
      const row = document.createElement("div");
      row.className = "donut-legend-row";
      
      const swatch = document.createElement("div");
      swatch.className = `donut-legend-swatch ${classMap[key]}`;
      
      const label = document.createElement("span");
      label.className = "donut-legend-label";
      label.textContent = translateVerdict(key);
      label.setAttribute("data-verdict-key", key);
      
      const countEl = document.createElement("span");
      countEl.className = "donut-legend-count";
      countEl.textContent = count;
      
      row.appendChild(swatch);
      row.appendChild(label);
      row.appendChild(countEl);
      
      legend.appendChild(row);
    });
  }
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
  const height = containerEl ? containerEl.scrollHeight : document.body.scrollHeight;
  window.parent.postMessage({ type: "RESIZE_PANEL", height: height }, "*");
}

window.addEventListener("load", sendHeight);

function verdictToRingColor(verdict) {
  const vClass = getVerdictClass(verdict || "");
  if (vClass === "true")  return "var(--score-high)";
  if (vClass === "false") return "var(--score-low)";
  const vText = (verdict || "").toLowerCase();
  if (vText.includes("conflicting")) return "var(--score-conflicting)";
  if (vText.includes("partial"))     return "var(--score-partially)";
  return "var(--score-mid)";
}

function updateScoreRing(score, verdict) {
  const ring = document.getElementById("ringProgress");
  if (!ring) return;

  // Ensure score is a rounded integer
  const roundedScore = Math.round(score || 0);

  const radius = ring.r.baseVal.value;
  const circumference = 2 * Math.PI * radius;

  ring.style.strokeDasharray = `${circumference} ${circumference}`;
  const offset = circumference - (roundedScore / 100) * circumference;
  ring.style.strokeDashoffset = offset;

  // Color matches verdict badge
  ring.style.stroke = verdictToRingColor(verdict);

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

    if (lastResponse.individual_facts && lastResponse.individual_facts.length > 1) {
        renderVerdictDistributionChart(lastResponse.individual_facts);
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
    const isFloat = event.data.mode === "float";
    document.body.classList.toggle("float-mode", isFloat);
    document.documentElement.classList.toggle("float-mode", isFloat);
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
// HISTORY_API = "http://localhost:8000/history";
 
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

  // ── Map history API shape → same shape that the live check uses ──────────────
  // History API: response.facts[] each has { original_fact, agreement_score,
  //   final_verdict, summary, summary_lithuanian, articles_used, individual_results }
  // Live check:  individual_facts[] each has { claim, score, verdict,
  //   explanation, explanation_lt, sources, snippets }

  const rawFacts = response.facts || [];

  const mappedFacts = rawFacts.map(f => ({
    claim:          f.original_fact || f.claim || "",
    exact_quote:    f.original_fact || f.claim || "",
    verdict:        f.final_verdict  || "unverifiable",
    explanation:    f.summary        || "",
    explanation_lt: f.summary_lithuanian || "",
    score:          typeof f.agreement_score === "number" ? f.agreement_score : 0,
    sources:        f.articles_used  || [],
    snippets:       (f.individual_results || []).map(r => ({
      ...r,
      explanation_lt: r.explanation_lithuanian || r.explanation_lt || ""
    }))
  }));

  // Overall figures (fall back to first fact when the top-level is absent)
  const overallVerdict  = response.final_verdict  || rawFacts[0]?.final_verdict  || "unverifiable";
  const overallScore    = typeof response.agreement_score === "number"
                            ? response.agreement_score
                            : (rawFacts[0]?.agreement_score || 0);
  const overallExpl     = currentLang === "lt"
                            ? (response.summary_lithuanian || response.summary || rawFacts[0]?.summary_lithuanian || rawFacts[0]?.summary || "")
                            : (response.summary            || rawFacts[0]?.summary || "");

  const allArticles     = rawFacts.flatMap(f => f.articles_used || []);
  const allIndividual   = rawFacts.flatMap(f =>
    (f.individual_results || []).map(r => ({
      ...r,
      explanation_lt: r.explanation_lithuanian || r.explanation_lt || ""
    }))
  );

  // ── Build the card scaffold ──────────────────────────────────────────────────
  const isMulti = mappedFacts.length > 1;

  detailContent.innerHTML = `
    <div class="resultCard" style="margin-top:0;">

      <!-- Claim text -->
      <div style="font-size:12px; color:var(--text-muted); text-align:left;
                  margin-bottom:12px; font-style:italic; line-height:1.4;">
        "${escapeHtml(claimText || "")}"
      </div>

      <!-- ── SINGLE-FACT: big score ring ────────────────────────────────── -->
      <div id="hd-singleSection" style="display:${isMulti ? "none" : "block"};">
        <div class="scoreRingContainer">
          <svg class="progressRing" width="120" height="120">
            <circle class="ringTrack"    cx="60" cy="60" r="52"></circle>
            <circle class="ringProgress" cx="60" cy="60" r="52" id="hdRingProgress"></circle>
          </svg>
          <div class="scoreCenter">
            <span id="hdScoreValue">0</span>
            <span class="scoreLabel">${t("confidence")}</span>
          </div>
        </div>
        <div class="resultHeader">
          <div class="verdict ${getVerdictClass(overallVerdict)}"
               data-verdict-key="${overallVerdict}">
            ${translateVerdict(overallVerdict)}
          </div>
        </div>
        <div class="explanation">${escapeHtml(overallExpl)}</div>
      </div>

      <!-- ── MULTI-FACT: donut chart + fact cards ───────────────────────── -->
      <div id="hd-multiSection" style="display:${isMulti ? "block" : "none"};">

        <!-- Verdict distribution donut (populated by JS below) -->
        <div id="hd-verdictDistribution" style="display:none;">
          <div style="font-size:13px; font-weight:700; text-align:left;
                      margin-bottom:10px;" data-i18n="verdictBreakdown">
            ${t("verdictBreakdown")}
          </div>
          <div class="donut-container">
            <div class="donut-chart-wrapper">
              <svg id="hd-verdictDonutSvg" width="120" height="120" viewBox="0 0 120 120"></svg>
              <div class="donut-center-text" id="hd-donutCenterText"></div>
            </div>
            <div id="hd-verdictDonutLegend" class="donut-legend"></div>
          </div>
        </div>

        <hr class="divider">
        <div style="font-size:13px; font-weight:700; text-align:left; margin-bottom:10px;"
             data-i18n="individualClaims">${t("individualClaims")}</div>
        <div id="hd-factsList" style="display:flex; flex-direction:column; gap:10px;"></div>
      </div>

      <hr class="divider">

      <!-- Sources / evidence (always shown) -->
      <details class="evidence-section" id="hd-evidenceSection">
        <summary>
          <span data-i18n="sourcesUsedPrefix">${t("sourcesUsedPrefix")}</span>:
          <span id="hd-sourceCount">${allArticles.length}</span>
        </summary>
        <div id="hd-articlesList" class="articles-container"></div>
        <div class="section-header" data-i18n="evidenceBySource">${t("evidenceBySource")}</div>
        <div id="hd-evidenceList"></div>
      </details>

    </div>
  `;

  // ── Populate articles ────────────────────────────────────────────────────────
  const articlesListEl = detailContent.querySelector("#hd-articlesList");
  if (allArticles.length > 0) {
    articlesListEl.innerHTML = allArticles.map(a => `
      <div class="article-item">
        <a href="${escapeHtml(a.url || "")}" target="_blank" class="article-title">
          ${escapeHtml(a.title || "")}
        </a>
        <div class="article-meta">
          ${escapeHtml(a.source || "")} · ${escapeHtml(a.published_date || t("dateUnknown"))}
        </div>
      </div>`).join("");
  } else {
    articlesListEl.innerHTML = `<p class="article-meta">${t("noArticles")}</p>`;
  }

  // ── Populate evidence by source ──────────────────────────────────────────────
  const evidenceListEl = detailContent.querySelector("#hd-evidenceList");
  if (allIndividual.length > 0) {
    evidenceListEl.innerHTML = allIndividual.map(r => {
      const verdict = r.result || "unverifiable";
      const vClass  = getVerdictClass(verdict);
      const expl    = currentLang === "lt" ? (r.explanation_lt || r.explanation || "") : (r.explanation || "");
      return `
        <div class="evidence-item">
          <div class="evidence-header">
            <span class="evidence-title">${escapeHtml(r.source_title || t("unknownSource"))}</span>
            <span class="verdict ${vClass}" data-verdict-key="${verdict}">${translateVerdict(verdict)}</span>
          </div>
          ${r.source_text ? `<blockquote class="evidence-snippet">${escapeHtml(r.source_text)}</blockquote>` : ""}
          ${expl ? `<div class="evidence-explanation">${escapeHtml(expl)}</div>` : ""}
          ${r.supporting_evidence?.length  ? `<div class="evidence-tag support">✓ ${escapeHtml(r.supporting_evidence[0])}</div>`  : ""}
          ${r.contradicting_evidence?.length ? `<div class="evidence-tag contra">✗ ${escapeHtml(r.contradicting_evidence[0])}</div>` : ""}
        </div>`;
    }).join("");
  } else {
    evidenceListEl.innerHTML = `<p class="article-meta">${t("noEvidence")}</p>`;
  }

  // ── Branch: single vs multi ──────────────────────────────────────────────────
  if (isMulti) {
    // Render donut chart using the same helper, but targeting the hd- elements.
    // We temporarily swap the IDs the helper reads, then restore them.
    _renderDonutForHistory(mappedFacts, detailContent);

    // Render individual fact cards (same markup as live check)
    const factsList = detailContent.querySelector("#hd-factsList");
    mappedFacts.forEach(fact => {
      const factDiv = document.createElement("div");
      factDiv.className = "fact-item";

      const vClass       = getVerdictClass(fact.verdict || "");
      const scorePercent = Math.round((fact.score || 0) * 100);
      let scoreColorClass = "score-mid";
      if (scorePercent >= 70) scoreColorClass = "score-high";
      else if (scorePercent < 40) scoreColorClass = "score-low";

      const sourcesHtml  = generateSourcesHtml(fact.sources || []);
      const snippetsHtml = generateSnippetsHtml(fact.snippets || []);
      const expl         = getLocalizedExplanation(fact);

      factDiv.innerHTML = `
        <div class="fact-top-row">
          <div class="badge-stack">
            <span class="badge-label">${t("confidence")}</span>
            <div class="score-badge ${scoreColorClass}">${scorePercent}%</div>
          </div>
          <div class="fact-claim">"${escapeHtml(fact.claim)}"</div>
        </div>
        <div style="margin-bottom:8px;">
          <span class="fact-verdict ${vClass}"
                data-verdict-key="${fact.verdict || "uncertain"}">
            ${translateVerdict(fact.verdict || "uncertain")}
          </span>
        </div>
        <div class="fact-explanation">${escapeHtml(expl)}</div>
        <div class="fact-sources-list">${sourcesHtml}</div>
        ${snippetsHtml ? `<div class="fact-snippets">${snippetsHtml}</div>` : ""}
      `;
      factsList.appendChild(factDiv);
    });

  } else {
    // Animate the single-fact score ring
    const scorePercent = Math.round(overallScore * 100);
    const ring   = detailContent.querySelector("#hdRingProgress");
    const scoreEl = detailContent.querySelector("#hdScoreValue");
    if (ring && scoreEl) {
      const circumference = 2 * Math.PI * 52;
      ring.style.strokeDasharray  = `${circumference} ${circumference}`;
      ring.style.strokeDashoffset = circumference;
      ring.style.stroke = verdictToRingColor(overallVerdict);
      setTimeout(() => {
        ring.style.strokeDashoffset = circumference - (scorePercent / 100) * circumference;
      }, 50);
      let cur = 0;
      const iv = setInterval(() => {
        cur += Math.ceil(scorePercent / 20) || 1;
        if (cur >= scorePercent) { cur = scorePercent; clearInterval(iv); }
        scoreEl.textContent = cur;
      }, 30);
    }
  }

  showHistoryState("detail");
  setTimeout(sendHeight, 100);
}

// ── Donut chart renderer scoped to history detail ─────────────────────────────
// Mirrors renderVerdictDistributionChart() but targets the hd- prefixed elements
// so it never clobbers the live-check chart.
function _renderDonutForHistory(facts, container) {
  const distEl   = container.querySelector("#hd-verdictDistribution");
  const svg      = container.querySelector("#hd-verdictDonutSvg");
  const legend   = container.querySelector("#hd-verdictDonutLegend");
  const centerTx = container.querySelector("#hd-donutCenterText");

  if (!facts || facts.length <= 1) {
    if (distEl) distEl.style.display = "none";
    return;
  }
  if (distEl) distEl.style.display = "block";

  const counts = aggregateVerdictCounts(facts);
  const total  = facts.length;
  if (centerTx) centerTx.textContent = total;

  const classMap = {
    verified:          "donut-slice-true",
    false:             "donut-slice-false",
    unverifiable:      "donut-slice-uncertain",
    conflicting:       "donut-slice-conflicting",
    partially_verified:"donut-slice-partially"
  };

  if (svg) {
    svg.innerHTML = "";
    let currentAngle = 0;
    const cx = 60, cy = 60, r = 52, innerR = 30;
    const slices = Object.entries(counts).filter(([, c]) => c > 0);

    slices.forEach(([key, count]) => {
      const sliceAngle = (count / total) * 360;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");

      if (sliceAngle === 360) {
        path.setAttribute("d",
          `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${r} ${r} 0 1 1 ${cx} ${cy - r} ` +
          `M ${cx} ${cy - innerR} A ${innerR} ${innerR} 0 1 0 ${cx} ${cy + innerR} A ${innerR} ${innerR} 0 1 0 ${cx} ${cy - innerR}`
        );
      } else {
        const s  = (currentAngle - 90) * Math.PI / 180;
        const e  = (currentAngle + sliceAngle - 90) * Math.PI / 180;
        const x1 = cx + r * Math.cos(s),       y1 = cy + r * Math.sin(s);
        const x2 = cx + r * Math.cos(e),       y2 = cy + r * Math.sin(e);
        const ix1= cx + innerR * Math.cos(s),  iy1= cy + innerR * Math.sin(s);
        const ix2= cx + innerR * Math.cos(e),  iy2= cy + innerR * Math.sin(e);
        const laf = sliceAngle > 180 ? 1 : 0;
        path.setAttribute("d",
          `M ${x1} ${y1} A ${r} ${r} 0 ${laf} 1 ${x2} ${y2} ` +
          `L ${ix2} ${iy2} A ${innerR} ${innerR} 0 ${laf} 0 ${ix1} ${iy1} Z`
        );
      }
      path.setAttribute("class", `donut-slice ${classMap[key] || ""}`);
      svg.appendChild(path);
      currentAngle += sliceAngle;
    });
  }

  if (legend) {
    legend.innerHTML = "";
    Object.entries(counts)
      .filter(([, c]) => c > 0)
      .sort((a, b) => b[1] - a[1])
      .forEach(([key, count]) => {
        const row    = document.createElement("div");
        row.className = "donut-legend-row";
        const swatch = document.createElement("div");
        swatch.className = `donut-legend-swatch ${classMap[key] || ""}`;
        const label  = document.createElement("span");
        label.className = "donut-legend-label";
        label.textContent = translateVerdict(key);
        label.setAttribute("data-verdict-key", key);
        const countEl = document.createElement("span");
        countEl.className = "donut-legend-count";
        countEl.textContent = count;
        row.append(swatch, label, countEl);
        legend.appendChild(row);
      });
  }
}


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