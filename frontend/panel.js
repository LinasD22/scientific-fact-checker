(function () {
  const existing = document.getElementById("factCheckerContainer");
  if (existing) existing.remove();
  injectPanel();
})();

function injectPanel() {
  const container = document.createElement("div");
  container.id = "factCheckerContainer";

  const iframe = document.createElement("iframe");
  iframe.id = "factCheckerIframe";
  iframe.src = chrome.runtime.getURL("popup.html");
  // Set a transparent background for the iframe to prevent white flashes
  iframe.style.background = "transparent";

  container.appendChild(iframe);
  document.body.appendChild(container);

  const style = document.createElement("style");
  style.textContent = `
    #factCheckerContainer {
      position: fixed;
      top: 20px;
      right: 20px;
      width: 360px;
      height: 200px; /* Initial small height */
      z-index: 2147483647;
      background: white;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 10px 25px rgba(0,0,0,0.2);
      border: 1px solid #e2e8f0;
      transition: height 0.3s ease-in-out; 
    }
    #factCheckerIframe {
      width: 100%;
      height: 100%;
      border: none;
      display: block;
    }
  `;
  document.head.appendChild(style);

  window.addEventListener("message", (event) => {
    if (event.data?.type === "CLOSE_PANEL") {
      container.remove();
    }
    if (event.data?.type === "RESIZE_PANEL") {
      // Add a 10px buffer to prevent accidental scrollbars
      container.style.height = (event.data.height + 10) + "px";
    }
  });
}
