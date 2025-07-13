#!/usr/bin/env python3
"""
End-to-end test for the ReadWeaver FastAPI /rewrite endpoint
that now expects: { "strings": { "<id>": "<text>", ... }, "url": "..." }

How it works
------------
1. Parse sample HTML with BeautifulSoup.
2. Enumerate all visible text nodes → dict[str_id → text].
3. POST to /rewrite.
4. Show before/after pairs, round-trip time, and write an HTML file
   where each node was replaced so you can eyeball the result.
"""

import requests, time, pathlib, sys, json
from typing import Dict, Any
from bs4 import BeautifulSoup, NavigableString

SERVER   = "http://127.0.0.1:8000"
REWRITE  = f"{SERVER}/rewrite"
DATA_DIR = pathlib.Path(__file__).with_suffix("")      # same folder

# ────────────────────────── helpers ────────────────────────────────────
def html_to_dict(html: str) -> Dict[str, str]:
    """
    Extract every non-empty visible text node and return
    { "0": "...", "1": "...", ... } (keys must be *strings* for JSON).
    """
    soup   = BeautifulSoup(html, "lxml")
    leaves = [n for n in soup.descendants
              if isinstance(n, NavigableString) and n.strip()]
    return {str(i): n.strip() for i, n in enumerate(leaves)}

def patch_html(html: str, rewrites: Dict[str, str]) -> str:
    """
    Replace original text nodes in *document order* with rewritten text.
    """
    soup   = BeautifulSoup(html, "lxml")
    leaves = [n for n in soup.descendants
              if isinstance(n, NavigableString) and n.strip()]
    for i, node in enumerate(leaves):
        new = rewrites.get(str(i))
        if new:
            node.replace_with(new)
    return str(soup)

def call_rewrite(strings: Dict[str, str], url: str) -> Dict[str, str]:
    payload = {"strings": strings, "url": url}
    t0      = time.perf_counter()
    r       = requests.post(REWRITE, json=payload, timeout=120)
    latency = time.perf_counter() - t0

    if r.status_code != 200:
        print(f"❌ {url}: status {r.status_code} → {r.text[:200]}")
        sys.exit(1)

    print(f"✅ {url}: {len(strings)} snippets → {latency:.2f}s round-trip")
    return r.json()["strings"]

def show_diff(orig: Dict[str, str], new: Dict[str, str], max_lines=5):
    print("\nFirst few rewrites:")
    for k in list(orig)[:max_lines]:
        before = orig[k][:120]
        after  = new.get(k, "")[:120]
        print(f"[{k}] {before!r}  →  {after!r}")

# ────────────────────────── test cases ─────────────────────────────────
TESTS = [
    {
        "name": "complex-quantum",
        "file": "test_quantum.html"
    },
    {
        "name": "minimal",
        "html": "<div><p>Hi!</p></div>"
    }
]

def main():
    # Quick health-check
    try:
        requests.get(SERVER, timeout=3)
    except requests.exceptions.RequestException:
        print("🚫 Server not running – start with: uvicorn server:app --reload")
        return

    for test in TESTS:
        name = test["name"]
        html = test.get("html") or pathlib.Path(test["file"]).read_text()
        strings = html_to_dict(html)
        rewrites = call_rewrite(strings, f"test://{name}")

        show_diff(strings, rewrites)

        rewritten_html = patch_html(html, rewrites)
        out_path = DATA_DIR / f"{name}_rewritten.html"
        out_path.write_text(rewritten_html, encoding="utf-8")
        print(f"💾 saved -> {out_path}\n" + "-"*60)

if __name__ == "__main__":
    main()