import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.graph import GraphClient

class TestGraphTodo(unittest.TestCase):
    def setUp(self):
        self.mock_auth = MagicMock()
        self.mock_auth.get_access_token.return_value = "fake_token"
        self.client = GraphClient(self.mock_auth)

    @patch('src.graph.requests.get')
    @patch('src.graph.requests.post')
    def test_create_todo_task_success(self, mock_post, mock_get):
        # 1. Mock GET lists response
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = {
            "value": [
                {"id": "list_123", "displayName": "Tasks", "wellknownListName": "default"},
                {"id": "list_456", "displayName": "Groceries"}
            ]
        }
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp
        
        # 2. Mock POST task response
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"id": "task_999", "title": "Test Task"}
        mock_post_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_post_resp
        
        # Run
        result = self.client.create_todo_task("user@test.com", "Test Task", "Do it")
        
        # Verify
        self.assertIsNotNone(result)
        self.assertEqual(result['id'], "task_999")
        
        # Check GET called correctly
        mock_get.assert_called_with(
            "https://graph.microsoft.com/v1.0/users/user@test.com/todo/lists",
            headers=self.client._get_headers()
        )
        
        # Check POST called with correct URL (using ID list_123)
        mock_post.assert_called_with(
            "https://graph.microsoft.com/v1.0/users/user@test.com/todo/lists/list_123/tasks",
            headers=self.client._get_headers(),
            json={
                "title": "Test Task", 
                "body": {"content": "Do it", "contentType": "text"}
            }
        )

if __name__ == '__main__':
    unittest.main()
