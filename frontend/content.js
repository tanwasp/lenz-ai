/**
 * content.js (Block-Level Rewriting)
 *
 * This version identifies and rewrites entire content blocks (e.g., <p>, <li>),
 * preserving the inner HTML structure for backend processing.
 */

// --- State Management ---
let isRewrittenView = true;
let originalBlocks = {}; // Stores original innerHTML { id: html }
let rewrittenBlocks = {}; // Stores rewritten innerHTML { id: html }
let blockCounter = 0; // Ensures unique IDs for all blocks
let observer;

// --- Core UI Functions ---

function injectAnimationStyles() {
  const styleId = "rewriter-animation-styles";
  if (document.getElementById(styleId)) return;
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `
    [data-rewriter-block-id] { transition: opacity 0.2s ease-in-out; }
    [data-rewriter-block-id].fade-out { opacity: 0; }
  `;
  document.head.appendChild(style);
}

function createToggleButton() {
  if (document.getElementById("rewriter-toggle-button")) return;

  const button = document.createElement("button");
  button.id = "rewriter-toggle-button";
  button.setAttribute("data-rewriter-ignore", "true");
  button.textContent = "View Original ✨";
  Object.assign(button.style, {
    position: "fixed",
    bottom: "20px",
    right: "20px",
    zIndex: "99999",
    padding: "12px 20px",
    backgroundColor: "#059669",
    color: "white",
    border: "none",
    borderRadius: "50px",
    cursor: "pointer",
    boxShadow: "0 5px 15px rgba(0, 0, 0, 0.2)",
    fontSize: "16px",
    fontWeight: "600",
  });
  button.addEventListener("click", toggleTextView);
  document.body.appendChild(button);
}

function applyRewrites(blockMap) {
  for (const id in blockMap) {
    const element = document.querySelector(`[data-rewriter-block-id="${id}"]`);
    if (element && element.innerHTML !== blockMap[id]) {
      element.innerHTML = blockMap[id];
    }
  }
}

function toggleTextView() {
  const button = document.getElementById("rewriter-toggle-button");
  if (!button) return;

  isRewrittenView = !isRewrittenView;
  const targetBlocks = isRewrittenView ? rewrittenBlocks : originalBlocks;

  const allBlocks = document.querySelectorAll("[data-rewriter-block-id]");
  allBlocks.forEach((el) => el.classList.add("fade-out"));

  setTimeout(() => {
    applyRewrites(targetBlocks);
    allBlocks.forEach((el) => el.classList.remove("fade-out"));
  }, 200);

  button.textContent = isRewrittenView
    ? "View Original ✨"
    : "View Rewritten 📝";
}

function processAndTagNodes(rootNode) {
  const newBlocks = {};
  const contentSelector = "p, li, h1, h2, h3, h4, h5, h6, blockquote";

  // --- Filtering Rules ---
  // Minimum number of visible characters to be considered "real" content.
  const minTextLength = 25;
  // Keywords or class names that likely indicate a UI element.
  const uiIndicators = [
    'class="nav-',
    'class="footer-',
    'class="cookie-',
    'menu="',
    "tabindex=",
    'data-label="',
    "Sorry, your browser doesn't support playback",
  ];

  const elements = rootNode.querySelectorAll(contentSelector);

  elements.forEach((el) => {
    // Check for UI indicators in the raw HTML.
    const isUIElement = uiIndicators.some((indicator) =>
      el.innerHTML.includes(indicator)
    );
    // Get the element's visible text content, stripped of tags and whitespace.
    const plainText = el.textContent.trim();
    // Get the trimmed innerHTML for the startsWith check.
    const trimmedInnerHTML = el.innerHTML.trim();

    // Combine all skip conditions.
    if (
      el.hasAttribute("data-rewriter-block-id") ||
      el.closest("[data-rewriter-ignore]") ||
      el.parentElement.closest("[data-rewriter-block-id]") ||
      trimmedInnerHTML.startsWith("<div") ||
      trimmedInnerHTML.startsWith("<a") ||
      // --- New filtering conditions ---
      isUIElement || // Skip if it contains a UI keyword.
      plainText.length < minTextLength // Skip if the visible text is too short.
    ) {
      return; // Skip the element entirely.
    }

    const id = blockCounter++;
    el.setAttribute("data-rewriter-block-id", id);

    originalBlocks[id] = el.innerHTML;
    newBlocks[id] = el.innerHTML;
  });

  return newBlocks;
}
// --- Main Execution Logic ---

function handleNewNodes(nodes) {
  // This function is called by the MutationObserver for dynamically added content.
  let combinedNewBlocks = {};
  for (const node of nodes) {
    // Ensure we only process element nodes and not text nodes at this top level.
    if (node.nodeType === Node.ELEMENT_NODE) {
      // Check the node itself if it's a content block
      if (node.matches("p, li, h1, h2, h3, h4, h5, h6, blockquote")) {
        const newBlocks = processAndTagNodes(node.parentElement); // process the parent to catch the node itself
        Object.assign(combinedNewBlocks, newBlocks);
      } else {
        // Check the children of the added node
        const newBlocks = processAndTagNodes(node);
        Object.assign(combinedNewBlocks, newBlocks);
      }
    }
  }

  if (Object.keys(combinedNewBlocks).length === 0) return;

  console.log(
    `%cObserver found ${
      Object.keys(combinedNewBlocks).length
    } new content blocks.`,
    "color: purple; font-weight: bold;"
  );

  // Send only the new blocks for rewriting.
  chrome.runtime
    .sendMessage({ type: "PROCESS_PAGE_TEXT", payload: combinedNewBlocks })
    .then((response) => {
      if (!chrome.runtime.id) return; // The context might have been invalidated.
      if (response && response.type === "REWRITE_TEXT_CONTENT") {
        Object.assign(rewrittenBlocks, response.payload);
        // If we are currently in the rewritten view, apply the new rewrites immediately.
        if (isRewrittenView) {
          applyRewrites(response.payload);
        }
      }
    });
}

function initialize() {
  if (window.hasRun) return;
  window.hasRun = true;

  console.log("Content: Initializing block-level rewrite script.");
  injectAnimationStyles();

  // 1. Perform the initial, full-page scan to find and tag content blocks.
  const initialBlocks = processAndTagNodes(document.body);

  if (Object.keys(initialBlocks).length === 0) {
    console.log("Content: No initial content blocks found.");
  } else {
    // 2. Send the initial blocks to be rewritten.
    chrome.runtime
      .sendMessage({ type: "PROCESS_PAGE_TEXT", payload: initialBlocks })
      .then((response) => {
        if (!chrome.runtime.id) return;
        if (response && response.type === "REWRITE_TEXT_CONTENT") {
          rewrittenBlocks = response.payload;
          // Ensure any blocks that weren't rewritten are still in the map.
          for (const key in originalBlocks) {
            if (!rewrittenBlocks[key]) {
              rewrittenBlocks[key] = originalBlocks[key];
            }
          }
          applyRewrites(rewrittenBlocks);
          isRewrittenView = true;
          createToggleButton();
        }
      });
  }

  // 3. Set up the observer to handle content added later.
  observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.addedNodes.length > 0) {
        handleNewNodes(mutation.addedNodes);
      }
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}

// --- Script Entry Point ---
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initialize);
} else {
  initialize();
}
