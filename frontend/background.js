if (chrome.contextMenus) {

  chrome.runtime.onInstalled.addListener(() => {

    chrome.contextMenus.create({
      id: "factCheckSelection",
      title: "Fact Check Selection",
      contexts: ["selection"]
    });

  });


  chrome.contextMenus.onClicked.addListener((info) => {

    if (info.menuItemId === "factCheckSelection") {

      const selectedText = info.selectionText || "";

      chrome.storage.local.set({
        lastClaim: selectedText
      });

      chrome.action.openPopup();
    }

  });

} else {

  console.error("contextMenus API not available");

}


chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

  if (request.type === "FACT_CHECK") {

    checkFact(request.claim)
      .then(result => sendResponse(result))
      .catch(() => sendResponse({
        verdict: "Error",
        explanation: "Fact check failed."
      }));

    return true; // Required for async
  }
});


async function checkFact(claim) {
  const response = await fetch("http://127.0.0.1:9000/api/fact-check/search", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      claim: claim
    })
  });

  const data = await response.json();

  return {
    verdict: data.final_verdict ?? "unverifiable",
    explanation: data.summary ?? "",
    score: typeof data.agreement_score === "number" ? data.agreement_score : 0,
  };
}
