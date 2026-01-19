import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.graph import GraphClient

class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self.mock_auth = MagicMock()
        self.mock_auth.get_access_token.return_value = "fake_token"
        self.client = GraphClient(self.mock_auth)
        self.user_email = "test@example.com"
        self.list_id = "fake_list_id"

    @patch('src.graph.requests')
    def test_duplicate_task_detection(self, mock_requests):
        # Setup mocks
        # Mocking list retrieval
        mock_list_resp = MagicMock()
        mock_list_resp.json.return_value = {'value': [{'wellknownListName': 'default', 'id': self.list_id}]}
        
        # Mocking task check - RETURN A DUPLICATE
        mock_tasks_resp = MagicMock()
        mock_tasks_resp.json.return_value = {
            'value': [
                {'id': 'existing_task_id', 'body': {'content': 'Some content\n\nMetadata:\nMessageID: 12345'}}
            ]
        }
        
        # Configure side_effect for requests.get
        def side_effect_get(url, headers, params=None):
            if '/todo/lists' in url and '/tasks' not in url:
                return mock_list_resp
            if '/tasks' in url:
                return mock_tasks_resp
            return MagicMock() # Fallback

        mock_requests.get.side_effect = side_effect_get
        
        # ACT
        result = self.client.create_todo_task(
            self.user_email, 
            "Test Title", 
            "Test Content", 
            message_id="12345"
        )
        
        # ASSERT
        # Should return the existing task
        self.assertEqual(result['id'], 'existing_task_id')
        # requests.post should NOT have been called to create a task
        mock_requests.post.assert_not_called()

    @patch('src.graph.requests')
    def test_new_task_creation(self, mock_requests):
        # Setup mocks
        # Mocking list retrieval
        mock_list_resp = MagicMock()
        mock_list_resp.json.return_value = {'value': [{'wellknownListName': 'default', 'id': self.list_id}]}
        
        # Mocking task check - RETURN EMPTY (No duplicates)
        mock_tasks_resp = MagicMock()
        mock_tasks_resp.json.return_value = {'value': []}
        
        # Mocking task creation response
        mock_create_resp = MagicMock()
        mock_create_resp.json.return_value = {'id': 'new_task_id', 'title': 'Test Title'}
        
        def side_effect_get(url, headers, params=None):
            if '/todo/lists' in url and '/tasks' not in url:
                return mock_list_resp
            if '/tasks' in url:
                return mock_tasks_resp
            return MagicMock()

        mock_requests.get.side_effect = side_effect_get
        mock_requests.post.return_value = mock_create_resp
        
        # ACT
        result = self.client.create_todo_task(
            self.user_email, 
            "Test Title", 
            "Test Content", 
            message_id="67890"
        )
        
        # ASSERT
        self.assertEqual(result['id'], 'new_task_id')
        mock_requests.post.assert_called_once()
        
        # Check payload contained metadata
        args, kwargs = mock_requests.post.call_args
        payload = kwargs['json']
        self.assertIn("Metadata:\nMessageID: 67890", payload['body']['content'])

if __name__ == '__main__':
    unittest.main()
