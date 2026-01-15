import os
import logging
import base64
from dotenv import load_dotenv
from src.llm import LLMProcessor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestFlow")

def create_dummy_image():
    # 1x1 Red Pixel PNG Base64
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKwMIQAAAABJRU5ErkJggg=="

def main():
    load_dotenv()
    
    print("Testing Email Processing Pipeline...")
    
    try:
        # Mock Config
        mock_config = {
            "categories": [
                {"name": "Work", "description": "Work related stuff"},
                {"name": "Personal", "description": "Personal stuff"}
            ],
            "llm_instructions": [
                "You are a helpful assistant.",
                "Classify emails."
            ]
        }
        llm = LLMProcessor(mock_config)
        print("LLMProcessor initialized.")
    except Exception as e:
        print(f"Failed to initialize LLMProcessor: {e}")
        return

    # Test Data
    subject = "Meeting Update"
    body = """
    Hi Team,
    
    Please review the attached chart. We need to discuss this tomorrow.
    
    Best regards,
    
    Miguel
    Software Engineer
    Mail Organizer Inc.
    """
    
    image_data = [{
        "name": "chart.png",
        "contentDetails": create_dummy_image(),
        "contentType": "image/png"
    }]
    
    print("\n--- Input Email ---")
    print(f"Subject: {subject}")
    print(f"Body: {body.strip()}")
    print("Attachments: 1 Image")
    
    print("\n--- Processing ---")
    result = llm.analyze_email(subject, body, image_data)
    
    print("\n--- Result ---")
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
