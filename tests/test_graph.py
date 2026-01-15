import sys
import os
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.auth import AuthManager
from src.graph import GraphClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fetch_emails():
    load_dotenv()
    target_email = os.getenv("TARGET_EMAIL")
    
    if not target_email:
        logger.error("TARGET_EMAIL not set in .env")
        return

    logger.info(f"Testing email fetch for: {target_email}")
    
    try:
        auth = AuthManager()
        client = GraphClient(auth)
        
        emails = client.get_unread_emails(target_email)
        
        logger.info(f"Successfully fetched {len(emails)} unread emails.")
        for email in emails:
            logger.info(f" - Subject: {email.get('subject')}")
            logger.info(f"   From: {email.get('from', {}).get('emailAddress', {}).get('name')}")
            logger.info(f"   ID: {email.get('id')}")

    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    test_fetch_emails()
