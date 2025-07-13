/**
 * background.js
 *
 * The service worker for the extension. It receives a map of text from the
 * content script, calls an API to process it, and sends the rewritten text back.
 */

// --- Configuration ---
console.log("[dwell] 🔄 Service-worker booted", new Date().toISOString());

// Quick sanity-check: do we actually hold the 'tabs' permission?
chrome.permissions.contains({ permissions: ["tabs"] }, (has) => {
  console.log("[dwell] 🔐 tabs permission:", has);
});
// This would be your actual backend endpoint in a real application.
// const API_ENDPOINT = "https://your-backend-api.com/rewrite-text";

/**
 * Mocks a backend API call to rewrite text content.
 *
 * In this mock version, it finds and replaces all occurrences of
 * "messi" (case-insensitive) with "tanish".
 *
 * @param {object} textMap - A JSON object where keys are indices and values are text strings.
 * @returns {Promise<object>} A promise that resolves to the rewritten text map.
 */
async function getRewrittenText(textMap) {
  console.log("Background: Mock API received text map:", textMap);

  const rewrittenMap = {};
  const searchRegex = /messi/gi; // g for global, i for case-insensitive
  const replacementText = "tanish";
  let rewriteOccurred = false;

  for (const key in textMap) {
    if (Object.hasOwnProperty.call(textMap, key)) {
      const originalText = textMap[key];
      if (searchRegex.test(originalText)) {
        rewriteOccurred = true;
        rewrittenMap[key] = originalText.replace(searchRegex, replacementText);
        console.log(
          `%cBackground: Rewrote text for key ${key}`,
          "color: green;"
        );
      } else {
        // If no replacement is needed, just copy the original text.
        rewrittenMap[key] = originalText;
      }
    }
  }

  console.log("Background: Mock API finished processing.", {
    rewriteOccurred,
    rewrittenMap,
  });

  // The final response includes the decision and the new text map.
  return {
    shouldRewrite: rewriteOccurred,
    rewrittenText: rewrittenMap,
  };
}

/* ------------------------------------------------------------------
   DWELL-TIME LOGGER – fires exactly once when a tab crosses the
   threshold; cancels if user leaves early.
   ------------------------------------------------------------------ */

// // === configuration ===
// const DWELL_THRESHOLD_MS = 5_000;                   // 45 s means "reading"
// const LOG_ENDPOINT       = "https://your-api/log";   // where to POST events

// // === runtime state ===
// let activeTabId   = null;    // id of the tab currently in focus (or null)
// let dwellTimerId  = null;    // setTimeout id for the pending "fire" (or null)
// let focusStart    = null;    // when we started counting (ms since epoch)
// let dwellIntervalId = null; // setInterval id for the countdown ticker
// let lastDwellUrl  = null;    // URL of last dwell event to prevent duplicates

// /*  Utility – clears any existing timer and state.
//     Called whenever the tab/window loses focus BEFORE threshold. */
// function cancelDwellTimer() {
//   if (dwellTimerId !== null) {
//     clearTimeout(dwellTimerId);                      // stop the scheduled fire
//     console.log("[dwell] ❌ cancelled (left too soon)");
//   }
//   if (dwellIntervalId !== null) {
//     clearInterval(dwellIntervalId);                 // stop the per-second ticker
//   }
//   dwellTimerId = null;
//   dwellIntervalId = null;
//   activeTabId  = null;
//   focusStart   = null;
// }

// /*  Utility – schedules a new timer that will fire once the user has stayed
//     for DWELL_THRESHOLD_MS. */
// function startDwellTimer(tabId) {
//   activeTabId  = tabId;                   // remember which tab we're timing
//   focusStart   = Date.now();              // note the starting clock tick

//   console.log("[dwell] ▶️ startDwellTimer", { tabId, focusStart });

//   // Schedule ONE callback in the future:
//   dwellTimerId = setTimeout(async () => {
//     // When we get here, the user has NOT switched away for ≥ threshold.
//     const { url, title } = await chrome.tabs.get(tabId);

//     // // Compose a minimal analytic payload (expand as needed):
//     // const payload = {
//     //   type: "READING_PASSAGE",
//     //   time: Date.now(),
//     //   url,
//     //   title,
//     //   dwellMs: Date.now() - focusStart,
//     // };

//     // Send message to content script to trigger dwell event
//     try {
//       await chrome.tabs.sendMessage(tabId, { type: "DWELL_EVENT_TRIGGERED" });
//       console.log("[dwell] ✅ sent dwell event to content script");
//     } catch (err) {
//       console.warn("[dwell] ⚠️ failed to send dwell event:", err);
//     }

//     // Stop the ticker – it would have expired anyway, but be explicit.
//     if (dwellIntervalId !== null) {
//       clearInterval(dwellIntervalId);
//       dwellIntervalId = null;
//     }

//     // Restart the timer to continue monitoring reading
//     console.log("[dwell] 🔄 restarting dwell timer for continuous monitoring");
//     dwellTimerId = null; // Clear the timer ID first
//     startDwellTimer(tabId); // Start a new timer cycle
//   }, DWELL_THRESHOLD_MS);

