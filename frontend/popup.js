const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const resultCard = document.getElementById("resultCard");
const authBtnAction = document.getElementById('authBtnAction');
const userInfo = document.getElementById('userInfo');
const themeToggle = document.getElementById("themeToggle");
const languageToggle = document.getElementById("languageToggle");

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
	chrome.storage.local.get(['token', 'userEmail', 'guestUsage'], (result) => {
		const today = new Date().toLocaleDateString();
		const checkBtn = document.getElementById("checkBtn");
		const btnText = document.getElementById("btnText");
		const LIMIT = 3;
		if (result.token) {
			userInfo.innerText = t("loggedInAs", { email: result.userEmail });
			authBtnAction.innerText = t("logout");
			checkBtn.disabled = false;
			checkBtn.style.opacity = "1";
			checkBtn.style.cursor = "pointer";
		} else {
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

// Clear Button Logic
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  resultCard.classList.add("hidden");
  sendHeight();
});

// ── Manual Check Logic ────────────────────────────────────────────────────────
checkBtn.addEventListener("click", autoCheck);

// ... existing code (theme logic, clearBtn, etc.) ...

function autoCheck() {
  const claim = claimInput.value.trim();
  if (!claim) return;

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

            const item = document.createElement("div");
            item.className = "evidence-item";
            item.innerHTML = `
              <div class="evidence-header">
                <span class="evidence-title">${r.source_title || t("unknownSource")}</span>
              </div>
              <div class="evidence-verdict-wrapper">
                <span class="verdict ${verdictClass}" data-verdict-key="${verdict}" style="font-size:11px; padding:2px 6px; display: inline-block;">${translateVerdict(verdict)}</span>
              </div>
              <div class="evidence-snippet">"${r.source_text || ""}"</div>
               <div class="evidence-explanation">${currentLang === 'lt' ? (r.explanation_lt || r.explanation || "") : (r.explanation || "")}</div>
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

// ── Resize & Score ────────────────────────────────────────────────────────────
function sendHeight() {
  const height = document.body.scrollHeight;
  window.parent.postMessage({ type: "RESIZE_PANEL", height: height }, "*");
}

window.addEventListener("load", sendHeight);

function updateScoreRing(score) {
  const circle = document.getElementById("ringProgress");
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  circle.style.strokeDashoffset = offset;

  if (score >= 70) circle.style.stroke = "var(--score-high)";
  else if (score >= 40) circle.style.stroke = "var(--score-mid)";
  else circle.style.stroke = "var(--score-low)";

  animateScoreText(score);
}

function animateScoreText(targetScore) {
   const scoreText = document.getElementById("scoreValue");
   if (targetScore === undefined || targetScore === null || isNaN(targetScore)) {
     scoreText.textContent = "!";
     return;
   }

   let current = 0;
   if (window.scoreInterval) clearInterval(window.scoreInterval);

   window.scoreInterval = setInterval(() => {
     current += Math.ceil(targetScore / 20);
     if (current >= targetScore) {
       current = targetScore;
       clearInterval(window.scoreInterval);
     }
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

// ── Auth & UI ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  const authBtnAction = document.getElementById("authBtnAction");
  const userInfo = document.getElementById("userInfo");

  function updateUI() {
    chrome.storage.local.get(["token", "userEmail", "guestUsage"], (result) => {
      const today = new Date().toLocaleDateString();
      const checkBtn = document.getElementById("checkBtn");
      const btnText = document.getElementById("btnText");
      const LIMIT = 3;

      if (result.token) {
        userInfo.innerText = t("loggedInAs", { email: result.userEmail });
        authBtnAction.innerText = t("logout");
        checkBtn.disabled = false;
        checkBtn.style.opacity = "1";
        checkBtn.style.cursor = "pointer";
      } else {
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
