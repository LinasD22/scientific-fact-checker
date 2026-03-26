const checkBtn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const btnText = document.getElementById("btnText");
const claimInput = document.getElementById("claimInput");
const resultCard = document.getElementById("resultCard");

// 1. Load selected text but DO NOT auto-check
chrome.storage.local.get("lastClaim", (data) => {
  if (data.lastClaim) {
    claimInput.value = data.lastClaim;
    
    // Clear the storage immediately so it doesn't persist to the next tab
    chrome.storage.local.remove("lastClaim");
    
    // UI Refresh to ensure the panel height matches the new text
    setTimeout(sendHeight, 50);
  }
});

// 2. Clear Button Logic
clearBtn.addEventListener("click", () => {
  claimInput.value = "";
  resultCard.classList.add("hidden");
  sendHeight();
});

// 3. Manual Check Logic
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
    // ... inside your chrome.runtime.sendMessage callback ...
(response) => {
    checkBtn.disabled = false;
    btnText.textContent = "Check Fact";
    resultCard.classList.remove("hidden");

    // 1. Basic Info
    document.getElementById("finalVerdict").textContent = response.verdict;
    document.getElementById("finalExplanation").textContent = response.explanation;
    document.getElementById("consensusBadge").textContent = response.consensus || "N/A";
    
    // 2. Score Ring
    updateScoreRing(response.score * 100 || 0);

    // 3. Populate Articles
    const articlesList = document.getElementById("articlesList");
    const sourceCount = document.getElementById("sourceCount");
    articlesList.innerHTML = ""; // Clear old results

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

    // 4. Raw Debug for Testing
    document.getElementById("rawResponse").textContent = JSON.stringify(response, null, 2);

    // 5. Adjust Panel Height
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
