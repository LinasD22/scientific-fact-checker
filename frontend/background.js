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
      .then(async (result) => {

        await storeLogEntry(request.claim, result, "success");
        sendResponse(result);

      })
      .catch(async (error) => {

        const errorResult = {
          verdict: "Error",
          explanation: "Fact check failed: " + (error?.message || "Unknown error.")
        };

        await storeLogEntry(request.claim, errorResult, "error");
        sendResponse(errorResult);

      });

    return true;
  }

});


async function checkFact(claim) {

  const API_KEY = "YOUR_KEY";

  const response = await fetch("https://api.yourAI.com/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${API_KEY}`
    },
    body: JSON.stringify({
      model: "1.0",
      input: `
      Determine if the following claim is TRUE, FALSE, or UNCERTAIN.
      Respond strictly in JSON format like:
      {
        "verdict": "...",
        "explanation": "..."
      }

      Claim: ${claim}
      `
    })
  });

  const data = await response.json();

  // Extract structured output safely
  const textOutput = data.output[0].content[0].text;

  return JSON.parse(textOutput);
}

async function storeLogEntry(claim, result, status) {

  const entry = {
    timestamp: new Date().toISOString(),
    claim: claim,
    verdict: result.verdict,
    explanation: result.explanation,
    status: status
  };

  const data = await chrome.storage.local.get("factLogs");
  const logs = data.factLogs || [];

  logs.push(entry);

  await chrome.storage.local.set({ factLogs: logs });
}