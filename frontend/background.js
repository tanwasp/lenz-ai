/**
 * background.js
 *
 * The service worker for the extension. It receives a map of text from the
 * content script, calls an API to process it, and sends the rewritten text back.
 */

// --- Configuration ---
// This would be your actual backend endpoint in a real application.
const API_ENDPOINT = "http://127.0.0.1:8001/rewrite";

/**
 * Mocks a backend API call to rewrite text content.
 *
 * In this mock version, it finds and replaces all occurrences of
 * "messi" (case-insensitive) with "tanish".
 *
 * @param {object} textMap - A JSON object where keys are indices and values are text strings.
 * @returns {Promise<object>} A promise that resolves to the rewritten text map.
 */
// async function getRewrittenText(textMap) {
//   console.log("Background: Mock API received text map:", textMap);

//   const rewrittenMap = {};
//   const searchRegex = /mcp/gi; // g for global, i for case-insensitive
//   const replacementText = "model context protocol";
//   let rewriteOccurred = false;

//   for (const key in textMap) {
//     if (Object.hasOwnProperty.call(textMap, key)) {
//       const originalText = textMap[key];
//       if (searchRegex.test(originalText)) {
//         rewriteOccurred = true;
//         rewrittenMap[key] = originalText.replace(searchRegex, replacementText);
//         console.log(
//           `%cBackground: Rewrote text for key ${key}`,
//           "color: green;"
//         );
//       } else {
//         // If no replacement is needed, just copy the original text.
//         rewrittenMap[key] = originalText;
//       }
//     }
//   }

//   console.log("Background: Mock API finished processing.", {
//     rewriteOccurred,
//     rewrittenMap,
//   });

//   // The final response includes the decision and the new text map.
//   return {
//     shouldRewrite: rewriteOccurred,
//     rewrittenText: rewrittenMap,
//   };
// }

async function getRewrittenText(textMap) {
  // console.log("Background: API received text map:", textMap);
  try {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ strings: textMap }),
    });

    if (!response.ok) {
      throw new Error(`API responded with status ${response.status}`);
    }
    // console.log("Background: API response received.");
    return await response.json();
  } catch (error) {
    console.error("Background: API call failed.", error);
    throw error;
  }
}

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
        console.log("Background: API response received:", apiResponse);
        // Adjust this block based on your backend's response structure
        if (apiResponse !== null && apiResponse.strings) {
          sendResponse({
            type: "REWRITE_TEXT_CONTENT",
            payload: apiResponse.strings,
          });
        } else {
          sendResponse({
            type: "NO_REWRITE_NEEDED",
          });
        }
      })
      .catch(() => {
        sendResponse({
          type: "API_ERROR",
        });
      });

    return true; // Indicates an asynchronous response.
  }
});
