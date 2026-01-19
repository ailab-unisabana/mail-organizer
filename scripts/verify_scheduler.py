import requests
import sys

def check_endpoint():
    url = "https://mail-organizer-620068304120.us-central1.run.app/renew?clientState=80213725"
    print(f"Checking URL: {url}")
    try:
        response = requests.post(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Endpoint is reachable and accepted the clientState.")
        elif response.status_code == 401:
            print("FAILURE: Unauthorized (401). incorrect clientState.")
        elif response.status_code == 403:
            print("FAILURE: Forbidden (403). Cloud Run Authentication issue (Anonymous access not allowed).")
        else:
            print(f"FAILURE: Unexpected status code {response.status_code}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    check_endpoint()
