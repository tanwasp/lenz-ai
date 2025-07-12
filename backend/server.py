# server.py
from typing import Dict, List, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup, NavigableString, Tag
from openai import OpenAI
import os, asyncio
from dotenv import load_dotenv

load_dotenv()

# ---------- CONFIG ----------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"
SIMPLIFY_LEVEL = "grade-8"        # could come from extension settings
# -----------------------------

app = FastAPI(title="ReadWeaver-backend")

class RewriteReq(BaseModel):
    strings: dict[int, str]               # raw outerHTML of the element the extension captured
    url: str                # used for caching / logging (optional)

class RewriteResp(BaseModel):
    html: str               # transformed HTML (same tag structure)

# ========== MAIN ENDPOINT ==========

@app.post("/rewrite", response_model=RewriteResp)
async def rewrite(req: RewriteReq):
    try:
        soup, leaves = parse_dom(req.html)
        # Chunk large pages – keep ≤2048 tokens per call
        original_chunks = [str(n) for n in leaves]
        rewritten_chunks = await rewrite_llm(original_chunks)
        transformed_html = refactor(soup, leaves, rewritten_chunks)
        return {"html": transformed_html}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))