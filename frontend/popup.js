const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const resultCard = document.getElementById("resultCard");

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

// Toggle logic
themeToggle.addEventListener("click", () => {
  const isDark = document.body.classList.toggle("dark-mode");
  
  // Update button icon
  themeToggle.textContent = isDark ? "☀️" : "🌙";
  
  // Save preference
  chrome.storage.local.set({ theme: isDark ? "dark" : "light" });
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

// Clear Button Logic
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  resultCard.classList.add("hidden");
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
		// Check if the response indicates the limit was hit
		if (response.verdict === "Limit Reached") {
			updateUI(); // Trigger the UI refresh to lock the button
			resultCard.classList.remove("hidden");
			document.getElementById("finalVerdict").textContent = "Limit Reached";
			document.getElementById("finalVerdict").className = "verdict uncertain";
			document.getElementById("finalExplanation").textContent = response.explanation;
			return; 
		}

		// Basic Info
		const verdictEl = document.getElementById("finalVerdict");
		const verdictText = (response.verdict || "").toLowerCase();

		verdictEl.textContent = response.verdict;
		verdictEl.className = "verdict"; // Reset classes

		if (verdictText.includes("limit")) {
			verdictEl.classList.add("uncertain"); // Using your yellow theme
		} else if (verdictText.includes("supported") || verdictText.includes("true")) {
			verdictEl.classList.add("true");
		} else if (verdictText.includes("refuted") || verdictText.includes("false")) {
			verdictEl.classList.add("false");
		} else {
			verdictEl.classList.add("uncertain");
		resultCard.classList.remove("hidden");
	}

	document.getElementById("finalExplanation").textContent = response.explanation;
    
	const factsContainer = document.getElementById("individualFactsContainer");
    const factsList = document.getElementById("individualFactsList");
    factsList.innerHTML = ""; // Clear old individual facts

    if (response.individual_facts && response.individual_facts.length > 0) {
        factsContainer.style.display = "block";
        
        response.individual_facts.forEach(fact => {
            const factDiv = document.createElement("div");
            factDiv.className = "fact-item";

            // Determine color class for the individual verdict
            let vClass = "uncertain";
            const vText = (fact.verdict || fact.status || "").toLowerCase();
            if (vText.includes("supported") || vText.includes("true")) vClass = "true";
            else if (vText.includes("refuted") || vText.includes("false")) vClass = "false";

            // Build the mini-card
            factDiv.innerHTML = `
                <div class="fact-claim">"${fact.claim}"</div>
                <div style="margin-bottom: 6px;">
                    <span class="fact-verdict ${vClass}">${fact.verdict || "Uncertain"}</span>
                </div>
                <div class="fact-explanation">${fact.explanation || fact.summary || ""}</div>
            `;
            factsList.appendChild(factDiv);
        });
    } else {
        factsContainer.style.display = "none";
    }
	
    // Score Ring
    updateScoreRing(response.score * 100 || 0);

    // Populate Articles
    const articlesList = document.getElementById("articlesList");
    const sourceCount = document.getElementById("sourceCount");
    articlesList.innerHTML = ""; // Clear old results

    // naujas - Po articles bloko, pridėk Sources & Evidence sekciją
    const evidenceList = document.getElementById("evidenceList");
    if (evidenceList) {
        evidenceList.innerHTML = "";

        if (response.individual_results && response.individual_results.length > 0) {
            response.individual_results.forEach((r, i) => {
                const verdict = r.result || "unverifiable";
                const verdictClass = verdict.includes("verified") ? "true"
                    : verdict === "false" ? "false" : "uncertain";

                const item = document.createElement("div");
                item.className = "evidence-item";
                item.innerHTML = `
                    <div class="evidence-header">
                        <span class="evidence-title">${r.source_title || "Unknown source"}</span>
                    </div>
                    <div class="evidence-verdict-wrapper">
                        <span class="verdict ${verdictClass}" style="font-size:11px; padding:2px 6px; display: inline-block;">${verdict}</span>
                    </div>
                    <div class="evidence-snippet">"${r.source_text || ""}"</div>
                    <div class="evidence-explanation">${r.explanation || ""}</div>
                    ${r.supporting_evidence?.length ? `<div class="evidence-tag support">✓ ${r.supporting_evidence[0]}</div>` : ""}
                    ${r.contradicting_evidence?.length ? `<div class="evidence-tag contra">✗ ${r.contradicting_evidence[0]}</div>` : ""}
                `;
                evidenceList.appendChild(item);
            });
        } else {
            evidenceList.innerHTML = "<p class='article-meta'>No evidence details available.</p>";
        }
    }
    //

    if (response.articles_used && response.articles_used.length > 0) {
        sourceCount.textContent = response.articles_used.length;
        
        response.articles_used.forEach(article => {
            const item = document.createElement("div");
            item.className = "article-item";
            item.innerHTML = `
                <a href="${article.url}" target="_blank" class="article-title">${article.title}</a>
                <div class="article-meta">
                    ${article.source} • ${article.published_date || 'Date Unknown'}
                </div>
            `;
            articlesList.appendChild(item);
        });
    } else {
        sourceCount.textContent = "0";
        articlesList.innerHTML = "<p class='article-meta'>No specific articles cited.</p>";
    }

    // Raw Debug for Testing
    document.getElementById("rawResponse").textContent = JSON.stringify(response, null, 2);

    // Adjust Panel Height
    setTimeout(sendHeight, 100);
}
  );
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
    const authBtnAction = document.getElementById('authBtnAction');
    const userInfo = document.getElementById('userInfo');

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
