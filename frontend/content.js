/**
 * content.js (Most Robust Version)
 *
 * This version correctly combines a stable toggle button with a MutationObserver
 * to handle dynamically loaded content without corrupting the state.
 */

// --- State Management ---
let isRewrittenView = true;
let originalTexts = {};
let rewrittenTexts = {};
let textNodeWrappers = [];
let observer;

// --- Core UI Functions ---

function injectAnimationStyles() {
  const styleId = "rewriter-animation-styles";
  if (document.getElementById(styleId)) return;
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `
    .rewriter-text-wrapper { transition: opacity 0.2s ease-in-out; }
    .rewriter-text-wrapper.fade-out { opacity: 0; }
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

function applyText(textMap) {
  // This function now correctly uses the complete textNodeWrappers array
  textNodeWrappers.forEach((span, index) => {
    if (textMap[index] && span.firstChild) {
      span.firstChild.nodeValue = textMap[index];
    }
  });
}

function toggleTextView() {
  const button = document.getElementById("rewriter-toggle-button");
  if (!button) return;

  isRewrittenView = !isRewrittenView;
  const targetTextMap = isRewrittenView ? rewrittenTexts : originalTexts;

  textNodeWrappers.forEach((span) => span.classList.add("fade-out"));
  setTimeout(() => {
    applyText(targetTextMap);
    textNodeWrappers.forEach((span) => span.classList.remove("fade-out"));
  }, 200);

  button.textContent = isRewrittenView
    ? "View Original ✨"
    : "View Rewritten 📝";
}

// --- Text Extraction and Processing ---

function processNodeFragment(rootNode) {
  // This function finds and wraps text nodes within a given node or fragment.
  // It returns a map of NEWLY found text to be sent to the background.
  const newTexts = {};
  const newWrappers = [];

  const treeWalker = document.createTreeWalker(
    rootNode,
    NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
  );
  const nodesToProcess = [];
  while (treeWalker.nextNode()) {
    nodesToProcess.push(treeWalker.currentNode);
  }

  nodesToProcess.forEach((currentNode) => {
    if (currentNode.shadowRoot) {
      const nestedNewTexts = processNodeFragment(currentNode.shadowRoot);
      Object.assign(newTexts, nestedNewTexts);
    }

    if (currentNode.nodeType === Node.TEXT_NODE) {
      const parent = currentNode.parentNode;
      if (
        currentNode.nodeValue.trim() === "" ||
        !parent ||
        parent.nodeName === "SCRIPT" ||
        parent.nodeName === "STYLE" ||
        parent.closest("[data-rewriter-ignore]") ||
        parent.closest(".rewriter-text-wrapper")
      ) {
        return;
      }

      const wrapperSpan = document.createElement("span");
      wrapperSpan.classList.add("rewriter-text-wrapper");
      parent.replaceChild(wrapperSpan, currentNode);
      wrapperSpan.appendChild(currentNode);

      // Add to the global wrappers array first to get the correct global index
      const index = textNodeWrappers.length;
      textNodeWrappers.push(wrapperSpan);

      // Then store the text with its global index
      originalTexts[index] = currentNode.nodeValue;
      newTexts[index] = currentNode.nodeValue;
    }
  });

  return newTexts;
}

// --- Main Execution Logic ---

function handleNewNodes(nodes) {
  // This function is called by the observer for dynamically added content.
  let combinedNewTexts = {};
  for (const node of nodes) {
    if (node.nodeType === Node.ELEMENT_NODE) {
      const newTexts = processNodeFragment(node);
      Object.assign(combinedNewTexts, newTexts);
    }
  }

  if (Object.keys(combinedNewTexts).length === 0) return;

  console.log(
    `%cObserver found ${Object.keys(combinedNewTexts).length} new text nodes.`,
    "color: purple; font-weight: bold;"
  );

  // Send only the new text for rewriting
  chrome.runtime
    .sendMessage({ type: "PROCESS_PAGE_TEXT", payload: combinedNewTexts })
    .then((response) => {
      if (!chrome.runtime.id) return;
      if (response && response.type === "REWRITE_TEXT_CONTENT") {
        // Add the new rewritten text to our global map
        Object.assign(rewrittenTexts, response.payload);
        // Apply the complete, updated rewritten text map
        if (isRewrittenView) {
          applyText(rewrittenTexts);
        }
      }
    });
}

function initialize() {
  if (window.hasRun) return;
  window.hasRun = true;

  console.log("Content: Initializing robust script.");
  injectAnimationStyles();

  // 1. Perform the initial, full-page scan.
  const initialTexts = processNodeFragment(document.body);

  if (Object.keys(initialTexts).length === 0) {
    console.log("Content: No initial text found.");
  } else {
    // 2. Send the initial text to be rewritten.
    chrome.runtime
      .sendMessage({ type: "PROCESS_PAGE_TEXT", payload: initialTexts })
      .then((response) => {
        if (!chrome.runtime.id) return;
        if (response && response.type === "REWRITE_TEXT_CONTENT") {
          // Populate the global rewrittenTexts map
          rewrittenTexts = response.payload;
          for (const key in originalTexts) {
            if (!rewrittenTexts[key]) {
              rewrittenTexts[key] = originalTexts[key];
            }
          }
          applyText(rewrittenTexts);
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

// ---------- Helper to extract parent block element ----------
function getParentBlockElement(node) {
  const blockElements = ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'DIV', 'ARTICLE', 'SECTION', 'BLOCKQUOTE', 'LI', 'DD', 'DT'];
  
  let current = node;
  while (current && current.nodeType !== Node.DOCUMENT_NODE) {
    if (current.nodeType === Node.ELEMENT_NODE && blockElements.includes(current.tagName)) {
      return current;
    }
    current = current.parentNode;
  }
  return null;
}

// // ---------- Get current visible block for dwell events ----------
// function getCurrentBlock() {
//   const blocks = document.querySelectorAll("p");  // Focus only on paragraphs
//   const visibleBlocks = [];
//   let totalText = "";
//   const maxBlocks = 2; // Maximum number of paragraphs to combine
//   const minTextLength = 50; // Minimum text length for substantial content
  
//   for (const el of blocks) {
//     const rect = el.getBoundingClientRect();
//     // Only 100% visible paragraphs - must be completely within viewport
//     const isCompletelyVisible = rect.top >= 0 && rect.bottom <= window.innerHeight;
//     const hasSubstantialText = el.innerText.trim().length >= minTextLength;
    
//     if (isCompletelyVisible && hasSubstantialText) {
//       visibleBlocks.push(el.innerText.trim());
//       totalText += el.innerText.trim() + " ";
      
//       // If we reached max blocks, break
//       if (visibleBlocks.length >= maxBlocks) {
//         break;
//       }
//     }
//   }
  
//   return totalText.trim();
// }

// // ---------- Send dwell event when reading is detected ----------
// function sendDwellEvent() {
//   const currentBlock = getCurrentBlock();
//   console.log("Current block:", currentBlock);
//   if (currentBlock) {
//     chrome.runtime.sendMessage({
//       type: "API_DWELL_REQUEST",
//       payload: {
//         context: currentBlock
//       }
//     });
//   }
// }

// ---------- Function to send text to localhost rephrase endpoint ----------
async function rephraseText(selectedText, parentContext) {
  try {
    const response = await fetch('http://localhost:8000/rephrase', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        selectedText: selectedText,
        parentContext: parentContext
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    return data.rephrasedText || selectedText;
  } catch (error) {
    console.error('Error calling rephrase endpoint:', error);
    return selectedText; // Return original text if API fails
  }
}

// ---------- New selection-replacement helper ----------
function replaceSelectionWith(text) {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;

  // Special-case <input>/<textarea>
  const active = document.activeElement;
  if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
    // For form fields, just replace the value (coloring not possible here)
    const { selectionStart: s, selectionEnd: e, value } = active;
    if (s !== null && e !== null && s !== e) {
      active.value = value.slice(0, s) + text + value.slice(e);
    }
    return;
  }

  // For generic content, replace the selection with a colored span
  const range = sel.getRangeAt(0);
  range.deleteContents();

  // Create a <span> to wrap the text and set its color
  const span = document.createElement("span");
  span.textContent = text;
  span.style.color = "brown"; // Set your desired color here (blue as example)

  // Insert the colored span at the selection
  range.insertNode(span);
  sel.removeAllRanges();
}

// ---------- Enhanced selection replacement with parent context ----------
async function replaceSelectionWithRephrase() {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
    console.log('No text selected');
    return;
  }

  const selectedText = sel.toString().trim();
  if (!selectedText) {
    console.log('No text selected');
    return;
  }

  // Get the parent block element
  const range = sel.getRangeAt(0);
  const startContainer = range.startContainer;
  const parentBlock = getParentBlockElement(startContainer);
  const parentContext = parentBlock ? parentBlock.textContent.trim() : '';

  console.log('Selected text:', selectedText);
  console.log('Parent context:', parentContext);

  // Call the rephrase API
  const rephrasedText = await rephraseText(selectedText, parentContext);
  
  // Replace the selection with the rephrased text
  replaceSelectionWith(rephrasedText);
}

// ---------- Listen for the message from the background ----------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log("Content: Message received", msg, "from", sender);
  if (msg.type === "REPLACE_SELECTION") {
    // Use the new rephrase function instead of simple replacement
    replaceSelectionWithRephrase().then(() => {
      sendResponse({ status: "ok" });
    }).catch((error) => {
      console.error('Error in replaceSelectionWithRephrase:', error);
      sendResponse({ status: "error", message: error.message });
    });
    return true; // Indicates async response
  }
  
  // if (msg.type === "DWELL_EVENT_TRIGGERED") {
  //   // Send dwell event when background detects user has been reading
  //   sendDwellEvent();
  //   sendResponse({ status: "ok" });
  // }
});
// --- Script Entry Point ---
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initialize);
} else {
  initialize();
}
