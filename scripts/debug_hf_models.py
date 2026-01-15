import os
import logging
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

token = os.getenv("HUGGINGFACE_API_TOKEN")
models_to_test = [
    "google/gemma-2-9b-it",
    "Qwen/Qwen2-VL-7B-Instruct"
]

client = InferenceClient(api_key=token)

for model_id in models_to_test:
    print(f"\n--- Testing {model_id} ---")
    try:
        messages = [{"role": "user", "content": "Hello! Describe yourself in one sentence."}]
        # Qwen-VL might need specific chat template, but standard often works for text-only probe
        response = client.chat_completion(model=model_id, messages=messages, max_tokens=20)
        print("Response:", response.choices[0].message.content)
    except Exception as e:
        print(f"ERROR with {model_id}: {e}")
