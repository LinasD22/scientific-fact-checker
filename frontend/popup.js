const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const resultCard = document.getElementById("resultCard");
const authBtnAction = document.getElementById('authBtnAction');
const userInfo = document.getElementById('userInfo');
const themeToggle = document.getElementById("themeToggle");

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

  ocrShowState("file", file.name);
  ocrDropZone.classList.add("ocr-loading");
  ocrSpinner.style.display = "inline";
  ocrFileName.style.display = "none";

  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(OCR_API_URL, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${response.status}`);
    }

    const data = await response.json();
    const text = (data.text || "").trim();

    if (!text) {
      ocrShowState("error", "No text found in image.");
    } else {
      claimInput.value = text;
      ocrShowState("file", file.name);
      sendHeight();
    }
  } catch (err) {
    ocrShowState("error", err.message || "OCR failed. Please try again.");
  } finally {
    ocrDropZone.classList.remove("ocr-loading");
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

// ── Theme ─────────────────────────────────────────────────────────────────────
chrome.storage.local.get("theme", (data) => {
  if (data.theme === "dark") {
    document.body.classList.add("dark-mode");
    themeToggle.textContent = "☀️";
  } else {
    themeToggle.textContent = "🌙";
  }
});

// Load selected text but DO NOT auto-check
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
			userInfo.innerText = "Logged in as " + result.userEmail;
			authBtnAction.innerText = "Logout";
			checkBtn.disabled = false;
			checkBtn.style.opacity = "1";
			checkBtn.style.cursor = "pointer";
		} else {
			const count = (result.guestUsage && result.guestUsage.date === today)
					? result.guestUsage.count
					: 0;
			const remaining = Math.max(0, LIMIT - count);

			userInfo.innerText = `Guest: ${remaining} uses left today`;
			authBtnAction.innerText = "Login/Register";
			if (remaining <= 0) {
				checkBtn.disabled = true;
				btnText.textContent = "Daily Limit Reached";
				checkBtn.style.opacity = "0.6";
				checkBtn.style.cursor = "not-allowed";
			} else {
				checkBtn.disabled = false;
				btnText.textContent = "Check Fact";
				checkBtn.style.opacity = "1";
				checkBtn.style.cursor = "pointer";
			}
		}
	});
}

// Toggle logic
themeToggle.addEventListener("click", () => {
  const isDark = document.body.classList.toggle("dark-mode");
  themeToggle.textContent = isDark ? "☀️" : "🌙";
  chrome.storage.local.set({ theme: isDark ? "dark" : "light" });
});

// Clear Button Logic
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  resultCard.classList.add("hidden");
  ocrShowState("idle");
  sendHeight();
});

// Manual Check Logic
checkBtn.addEventListener("click", autoCheck);

function autoCheck() {
  const claim = claimInput.value.trim();
  if (!claim) return;

  checkBtn.disabled = true;
  btnText.textContent = "Checking...";
  resultCard.classList.add("hidden");
  sendHeight();

  chrome.runtime.sendMessage(
    { type: "FACT_CHECK", claim: claim },
    (response) => {
      checkBtn.disabled = false;
      btnText.textContent = "Check Fact";

	  updateUI();

      if (response.verdict === "Limit Reached") {
        updateUI();
        resultCard.classList.remove("hidden");
        document.getElementById("finalVerdict").textContent = "Limit Reached";
        document.getElementById("finalVerdict").className = "verdict uncertain";
        document.getElementById("finalExplanation").textContent = response.explanation;
        return;
      }

      // --- NEW CONDITIONAL LAYOUT LOGIC ---
      const facts = response.individual_facts || [];
      const factsContainer = document.getElementById("individualFactsContainer");
      const factsList = document.getElementById("individualFactsList");
      const mainScoreSection = document.querySelector(".scoreRingContainer");
      const mainVerdictSection = document.querySelector(".resultHeader");
      const finalExplanation = document.getElementById("finalExplanation");

      factsList.innerHTML = ""; // Clear old results

      if (facts.length > 1) {
        // CASE: MULTIPLE FACTS - Hide Big Ring, Show List
        mainScoreSection.style.display = "none";
        mainVerdictSection.style.display = "none";
        finalExplanation.style.display = "none";
		document.querySelector(".evidence-section").style.display = "none";
        factsContainer.style.display = "block";

        facts.forEach(fact => {
			const factDiv = document.createElement("div");
			factDiv.className = "fact-item";

			const vClass = getVerdictClass(fact.verdict);
			const scorePercent = Math.round(fact.score * 100);
			const sourcesHtml = generateSourcesHtml(fact.sources);

			// Get color based on score for the badge
			let scoreColorClass = "score-mid";
			if (scorePercent >= 70) scoreColorClass = "score-high";
			else if (scorePercent < 40) scoreColorClass = "score-low";

			factDiv.innerHTML = `
				<div class="fact-top-row">
					<div class="badge-stack">
						<span class="badge-label">CONFIDENCE</span>
						<div class="score-badge ${scoreColorClass}">
							${scorePercent}%
						</div>
					</div>
					<div class="fact-claim">"${fact.claim}"</div>
			</div>
			<div style="margin-bottom: 8px;">
				<span class="fact-verdict ${vClass}">${fact.verdict}</span>
			</div>
			<div class="fact-explanation">${fact.explanation}</div>
			<div class="fact-sources-list">${sourcesHtml}</div>
		`;
		factsList.appendChild(factDiv);
        });
      } else {
        // CASE: SINGLE FACT - Show Big Ring, Hide List
        mainScoreSection.style.display = "block";
        mainVerdictSection.style.display = "block";
        finalExplanation.style.display = "block";
		document.querySelector(".evidence-section").style.display = "block";
        factsContainer.style.display = "none";

        // Update the big ring and text
        const verdictEl = document.getElementById("finalVerdict");
        const vClass = getVerdictClass(response.verdict);

        verdictEl.textContent = response.verdict;
        verdictEl.className = `verdict ${vClass}`;
        finalExplanation.textContent = response.explanation;

        updateScoreRing(response.score * 100 || 0);
      }

      // Populate Global Articles (Bottom Section)
      updateArticlesList(response.articles_used);

      resultCard.classList.remove("hidden");
      document.getElementById("rawResponse").textContent = JSON.stringify(response, null, 2);
      setTimeout(sendHeight, 100);
    }
  );
}

// --- HELPER FUNCTIONS ---

function getVerdictClass(verdict) {
    const vText = (verdict || "").toLowerCase();
    if (vText.includes("supported") || vText.includes("true") || vText.includes("verified") || vText.includes("accurate")) return "true";
    if (vText.includes("refuted") || vText.includes("false") || vText.includes("inaccurate") || vText.includes("misleading")) return "false";
    return "uncertain";
}

function generateSourcesHtml(sources) {
    if (!sources || sources.length === 0) return '<span class="no-sources">No specific sources found</span>';
    return `
        <div style="font-size: 10px; font-weight: 700; margin-bottom: 4px; color: var(--text-muted);">SOURCES:</div>
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
                <div class="article-meta">${article.source} • ${article.published_date || 'Date Unknown'}</div>
            `;
            articlesList.appendChild(item);
        });
    } else {
        sourceCount.textContent = "0";
        articlesList.innerHTML = "<p class='article-meta'>No specific articles cited.</p>";
    }
}

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

  if (score >= 70) {
    circle.style.stroke = "var(--score-high)";
  } else if (score >= 40) {
    circle.style.stroke = "var(--score-mid)";
  } else {
    circle.style.stroke = "var(--score-low)";
  }

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

document.addEventListener('DOMContentLoaded', function() {
    authBtnAction.addEventListener('click', () => {
        chrome.storage.local.get(['token'], (result) => {
            if (result.token) {
                chrome.storage.local.remove(['token', 'userEmail'], () => {
                    updateUI();
                });
            } else {
                chrome.runtime.sendMessage({ type: "OPEN_AUTH" });
            }
        });
    });

    updateUI();
});