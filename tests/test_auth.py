import sys
import os
from dotenv import load_dotenv

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.auth import AuthManager

def test_auth():
    load_dotenv()
    
    print("Testing Authentication...")
    
    # Sanity check env vars
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    tenant_id = os.getenv("TENANT_ID")
    
    print(f"CLIENT_ID loaded: {'Yes' if client_id else 'No'} (Len: {len(client_id) if client_id else 0})")
    print(f"CLIENT_SECRET loaded: {'Yes' if client_secret else 'No'} (Len: {len(client_secret) if client_secret else 0})")
    print(f"TENANT_ID loaded: {'Yes' if tenant_id else 'No'} (Len: {len(tenant_id) if tenant_id else 0})")
    
    try:
        auth = AuthManager()
        token = auth.get_access_token()
        if token:
            print("Successfully acquired access token!")
            print(f"Token type: {type(token)}")
            # print(f"Token: {token[:20]}...") 
        else:
            print("Failed to acquire token (None returned).")
    except Exception as e:
        print(f"Authentication failed with error: {e}")

if __name__ == "__main__":
    test_auth()
