import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.server import app, processors

class TestRenewEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Setup mock processors
        self.mock_graph_client = MagicMock()
        processors["graph_client"] = self.mock_graph_client
        processors["target_email"] = "test@example.com"
        
        # Set env var for test
        os.environ["CLIENT_STATE"] = "test_secret"

    def tearDown(self):
        if "CLIENT_STATE" in os.environ:
            del os.environ["CLIENT_STATE"]

    def test_renew_success(self):
        # Mock renewal result
        self.mock_graph_client.renew_all_subscriptions.return_value = 2
        
        # ACT: Call with correct token
        response = self.client.post("/renew?clientState=test_secret")
        
        # ASSERT
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "renewed": 2})
        self.mock_graph_client.renew_all_subscriptions.assert_called_once()

    def test_renew_unauthorized_wrong_token(self):
        # ACT: Call with wrong token
        response = self.client.post("/renew?clientState=wrong_secret")
        
        # ASSERT
        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.text)
        self.mock_graph_client.renew_all_subscriptions.assert_not_called()

    def test_renew_unauthorized_missing_token(self):
        # ACT: Call without token
        response = self.client.post("/renew")
        
        # ASSERT
        self.assertEqual(response.status_code, 401)
        self.mock_graph_client.renew_all_subscriptions.assert_not_called()

if __name__ == '__main__':
    unittest.main()
