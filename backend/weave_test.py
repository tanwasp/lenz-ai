import weave
from openai import OpenAI
import os

INFERENCE_ENDPOINT = "https://api.inference.wandb.ai/v1"

print(os.getenv("WEAVE_API_KEY"))
weave.init("Lenz")

# weave inference
client = OpenAI(
    base_url=INFERENCE_ENDPOINT,

    # Get your API key from https://wandb.ai/authorize
    # api_key=os.getenv("WEAVE_API_KEY"),
    api_key=os.getenv("WEAVE_API_KEY"),

    # Required for W&B inference usage tracking
    project="tanishwasp-lenz/Lenz",
)

@weave.op()
def run_chat():
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.1-8B-Instruct",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me a joke."}
        ],
    )
    return response.choices[0].message.content

# Run and log the traced call
output = run_chat()
print(output)
