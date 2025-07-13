# server.py
from __future__ import annotations
from typing import Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI, OpenAIError
import os, json
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

class RewriteReq(BaseModel):
    strings: Dict[int, str]
    url: str | None = None

class RewriteResp(BaseModel):
    strings: Dict[int, str]

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
        "Rewrite each snippet accordingly; short, grade-8 language for weak topics, "
        "normal technical wording for strong.\nReturn via rewrite_batch."
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

        # 2. Query mastery (this also starts FAISS on first ever call)
        weak, strong, _ = mastery.classify(USER, phrases)

        # 3. Rewrite with mastery context
        new_snips = rewrite_snips(snips, weak, strong)

        return {"strings": new_snips}

    except (OpenAIError, Exception) as e:
        raise HTTPException(status_code=500, detail=str(e))