import os
import logging
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

token = os.getenv("HUGGINGFACE_API_TOKEN")
# Qwen2-VL-7B-Instruct is the standard free multimodal model
model_id = "Qwen/Qwen2-VL-7B-Instruct"

client = InferenceClient(api_key=token)

print(f"Testing {model_id}...")

# Mock Image (1x1 Red Pixel)
mock_image_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

messages = [
    {
        "role": "user", 
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": mock_image_uri}}
        ]
    }
]

try:
    response = client.chat_completion(model=model_id, messages=messages, max_tokens=50)
    print("Response:", response.choices[0].message.content)
except Exception as e:
    print(f"ERROR: {e}")
