const checkBtn = document.getElementById("checkBtn");
const claimInput = document.getElementById("claimInput");

const resultBox = document.getElementById("resultBox");
const verdictText = document.getElementById("verdict");
const explanationText = document.getElementById("explanation");
const scoreText = document.getElementById("score");


// Load selected text automatically
chrome.storage.local.get("lastClaim", (data) => {

  if (data.lastClaim) {
    claimInput.value = data.lastClaim;
    autoCheck();
  }

});


checkBtn.addEventListener("click", autoCheck);


function autoCheck() {

  const claim = claimInput.value.trim();

  if (!claim) return;

  verdictText.textContent = "Checking...";
  explanationText.textContent = "";
  scoreText.textContent = "";
  resultBox.classList.remove("hidden");


  chrome.runtime.sendMessage(
    {
      type: "FACT_CHECK",
      claim: claim
    },
    (response) => {

      if (!response) {
        verdictText.textContent = "Error";
        explanationText.textContent = "No response.";
		scoreText.textContent = "Error";
        return;
      }
		score = 60;
      verdictText.textContent = response.verdict;
      explanationText.textContent = response.explanation;
      scoreText.textContent = `Agreement score: ${Number(score ?? 0).toFixed(2)}`;

		updateScoreRing(score);
    }
  );

}

function updateScoreRing(score) {

  const circle = document.querySelector(".ringProgress");
  const scoreText = document.getElementById("scoreValue");

  const radius = 60;
  const circumference = 2 * Math.PI * radius;

  const offset = circumference - (score / 100) * circumference;

  circle.style.strokeDashoffset = offset;
	if (score > 70) circle.style.stroke = "#16a34a";
	else if (score > 40) circle.style.stroke = "#eab308";
	else circle.style.stroke = "#dc2626";
  
  animateScore(score);
}

function animateScore(targetScore) {

  const scoreText = document.getElementById("scoreValue");

  let current = 0;

	if (!score){
	  scoreText.textContent = "Error";
  }
  else {
  const interval = setInterval(() => {

    current += 2;

    if (current >= targetScore) {
      current = targetScore;
      clearInterval(interval);
    }

    scoreText.textContent = current;

  }, 10);
  }

  
}