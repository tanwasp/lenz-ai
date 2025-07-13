# server.py
from __future__ import annotations
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI, OpenAIError
import os, json
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import weave

load_dotenv()

# ─── internal mastery module (your previous file) ──────────────────────
import mastery

# ─── config ────────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-4o-mini"
USER   = "browser_user"                 # you may want a cookie / auth here

# weave inference
INFERENCE_ENDPOINT = "https://api.inference.wandb.ai/v1"

# weave inference
INFERENCE_ENDPOINT = "https://api.inference.wandb.ai/v1"

# ─── FastAPI boilerplate ───────────────────────────────────────────────
app = FastAPI(title="ReadWeaver-backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or restrict to your extension origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RewriteReq(BaseModel):
    strings: Dict[int, str]
    # url: str | None = None

class RewriteResp(BaseModel):
    strings: Dict[int, str]

class RephraseReq(BaseModel):
    selectedText: str
    parentContext: str

class RephraseResp(BaseModel):
    summary: str
    rephrasedText: str

class DwellReq(BaseModel):
    context: str
    url: str = ""
    timestamp: int

class DwellResp(BaseModel):
    status: str
    message: str

# ─── NEW: confusion logging schema ──────────────────────────────────────────

class ConfReq(BaseModel):
    concept: str

# For mastery classification
class ClassifyReq(BaseModel):
    phrases: list[str]

class ClassifyResp(BaseModel):
    weak: list[str]
    strong: list[str]
    neutral: list[str]

# ─── OpenAI tool schemas ───────────────────────────────────────────────
EXTRACT_TOOL = [
    {
      "type": "function",
      "function": {
        "name": "list_phrases",
        "description": "Return key phrases that may need mastery lookup",
        "parameters": {
          "type": "object",
          "properties": {
            "phrases": {
              "type": "array",
              "items": {"type": "string"}
            }
          },
          "required": ["phrases"]
        }
      }
    }
]

REWRITE_TOOL = [
    {
      "type": "function",
      "function": {
        "name": "rewrite_batch",
        "description": "Rewrite each snippet given the user's weak/strong topics",
        "parameters": {
          "type": "object",
          "properties": {
            "rewrites": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "id":   {"type": "integer"},
                  "text": {"type": "string"}
                },
                "required": ["id", "text"]
              }
            }
          },
          "required": ["rewrites"]
        }
      }
    }
]

# ─── helpers ───────────────────────────────────────────────────────────
@weave.op()
def openai_call(messages, tools, tool_choice="auto"):
    return client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=0.2
    )

def extract_phrases(snips: Dict[int, str]) -> list[str]:
    numbered = "\n".join(f"{i}. {t}" for i, t in snips.items())
    resp = openai_call(
        [
            {"role": "system",
             "content": "Extract key technical phrases the reader might not know."},
            {"role": "user", "content": numbered}
        ],
        tools=EXTRACT_TOOL,
        tool_choice={"type": "function", "function": {"name": "list_phrases"}}
    )
    args = resp.choices[0].message.tool_calls[0].function.arguments
    return json.loads(args)["phrases"]

# ------------------------------------------------------------------
#  Helper – rewrite snippets OR skip when nothing is relevant
# ------------------------------------------------------------------

from typing import Optional, Dict as _Dict  # local alias to avoid confusion


def rewrite_snips(
    snips: Dict[int, str],
    weak: list[str],
    strong: list[str],
) -> Optional[_Dict[int, str]]:
    """Return a rewritten map or **None** if no mastery context applies.

    • If both *weak* and *strong* are empty the function decides the database
      has no signal.  Skips the expensive LLM call and returns *None* so the
      caller can fall back to the original snippets unchanged.
    """

    # --- Early-exit: nothing to personalise ---------------------------------
    if not weak and not strong:
        print("rewrite_snips: no mastery context → returning None")
        return None

    numbered = "\n".join(f"{i}. {t}" for i, t in snips.items())
    print(f"weak: {weak}")
    print(f"strong: {strong}")
    
    system_prompt = (
        "You are ReadWeaver. The user finds these topics hard: "
        "You are ReadWeaver. The user finds these topics hard: "
        f"{weak}. They are comfortable with: {strong}. "
        "Err on the side of leaving text as it is. Only rewrite when a sentence *directly* involves a hard topic. "
        "If none of the topics provided are relevant to a snippet, return it exactly as given. "
        "When rewriting, operate at the **sentence level**: leave untouched sentences verbatim and only change the sentences that need clarification. "
        "For any sentence you change, wrap JUST THAT sentence (not the whole paragraph) in <span style='color:#8B4513'>…</span> so the UI highlights only the modified parts. Unmodified sentences must stay outside any span. "
        "Maintain the original HTML structure and tags. Do not rewrite titles or headers. "
        "Jargon → add intuitive explanation in brackets; include an example if helpful. Keep language approx. 9th-grade. "
        "If no information about user mastery is provided, or nothing is relevant, do not rewrite. "
        "Return via rewrite_batch."
    )
    # --- LLM call ---------------------------------------------------------------
    resp = openai_call(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": numbered}
        ],
        tools=REWRITE_TOOL,
        tool_choice={"type": "function", "function": {"name": "rewrite_batch"}}
    )
    data = json.loads(resp.choices[0].message.tool_calls[0]
                      .function.arguments)
    rewritten_map = {item["id"]: item["text"] for item in data["rewrites"]}

    # If nothing was rewritten (empty or identical) → treat as None
    if not rewritten_map:
        print("rewrite_snips: LLM returned empty rewrites → None")
        return None

    no_change = all(rewritten_map.get(k) == snips.get(k) for k in rewritten_map)
    if no_change:
        print("rewrite_snips: rewrites identical to originals → None")
        return None

    return rewritten_map

