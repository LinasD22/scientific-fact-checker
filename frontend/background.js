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

  const API_KEY = "YOUR_OPENAI_KEY"; // Replace with your key

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${API_KEY}`
    },
    body: JSON.stringify({
      model: "gpt-4.1-mini",
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
