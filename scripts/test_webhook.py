import requests
import json

url = "http://127.0.0.1:8000/webhook"
payload = {
    "value": [
      {
        "subscriptionId": "test-sub-id",
        "resource": "Users/test@example.com/Messages/foo",
        "changeType": "created",
        "clientState": "secretClientState",
        "resourceData": {
          "id": "FAKE_MESSAGE_ID_123"
        }
      }
    ]
}

try:
    print(f"Sending POST to {url}...")
    response = requests.post(url, json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
