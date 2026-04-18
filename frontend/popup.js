const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const resultCard = document.getElementById("resultCard");
const authBtnAction = document.getElementById('authBtnAction');
const userInfo = document.getElementById('userInfo');
const themeToggle = document.getElementById("themeToggle");

// Check for saved theme on load
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
    
    // Clear the storage immediately so it doesn't persist to the next tab
    chrome.storage.local.remove("lastClaim");
    
    // UI Refresh to ensure the panel height matches the new text
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
				btnText.textContent = "Daily Limit Reached"; // Updates text immediately
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
  
  // Update button icon
  themeToggle.textContent = isDark ? "☀️" : "🌙";
  
  // Save preference
  chrome.storage.local.set({ theme: isDark ? "dark" : "light" });
});

// Clear Button Logic
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  resultCard.classList.add("hidden");
  sendHeight();
});

// Manual Check Logic
checkBtn.addEventListener("click", autoCheck);

// ... existing code (theme logic, clearBtn, etc.) ...

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

// --- NEW HELPER FUNCTIONS (Add these at the very bottom of popup.js) ---

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

// Keep your existing updateScoreRing and sendHeight functions below...

function sendHeight() {
  const height = document.body.scrollHeight;
  window.parent.postMessage({ type: "RESIZE_PANEL", height: height }, "*");
}

// Call on load
window.addEventListener("load", sendHeight);

function updateScoreRing(score) {
  const circle = document.getElementById("ringProgress");
  
  // Radius is 52. Circumference = 2 * PI * r
  const radius = 52;
  const circumference = 2 * Math.PI * radius;

  // Calculate the offset
  const offset = circumference - (score / 100) * circumference;
  circle.style.strokeDashoffset = offset;

  // Dynamic colors matching CSS variables
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
  // Clear any existing intervals to prevent glitches on rapid clicks
  if (window.scoreInterval) clearInterval(window.scoreInterval);

  window.scoreInterval = setInterval(() => {
    current += Math.ceil(targetScore / 20); // Dynamic step size
    
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
                // LOGOUT LOGIC
                chrome.storage.local.remove(['token', 'userEmail'], () => {
                    updateUI();
                    // todo: Call backend /logout endpoint here if blacklisting
                });
            } else {
                // LOGIN LOGIC
                chrome.runtime.sendMessage({ type: "OPEN_AUTH" });
            }
        });
    });

    updateUI();
});
