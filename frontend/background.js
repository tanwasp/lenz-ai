/**
 * Background service worker for the Personalized Web Rewriter extension.
 *
 * This script listens for messages from the content script and orchestrates
 * the interaction with the backend LLM API.
 *
 * Responsibilities:
 * 1. Receive page content from content.js.
 * 2. Get the user's knowledge profile from storage.
 * 3. Call the backend API with the page content and user profile.
 * 4. Based on the API response, send a message back to content.js
 * to either rewrite the page or do nothing.
 */

// --- Configuration ---
// IMPORTANT: Replace this with your actual backend API endpoint.
const API_ENDPOINT = "https://your-backend-api.com/rewrite";

// --- Helper Functions ---

/**
 * Fetches the user's knowledge profile from Chrome's storage.
 * For the MVP, it returns a hardcoded profile if none is found.
 * @returns {Promise<object>} A promise that resolves to the user's knowledge profile.
 */
async function getUserKnowledgeProfile() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(["knownTopics", "learningTopics"], (result) => {
      if (result.knownTopics || result.learningTopics) {
        resolve({
          known: result.knownTopics || [],
          learning: result.learningTopics || [],
        });
      } else {
        // Default/hardcoded profile for the MVP
        resolve({
          known: ["JavaScript", "HTML", "CSS"],
          learning: ["Web Components", "Service Workers", "Chrome Extensions"],
        });
      }
    });
  });
}

/**
 * Calls the backend API to get a decision and potentially rewritten content.
 * @param {string} url - The URL of the page.
 * @param {string} contentSample - A sample of the page's text content.
 * @param {string} fullHTML - The full inner HTML of the page body.
 * @param {object} userProfile - The user's knowledge profile.
 * @returns {Promise<object>} A promise that resolves to the API's response.
 */
async function callRewriteAPI(url, contentSample, fullHTML, userProfile) {
  console.log("Background script: Calling backend API.");

  // --- MOCK API RESPONSE (FOR TESTING WITHOUT A REAL BACKEND) ---
  // To test, you can toggle between 'mockShouldRewrite' and 'mockShouldNotRewrite'.
  const MOCK_MODE = true;
  if (MOCK_MODE) {
    return new Promise((resolve) => {
      setTimeout(() => {
        // --- SIMULATE A "YES, REWRITE" RESPONSE ---
        const mockShouldRewrite = {
          shouldRewrite: true,
          rewrittenHTML: `
                        <div style="font-family: sans-serif; padding: 2em; border: 2px solid #4F46E5; background: #F0F9FF; border-radius: 8px;">
                            <h1 style="color: #4F46E5;">Page Rewritten (Mock)</h1>
                            <p>This is a <strong>mock response</strong> from the backend.</p>
                            <p>The original page content would be rewritten based on your knowledge profile:</p>
                            <ul>
                                <li><strong>Known Topics:</strong> ${userProfile.known.join(
                                  ", "
                                )}</li>
                                <li><strong>Learning Topics:</strong> ${userProfile.learning.join(
                                  ", "
                                )}</li>
                            </ul>
                            <p>This demonstrates that the full request-response cycle is working!</p>
                        </div>
                    `,
        };

        // --- SIMULATE A "NO, DO NOT REWRITE" RESPONSE ---
        const mockShouldNotRewrite = {
          shouldRewrite: false,
        };

        // Change this to test different scenarios
        resolve(mockShouldRewrite);
      }, 1500); // Simulate network delay
    });
  }
  // --- END MOCK API RESPONSE ---

  // --- REAL API CALL (when you have a backend) ---
  try {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: url,
        contentSample: contentSample,
        fullHTML: fullHTML,
        userProfile: userProfile,
      }),
    });

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Background script: Error calling backend API:", error);
    // If the API fails, we'll default to not rewriting the page.
    return { shouldRewrite: false };
  }
}

// --- Main Event Listener ---

// Listens for the 'ANALYZE_PAGE' message from the content script.
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "ANALYZE_PAGE") {
    console.log(
      "Background script: Received page content for analysis from tab",
      sender.tab.id
    );
    const { url, contentSample, fullHTML } = request.payload;

    // Use an async function to handle the asynchronous operations.
    const processPage = async () => {
      const userProfile = await getUserKnowledgeProfile();
      const apiResponse = await callRewriteAPI(
        url,
        contentSample,
        fullHTML,
        userProfile
      );

      // Get the tab ID from the sender.
      const tabId = sender.tab.id;
      if (!tabId) {
        console.error("Could not get tab ID from sender.");
        return;
      }

      if (apiResponse.shouldRewrite && apiResponse.rewrittenHTML) {
        console.log(
          "Background script: Decision is YES. Sending rewrite command."
        );
        chrome.tabs.sendMessage(tabId, {
          type: "REWRITE_CONTENT",
          payload: {
            rewrittenHTML: apiResponse.rewrittenHTML,
          },
        });
      } else {
        console.log(
          "Background script: Decision is NO. Telling content script to just show the page."
        );
        // We still send a message to ensure the content script unhides the page.
        chrome.tabs.sendMessage(tabId, { type: "SHOW_ORIGINAL_CONTENT" });
      }
    };

    processPage();

    // Return true to indicate that we will send a response asynchronously.
    return true;
  }
});
