#!/usr/bin/env python3
"""
Test script for the ReadWeaver FastAPI server.
This script sends sample HTML content to the server and displays the rewritten results.
"""

import requests
import json
from typing import Dict, Any

# Server configuration
SERVER_URL = "http://127.0.0.1:8000"  # Default FastAPI server URL
REWRITE_ENDPOINT = f"{SERVER_URL}/rewrite"

def test_server_health() -> bool:
    """
    Check if the server is running by hitting the root endpoint.
    Returns True if server is accessible, False otherwise.
    """
    try:
        response = requests.get(SERVER_URL, timeout=5)
        print(f"✅ Server is running (status: {response.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Server is not accessible: {e}")
        return False

def send_rewrite_request(html_content: str, url: str = "test://example.com") -> Dict[str, Any]:
    """
    Send HTML content to the /rewrite endpoint.
    
    Args:
        html_content: The HTML string to be rewritten
        url: Optional URL for logging/caching purposes
    
    Returns:
        Dictionary containing the response or error information
    """
    try:
        # Prepare the request payload
        payload = {
            "html": html_content,
            "url": url
        }
        
        # Send POST request to the rewrite endpoint
        response = requests.post(
            REWRITE_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30  # Allow time for OpenAI API calls
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json(),
                "status_code": response.status_code
            }
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "status_code": None
        }

def display_results(original_html: str, result: Dict[str, Any]) -> None:
    """
    Display the test results in a formatted way.
    
    Args:
        original_html: The original HTML that was sent
        result: The response from the server
    """
    print("\n" + "="*60)
    print("ORIGINAL HTML:")
    print("-" * 20)
    print(original_html)
    
    print("\n" + "="*60)
    if result["success"]:
        print("✅ REWRITE SUCCESSFUL!")
        print("-" * 20)
        print("REWRITTEN HTML:")
        print(result["data"]["html"])
    else:
        print("❌ REWRITE FAILED!")
        print("-" * 20)
        print(f"Status Code: {result['status_code']}")
        print(f"Error: {result['error']}")
    print("="*60)

def write_html_to_file(html_content: str, filename: str) -> None:
    """
    Write rewritten HTML to a file.
    
    Args:
        html_content: The HTML string to write
        filename: Name of the output file
    """
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"📁 Saved to {filename}")

def main():
    """
    Main function that runs the test scenarios.
    """
    print("🚀 Starting ReadWeaver Server Test")
    print("="*60)
    
    # Test 1: Check if server is running
    if not test_server_health():
        print("\n💡 Make sure to start the server first with:")
        print("   cd backend && uvicorn server:app --reload")
        return
    
    # Test 2: Simple paragraph test
    print("\n🧪 Test 1: Simple paragraph")
    simple_html = """
    <div>
        <p>The photosynthesis process involves the conversion of carbon dioxide and water into glucose and oxygen using sunlight energy captured by chlorophyll molecules in plant cells.</p>
    </div>
    """
    
    result = send_rewrite_request(simple_html, "test://simple-paragraph")
    display_results(simple_html, result)
    if result["success"]:
        write_html_to_file(result["data"]["html"], "test_simple.html")
    
    # Test 3: Complex content with multiple elements
    print("\n🧪 Test 2: Complex content")
    complex_html = open("test_quantum.html", "r").read()
    
    result = send_rewrite_request(complex_html, "test://complex-content")
    display_results(complex_html, result)
    if result["success"]:
        write_html_to_file(result["data"]["html"], "test_complex.html")
    
    # Test 4: Empty content (edge case)
    print("\n🧪 Test 3: Edge case - minimal content")
    minimal_html = "<div><p>Hi!</p></div>"
    
    result = send_rewrite_request(minimal_html, "test://minimal")
    display_results(minimal_html, result)
    if result["success"]:
        write_html_to_file(result["data"]["html"], "test_minimal.html")
    
    print("\n✨ All tests completed!")
    print("\n💡 Tips:")
    print("- The server wraps rewritten text in <span class='simplified' title='original'>")
    print("- Original text is preserved in the 'title' attribute for tooltips")
    print("- Make sure you have OPENAI_API_KEY set in your environment")

if __name__ == "__main__":
    main() 