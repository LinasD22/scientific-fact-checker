const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const resultCard = document.getElementById("resultCard");

const themeToggle = document.getElementById("themeToggle");
const languageToggle = document.getElementById("languageToggle");

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
    claimPlaceholder: "Įklijuokite sveikatos teiginį patikrinimui...",
    clear: "Išvalyti",
    checkFact: "Tikrinti faktą",
    checking: "Tikrinama...",
    confidence: "Pasitikėjimas",
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
    guestUsage: "Svečias: liko {{count}} naudojimų",
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
  updateUI(); // Re-run to update dynamic text (guest count, etc.)
});

// ── Load selected text but DO NOT auto-check ─────────────────────────────────
chrome.storage.local.get("lastClaim", (data) => {
  if (data.lastClaim) {
    claimInput.value = data.lastClaim;
    chrome.storage.local.remove("lastClaim");
    setTimeout(sendHeight, 50);
  }
});

// ── Clear Button ──────────────────────────────────────────────────────────────
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  resultCard.classList.add("hidden");
  sendHeight();
});

// ── Manual Check Logic ────────────────────────────────────────────────────────
checkBtn.addEventListener("click", autoCheck);

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
        document.getElementById("finalExplanation").textContent = response.explanation;
        return;
      }

      const verdictEl = document.getElementById("finalVerdict");
      const verdictText = (response.verdict || "").toLowerCase();

      verdictEl.textContent = translateVerdict(response.verdict || "unverifiable");
      verdictEl.setAttribute("data-verdict-key", response.verdict || "unverifiable");
      verdictEl.className = "verdict";

      if (verdictText.includes("limit")) verdictEl.classList.add("uncertain");
      else if (verdictText.includes("supported") || verdictText.includes("true"))
        verdictEl.classList.add("true");
      else if (verdictText.includes("refuted") || verdictText.includes("false"))
        verdictEl.classList.add("false");
      else verdictEl.classList.add("uncertain");

      resultCard.classList.remove("hidden");
      document.getElementById("finalExplanation").textContent = response.explanation;

      const factsContainer = document.getElementById("individualFactsContainer");
      const factsList = document.getElementById("individualFactsList");
      factsList.innerHTML = "";

      if (response.individual_facts && response.individual_facts.length > 0) {
        factsContainer.style.display = "block";
        response.individual_facts.forEach((fact) => {
          const factDiv = document.createElement("div");
          factDiv.className = "fact-item";

          let vClass = "uncertain";
          const vText = (fact.verdict || fact.status || "").toLowerCase();
          if (vText.includes("supported") || vText.includes("true"))
            vClass = "true";
          else if (vText.includes("refuted") || vText.includes("false"))
            vClass = "false";

          factDiv.innerHTML = `
                <div class="fact-claim">"${fact.claim}"</div>
                <div style="margin-bottom: 6px;">
                    <span class="fact-verdict ${vClass}" data-verdict-key="${fact.verdict || "uncertain"}">${translateVerdict(fact.verdict || "uncertain")}</span>
                </div>
                <div class="fact-explanation">${fact.explanation || fact.summary || ""}</div>
            `;
          factsList.appendChild(factDiv);
        });
      } else {
        factsContainer.style.display = "none";
      }

      updateScoreRing((response.score || 0) * 100);

      const articlesList = document.getElementById("articlesList");
      const sourceCount = document.getElementById("sourceCount");
      articlesList.innerHTML = "";

      const evidenceList = document.getElementById("evidenceList");
      if (evidenceList) {
        evidenceList.innerHTML = "";

        if (response.individual_results && response.individual_results.length > 0) {
          response.individual_results.forEach((r) => {
            const verdict = r.result || "unverifiable";
            const verdictClass = verdict.includes("verified")
              ? "true"
              : verdict === "false"
              ? "false"
              : "uncertain";

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
                    <div class="evidence-explanation">${r.explanation || ""}</div>
                    ${r.supporting_evidence?.length ? `<div class="evidence-tag support">✓ ${r.supporting_evidence[0]}</div>` : ""}
                    ${r.contradicting_evidence?.length ? `<div class="evidence-tag contra">✗ ${r.contradicting_evidence[0]}</div>` : ""}
                `;
            evidenceList.appendChild(item);
          });
        } else {
          evidenceList.innerHTML = "<p class='article-meta'>" + t("noEvidence") + "</p>";
        }
      }

      if (response.articles_used && response.articles_used.length > 0) {
        sourceCount.textContent = response.articles_used.length;
        response.articles_used.forEach((article) => {
          const item = document.createElement("div");
          item.className = "article-item";
          item.innerHTML = `
                <a href="${article.url}" target="_blank" class="article-title">${article.title}</a>
                <div class="article-meta">
                    ${article.source} • ${article.published_date || t("dateUnknown")}
                </div>
            `;
          articlesList.appendChild(item);
        });
      } else {
        sourceCount.textContent = "0";
        articlesList.innerHTML = "<p class='article-meta'>" + t("noArticles") + "</p>";
      }

      document.getElementById("rawResponse").textContent = JSON.stringify(
        response,
        null,
        2
      );

      setTimeout(sendHeight, 100);
    }
  );
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
