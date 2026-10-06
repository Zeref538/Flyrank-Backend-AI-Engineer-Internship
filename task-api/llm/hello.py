"""Stage 0: prove a model answers, from this machine.  python llm/hello.py

Three environment variables (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL) are the only
difference between a model on your laptop and one in a datacentre.
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"], timeout=60)
res = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
)
print(res.choices[0].message.content)
