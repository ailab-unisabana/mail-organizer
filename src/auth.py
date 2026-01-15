import os
import msal
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthManager:
    def __init__(self):
        self.client_id = os.getenv("CLIENT_ID", "").strip()
        self.client_secret = os.getenv("CLIENT_SECRET", "").strip()
        self.tenant_id = os.getenv("TENANT_ID", "").strip()
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scope = ["https://graph.microsoft.com/.default"] # For Client Credentials Flow

        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise ValueError("Missing required environment variables for Authentication.")

        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret
        )

    def get_access_token(self):
        """Acquires a token from MSAL cache or ID Provider."""
        # Check cache first
        result = self.app.acquire_token_silent(self.scope, account=None)

        if not result:
            logger.info("No suitable token in cache. Acquiring new one...")
            result = self.app.acquire_token_for_client(scopes=self.scope)

        if "access_token" in result:
            return result["access_token"]
        else:
            logger.error(f"Authentication Failure: {result.get('error')}")
            logger.error(f"Description: {result.get('error_description')}")
            logger.error(f"Full Result: {result}")
            raise Exception(f"Failed to acquire access token: {result.get('error')}")
