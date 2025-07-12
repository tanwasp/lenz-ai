/**
 * Content script for the Personalized Web Rewriter extension.
 *
 * This script runs at `document_start`, meaning it executes before the
 * DOM is fully constructed. Its primary jobs are:
 * 1. To immediately hide the page body to prevent the original content from flashing.
 * 2. To extract the initial DOM content as it loads.
 * 3. To send this content to the background script for processing.
 * 4. To listen for a response from the background script and either:
 * - Replace the page with rewritten content.
 * - Unhide the page if no rewrite is necessary.
 */

// Immediately hide the body to prevent flashing of original content.
// We will unhide it later, either after rewriting or if no rewrite occurs.
document.documentElement.style.visibility = "hidden";

// A function to send the current DOM content to the background script.
const sendContentToBackground = () => {
  // We only want to send the content once.
  if (document.body && !document.body.hasAttribute("data-rewriter-processed")) {
    document.body.setAttribute("data-rewriter-processed", "true");

    const pageContent = document.body.innerText;
    const pageHTML = document.body.innerHTML;
    const pageURL = window.location.href;

    // We send a subset of the text content to the LLM to make a decision,
    // to avoid sending massive amounts of data unnecessarily.
    const contentSample = pageContent.substring(0, 2000);

    console.log("Content script: Sending content to background for analysis.");
    chrome.runtime.sendMessage({
      type: "ANALYZE_PAGE",
      payload: {
        url: pageURL,
        contentSample: contentSample,
        fullHTML: pageHTML, // Send full HTML for potential rewrite
      },
    });
  }
};

// Use a MutationObserver to detect when the body element is added to the DOM.
const observer = new MutationObserver((mutations, obs) => {
  if (document.body) {
    sendContentToBackground();
    obs.disconnect(); // Stop observing once we have the body.
  }
});

observer.observe(document.documentElement, {
  childList: true,
  subtree: true,
});

// Listen for messages from the background script.
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log(
    "Content script: Received message from background.",
    request.type
  );
  if (request.type === "REWRITE_CONTENT") {
    // Replace the entire body with the rewritten HTML.
    document.body.innerHTML = request.payload.rewrittenHTML;
    console.log("Content script: Page content has been rewritten.");
  }

  // Whether content was rewritten or not, we now show the page.
  // This ensures the page becomes visible even if the rewrite fails or isn't needed.
  document.documentElement.style.visibility = "visible";

  // Send a response to acknowledge receipt.
  sendResponse({ status: "completed" });
  return true; // Indicates an asynchronous response.
});

// As a fallback, if the DOM is already loaded when the script runs
// or the observer doesn't fire as expected, try to send content on load.
document.addEventListener("DOMContentLoaded", () => {
  sendContentToBackground();
  // The page is still hidden here. Visibility will be handled by the
  // message listener's response from the background script.
});
