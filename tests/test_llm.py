import sys
import os
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm import LLMProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_llm_analysis():
    load_dotenv()
    
    # Check API Key
    if not os.getenv("GROQ_API_KEY") or not os.getenv("GOOGLE_API_KEY"):
        logger.error("GROQ_API_KEY or GOOGLE_API_KEY not set")
        return

    logger.info("Testing LLM Analysis (Groq + Gemini)...")
    
    # Mock Email Content
    subject = "Urgent: Project Deadline Extended"
    body = """
    Hi Miguel,
    
    Just wanted to let you know that the deadline for the 'Mail Organizer' project has been extended to next Friday.
    
    Please update the roadmap and send me a confirmation.
    
    Thanks,
    Boss
    """
    
    # Mock Image (1x1 Red Pixel)
    mock_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    mock_attachments = [{
        "name": "test_image.png",
        "contentDetails": mock_image_b64,
        "contentType": "image/png"
    }]

    try:
        mock_config = {
             "categories": [{"name": "Work", "description": "Work stuff"}],
             "llm_instructions": ["You are a helper."]
        }
        processor = LLMProcessor(mock_config)
        # Pass mock attachments
        result = processor.analyze_email(subject, body, image_data_list=mock_attachments)
        
        logger.info("Analysis Result:")
        logger.info(result)
        
        # Validation
        if result.get("category") == "Work" and result.get("is_actionable"):
             logger.info("PASS: Classification Correct")
        else:
             logger.warning("WARN: Classification might be unexpected (check output)")
             
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    test_llm_analysis()
