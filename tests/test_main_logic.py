import unittest
from unittest.mock import MagicMock
import logging
from src.graph import GraphClient
from src.llm import LLMProcessor
# Import process_emails from main. We might need to adjust import if main is not a module, 
# but since I wrote it as main.py in root, I can import it if I add root to path.
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import process_emails, get_folder_name_for_category

class TestMainLogic(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GraphClient)
        self.mock_llm = MagicMock(spec=LLMProcessor)
        self.config = {
            "categories": [
                {"name": "DIA", "folder_name": "Inbox/DIA"},
                {"name": "Social", "folder_name": "Inbox/Social"}
            ]
        }
        self.target_email = "test@example.com"
        
        # Setup common email return
        self.mock_email = {
            "id": "msg123",
            "subject": "Test Subject",
            "body": {"content": "Test Body"},
            "hasAttachments": False
        }
        self.mock_client.get_unread_emails.return_value = [self.mock_email]

    def test_categorized_and_actionable(self):
        # Setup LLM return
        self.mock_llm.analyze_email.return_value = {
            "category": "DIA",
            "is_actionable": True,
            "task_title": "Review PhD",
            "summary": "Summary"
        }
        
        process_emails(self.mock_client, self.mock_llm, self.config, self.target_email)
        
        # Verify Move
        self.mock_client.move_email.assert_called_with(self.target_email, "msg123", "Inbox/DIA")
        
        # Verify Task Creation
        self.mock_client.create_todo_task.assert_called_with(
            self.target_email, 
            "Review PhD", 
            "Source Email: Test Subject\nSummary: Summary", 
            list_name="Inbox/DIA"
        )

    def test_uncategorized_null(self):
        self.mock_llm.analyze_email.return_value = {
            "category": None,
            "is_actionable": False
        }
        
        process_emails(self.mock_client, self.mock_llm, self.config, self.target_email)
        
        # Verify No Move
        self.mock_client.move_email.assert_not_called()
        self.mock_client.create_todo_task.assert_not_called()

    def test_uncategorized_actionable(self):
        self.mock_llm.analyze_email.return_value = {
            "category": None,
            "is_actionable": True,
            "task_title": "General Task",
            "summary": "Summary"
        }
        
        process_emails(self.mock_client, self.mock_llm, self.config, self.target_email)
        
        # Verify No Move
        self.mock_client.move_email.assert_not_called()
        
        # Verify Task (Default list)
        self.mock_client.create_todo_task.assert_called_with(
            self.target_email, 
            "General Task", 
            "Source Email: Test Subject\nSummary: Summary", 
            list_name=None
        )

    def test_categorized_not_actionable(self):
        self.mock_llm.analyze_email.return_value = {
            "category": "Social",
            "is_actionable": False
        }
        
        process_emails(self.mock_client, self.mock_llm, self.config, self.target_email)
        
        # Verify Move
        self.mock_client.move_email.assert_called_with(self.target_email, "msg123", "Inbox/Social")
        
        # Verify No Task
        self.mock_client.create_todo_task.assert_not_called()

if __name__ == '__main__':
    unittest.main()