//   // Live countdown ‑ logs every second until the timer fires or is cancelled.
//   dwellIntervalId = setInterval(() => {
//     const remaining = DWELL_THRESHOLD_MS - (Date.now() - focusStart);
//     if (remaining <= 0) {
//       clearInterval(dwellIntervalId);
//       dwellIntervalId = null;
//       return;
//     }
//     console.log(`[dwell] ⏳ ${Math.ceil(remaining / 1000)}s remaining…`);
//   }, 1000);

//   console.log(
//     `[dwell] ⏱️  started (${DWELL_THRESHOLD_MS / 1000}s) for tab ${tabId}`
//   );
// }

// /* ------------------------------------------------------------------
//    EVENT WIRES
//    ------------------------------------------------------------------ */

// /*  Fires every time the user makes *any* tab in *any* window active.
//     - user clicks a different tab
//     - cmd/ctrl-tab
//     - link auto-opens & steals focus  */
// chrome.tabs.onActivated.addListener((activeInfo) => {
//   console.log("[dwell] 📌 tabs.onActivated event", activeInfo);
//   cancelDwellTimer();          // abort timing on the previous tab
//   startDwellTimer(activeInfo.tabId); // start timing this new tab
// });

// /*  Fires when window focus changes:
//     - user alt-tabs to another app → winId === chrome.windows.WINDOW_ID_NONE
//     - user returns to Chrome OR picks a different Chrome window         */
// chrome.windows.onFocusChanged.addListener(async (winId) => {
//   console.log("[dwell] 🪟 windows.onFocusChanged", winId);
//   // User left Chrome entirely → cancel pending timer.
//   if (winId === chrome.windows.WINDOW_ID_NONE) {
//     cancelDwellTimer();
//     return;
//   }

//   // User focused a Chrome window: find *its* active tab and treat that
//   // as a new activation.
//   const [tab] = await chrome.tabs.query({ windowId: winId, active: true });
//   if (chrome.runtime.lastError) {
//     console.warn("[dwell] ⚠️  tabs.query error:", chrome.runtime.lastError.message);
//   }
//   console.log("[dwell] → active tab after focus change", tab);

//   if (tab) {
//     cancelDwellTimer();        // stop any timer still running
//     startDwellTimer(tab.id);   // begin timing the newly focused tab
//   }
// });

// /*  Clean up if the tracked tab is closed before the timer fires. */
// chrome.tabs.onRemoved.addListener((tabId) => {
//   if (tabId === activeTabId) cancelDwellTimer();
// });

/**
 * Main listener for messages from content scripts.
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // *** FIX: Only process messages from the top-level frame to avoid iframes. ***
  if (sender.frameId !== 0) {
    console.log(
      `Background: Ignored message from iframe (frameId: ${sender.frameId})`
    );
    return;
  }

  if (message.type === "PROCESS_PAGE_TEXT") {
    console.log(
      `Background: Received text from top-level frame at URL: ${sender.url}`
    );

    getRewrittenText(message.payload)
      .then((apiResponse) => {
        if (apiResponse.shouldRewrite) {
          sendResponse({
            type: "REWRITE_TEXT_CONTENT",
            payload: apiResponse.rewrittenText,
          });
        } else {
          console.log(
            "Background: No instances of 'messi' found. No rewrite necessary."
          );
          sendResponse({
            type: "NO_REWRITE_NEEDED",
          });
        }
      })
      .catch((error) => {
        console.error("Background: API call failed.", error);
        sendResponse({
          type: "API_ERROR",
        });
      });

    return true; // Indicates an asynchronous response.
  }

  if (message.type === "API_DWELL_REQUEST") {
    console.log("Background: Received dwell event from content script");
    
    console.log("Background: Dwell payload received", message.payload);
    // Send dwell event to FastAPI server
    fetch("http://localhost:8000/dwell", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        context: message.payload.context,
        url: sender.url || "",
        timestamp: Date.now()
      })
    })
    .then(response => response.json())
    .then(data => {
      console.log("Background: Dwell event logged successfully", data);
      sendResponse({ status: "ok" });
    })
    .catch(error => {
      console.error("Background: Failed to log dwell event", error);
      sendResponse({ status: "error", message: error.message });
    });

    return true; // Indicates an asynchronous response.
  }
});

chrome.commands.onCommand.addListener(async (cmd) => {
  console.log("Background: onCommand fired:", cmd);
  if (cmd !== "replace-selection") return; // Ignore unrelated shortcuts

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) {
      console.warn("Background: No active tab found.");
      return;
    }

    console.log(`Background: Sending REPLACE_SELECTION to tab ${tab.id} (${tab.url})`);

    chrome.tabs.sendMessage(
      tab.id,
      { type: "REPLACE_SELECTION" }, // No hardcoded payload - let content script handle it
      (response) => {
        if (chrome.runtime.lastError) {
          console.error(
            "Background: sendMessage failed:",
            chrome.runtime.lastError.message
          );
        } else {
          console.log("Background: content script responded:", response);
        }
      }
    );
  } catch (err) {
    console.error("Background: Unexpected error in command handler.", err);
  }
});