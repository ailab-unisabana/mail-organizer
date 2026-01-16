import os
import msal
import logging

# Configure logging for the application
# This sets the default logging level to INFO, meaning standard messages will be shown.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthManager:
    """
    Handles authentication with Microsoft Azure Active Directory (Entra ID) using the MSAL library.
    This class is responsible for acquiring and managing access tokens required to make API calls to Microsoft Graph.
    Permission flows supported: Client Credentials Flow (Application Permissions).
    """
    def __init__(self):
        """
        Initializes the AuthManager by loading credentials from environment variables.
        Expected environment variables:
        - CLIENT_ID: The Application (client) ID from Azure App Registration.
        - CLIENT_SECRET: The Client Secret value.
        - TENANT_ID: The Directory (tenant) ID.
        """
        # Load credentials from environment variables and strip any accidental whitespace
        self.client_id = os.getenv("CLIENT_ID", "").strip()
        self.client_secret = os.getenv("CLIENT_SECRET", "").strip()
        self.tenant_id = os.getenv("TENANT_ID", "").strip()

        # Construct the authority URL. This is the endpoint MSAL talks to for tokens.
        # Format: https://login.microsoftonline.com/{tenant_id}
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"

        # Define the scope. For Client Credentials Flow (Daemon app), the scope is always '.default'.
        # This tells Microsoft Identity to permit all application permissions granted in the Azure Portal.
        self.scope = ["https://graph.microsoft.com/.default"] 

        # Validate that all necessary credentials are present
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise ValueError("Missing required environment variables for Authentication.")

        # Initialize the MSAL Confidential Client Application
        # This object handles the heavy lifting of token requests and caching.
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret
        )

    def get_access_token(self):
        """
        Acquires an access token for Microsoft Graph.
        
        Strategy:
        1. Check the internal MSAL token cache for a valid existing token. (acquire_token_silent)
        2. If no valid token exists in cache, request a new one from Azure AD. (acquire_token_for_client)
        
        Returns:
            str: The access token string (JWT).
            
        Raises:
            Exception: If authentication fails.
        """
        # 1. Attempt to get a token directly from the in-memory cache
        # This avoids unnecessary processing power and network calls.
        result = self.app.acquire_token_silent(self.scope, account=None)

        if not result:
            # 2. Cache miss or token expired. Request a new token from the server.
            logger.info("No suitable token in cache. Acquiring new one...")
            result = self.app.acquire_token_for_client(scopes=self.scope)

        # Check if the result contains an access token
        if "access_token" in result:
            return result["access_token"]
        else:
            # Log detailed error information if authentication failed
            logger.error(f"Authentication Failure: {result.get('error')}")
            logger.error(f"Description: {result.get('error_description')}")
            logger.error(f"Full Result: {result}")
            raise Exception(f"Failed to acquire access token: {result.get('error')}")