# ─── main endpoint ─────────────────────────────────────────────────────
@app.post("/rewrite", response_model=RewriteResp)
def rewrite(req: RewriteReq):
    try:
        snips = req.strings

        # 1. Extract phrases the model wants mastery for
        phrases = extract_phrases(snips)
        # print("phrases", phrases)

        # 2. Query mastery (this also starts FAISS on first ever call)
        weak, strong, _ = mastery.classify(USER, phrases)
        # print("weak", weak)
        # print("strong", strong)

        # 3. Rewrite with mastery context (may return None)
        new_snips = rewrite_snips(snips, weak, strong)

        if new_snips is None:
            # No relevant topics → keep original snippets unchanged
            new_snips = snips
            print("rewrite: skipped LLM rewrite – no mastery context")
        else:
            print("new_snips", new_snips)
        
        return {"strings": new_snips}

    except (OpenAIError, Exception) as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── rephrase endpoint ─────────────────────────────────────────────────
@app.post("/rephrase", response_model=RephraseResp)
def rephrase_text(req: RephraseReq):
    try:
        # Create a prompt that produces both a summary concept and a rephrase
        system_prompt = (
            "You are a helpful assistant. For the given context and selected passage, produce: \n"
            "1. summary – a SHORT concept name or key phrase (max 5 words) capturing the essence of the user's confusion/question, based on BOTH the selected text and its replacement. Don't use fillers like Understanding. The purpose is to create a vector database of concepts so name it accordingly\n"
            "2. rephrase – if possible, prefer to keep the original text and simply add a brief explanation in brackets after any jargon or unclear term. Only fully rephrase the text if this would make it much clearer than just adding brackets. Ensure the result still fits grammatically in the original context.\n\n"
            "Respond ONLY in valid JSON on a single line with keys 'summary' and 'rephrase'."
        )

        user_prompt = (
            f"Context: {req.parentContext}\n\n"
            f"Selected text: {req.selectedText}\n\n"
            "Return the JSON now."
        )
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        raw = response.choices[0].message.content.strip()
        try:
            parsed = json.loads(raw)
            summary   = parsed.get("summary", "").strip()
            rephrase  = parsed.get("rephrase", "").strip()
        except json.JSONDecodeError:
            # fallback: treat whole string as rephrase, empty summary
            summary = ""
            rephrase = raw

        # Log confusion event using summary when available, else selectedText
        concept_to_log = summary or req.selectedText
        try:
            mastery.add_event(USER, concept_to_log, "confusion")
            print(f"Logged confusion event for: {concept_to_log}")
        except Exception as e:
            print(f"Failed to log confusion event: {e}")

        return {"summary": summary, "rephrasedText": rephrase}
        
    except (OpenAIError, Exception) as e:
        raise HTTPException(status_code=500, detail=str(e))

# # ─── dwell endpoint ────────────────────────────────────────────────────────
# @app.post("/dwell", response_model=DwellResp)
# def log_dwell_event(req: DwellReq):
#     try:
#         # Log assumed mastery event for the dwell context
#         mastery.add_event(USER, req.context, "assumed_mastery")
#         print(f"Logged assumed mastery event for dwell context: {req.context[:100]}...")
        
#         return {
#             "status": "success", 
#             "message": "Dwell event logged successfully"
#         }
        
#     except Exception as e:
#         print(f"Failed to log dwell event: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# ─── confusion logging endpoint ─────────────────────────────────────────────


@app.post("/log_confusion")
def log_confusion(req: ConfReq):
    """Record a confusion signal coming from the MCP observer."""
    try:
        mastery.add_event(USER, req.concept.strip().lower(), "confusion")
        print(f"Logged confusion via HTTP: {req.concept}")
        return {"status": "ok"}
    except Exception as e:
        print(f"Failed to log confusion via HTTP: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── mastery classification endpoint ────────────────────────────────────────


@app.post("/mastery_classify", response_model=ClassifyResp)
def mastery_classify(req: ClassifyReq):
    """Return weak/strong/neutral classification for each phrase."""
    try:
        weak, strong, neutral = mastery.classify(USER, req.phrases)
        return {"weak": weak, "strong": strong, "neutral": neutral}
    except Exception as e:
        print(f"Failed to classify mastery: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
weave.init('Lenz') # 🐝
    
weave.init('Lenz') # 🐝