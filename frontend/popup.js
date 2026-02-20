const checkBtn = document.getElementById("checkBtn");
const claimInput = document.getElementById("claimInput");

const resultBox = document.getElementById("resultBox");
const verdictText = document.getElementById("verdict");
const explanationText = document.getElementById("explanation");


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
        return;
      }

      verdictText.textContent = response.verdict;
      explanationText.textContent = response.explanation;

    }
  );

}

