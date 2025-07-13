# server.py
from __future__ import annotations
from typing import Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI, OpenAIError
import os, json
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# ─── internal mastery module (your previous file) ──────────────────────
import mastery

# ─── config ────────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-4o-mini"
USER   = "browser_user"                 # you may want a cookie / auth here

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

def rewrite_snips(snips: Dict[int, str],
                  weak: list[str],
                  strong: list[str]) -> Dict[int, str]:
    numbered = "\n".join(f"{i}. {t}" for i, t in snips.items())
    system_prompt = (
        "You are ReadWeaver. The user finds these topics hard: "
        f"{weak}. They are comfortable with: {strong}. "
        "Rewrite each snippet so that it is understandable to an undergraduate student and leave it be if it is already understandable"
        # "Rewrite each snippet accordingly; short, grade-8 language for weak topics, "
        # "normal technical wording for strong.\nReturn via rewrite_batch."
    )
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
    return {item["id"]: item["text"] for item in data["rewrites"]}

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

        # 3. Rewrite with mastery context
        new_snips = rewrite_snips(snips, weak, strong)
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

# ─── dwell endpoint ────────────────────────────────────────────────────────
@app.post("/dwell", response_model=DwellResp)
def log_dwell_event(req: DwellReq):
    try:
        # Log assumed mastery event for the dwell context
        mastery.add_event(USER, req.context, "assumed_mastery")
        print(f"Logged assumed mastery event for dwell context: {req.context[:100]}...")
        
        return {
            "status": "success", 
            "message": "Dwell event logged successfully"
        }
        
    except Exception as e:
        print(f"Failed to log dwell event: {e}")
        raise HTTPException(status_code=500, detail=str(e))