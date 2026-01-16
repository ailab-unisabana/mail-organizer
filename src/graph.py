import requests
import logging
import datetime
import os

logger = logging.getLogger(__name__)

class GraphClient:
    """
    A client wrapper for the Microsoft Graph API.
    
    This class handles specific operations required for the email organizer:
    - Reading emails from the Inbox.
    - Moving emails between folders.
    - Creating tasks in Microsoft To Do.
    - Managing webhook subscriptions for new email notifications.
    """
    def __init__(self, auth_manager):
        """
        Initializes the GraphClient with an AuthManager instance.
        auth_manager: Instance of AuthManager (from src.auth) to handle token acquisition.
        """
        self.auth_manager = auth_manager
        self.base_url = "https://graph.microsoft.com/v1.0"

    def _get_headers(self):
        """
        Constructs the HTTP headers required for Graph API requests.
        Always fetches a fresh access token from the AuthManager.
        """
        token = self.auth_manager.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_unread_emails(self, user_email):
        """
        Fetches the 10 most recent unread emails from the user's Inbox.
        
        Args:
            user_email (str): The email address (UPN) of the target user.
            
        Returns:
            list: A list of email dictionaries containing 'id', 'subject', 'body', etc.
        """
        # API Endpoint: List messages in specific user's Inbox
        endpoint = f"{self.base_url}/users/{user_email}/mailFolders/Inbox/messages"
        
        # OData Query Parameters to filter and select data
        params = {
            "$filter": "isRead eq false", # Only get unread messages
            "$top": 10,                   # Limit to top 10 to check
            "$select": "id,subject,body,from,receivedDateTime,hasAttachments", # Select specific fields to reduce payload size
            "$orderby": "receivedDateTime desc" # Newest first
        }
        
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params)
            response.raise_for_status() # Raise error for bad HTTP status
            return response.json().get('value', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching emails: {e}")
            if e.response is not None:
                logger.error(f"Response: {e.response.text}")
                if e.response.status_code == 401:
                    logger.error("HINT: Check Azure 'Mail.Read' permissions.")
            return []

    def get_message(self, user_email, message_id):
        """
        Fetches a single specific message by its unique ID.
        Useful when processing a webhook notification that gives us a resource ID.
        """
        endpoint = f"{self.base_url}/users/{user_email}/messages/{message_id}"
        
        # Same fields as get_unread to maintain consistency in processing logic
        params = {
            "$select": "id,subject,body,from,receivedDateTime,hasAttachments"
        }
        
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching message {message_id}: {e}")
            if e.response is not None:
               logger.error(f"Response: {e.response.text}")
            return None

    def move_email(self, user_email, message_id, folder_name):
        """
        Moves an email to a specific destination folder.
        If the folder does not exist, it will be created dynamically.
        
        Args:
            user_email: The user's email address.
            message_id: The unique ID of the message to move.
            folder_name: The display name of the target folder (e.g., 'Invoices').
            
        Returns:
            bool: True if successful, False otherwise.
        """
        # 1. Resolve folder name to a Folder ID. Create it if missing.
        folder_id = self._get_folder_id(user_email, folder_name)
            
        if not folder_id:
            logger.error(f"Could not find or create folder: {folder_name}")
            return False
            
        # 2. Perform the Move action via Graph API
        endpoint = f"{self.base_url}/users/{user_email}/messages/{message_id}/move"
        payload = {"destinationId": folder_id}
        
        try:
            response = requests.post(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            logger.info(f" moved email {message_id} to {folder_name}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error moving email: {e}")
            return False

    def _get_folder_id(self, user_email, folder_path):
        """
        Helper to find the ID of a mail folder given its path (e.g., 'Inbox/Important').
        Iteratively finds or creates subfolders.
        """
        parts = folder_path.split('/')
        current_id = "msgfolderroot" # The root of the mailbox folder hierarchy
        
        # Traverse the path, one level at a time
        for part in parts:
            found_id = self._find_child_folder(user_email, current_id, part)
            if not found_id:
                logger.info(f"Folder '{part}' not found in '{current_id}', creating...")
                found_id = self._create_child_folder(user_email, current_id, part)
                if not found_id:
                    # Failed to create a necessary subfolder, abort
                    return None
            current_id = found_id
            
        return current_id

    def _find_child_folder(self, user_email, parent_id, folder_name):
        """Searches for a child folder with a specific name under a parent folder."""
        endpoint = f"{self.base_url}/users/{user_email}/mailFolders/{parent_id}/childFolders"
        params = {"$filter": f"displayName eq '{folder_name}'", "$select": "id"}
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params)
            response.raise_for_status()
            folders = response.json().get('value', [])
            if folders:
                return folders[0]['id']
            return None
        except Exception as e:
            logger.error(f"Error finding folder {folder_name}: {e}")
            return None

    def _create_child_folder(self, user_email, parent_id, folder_name):
        """Creates a new child folder under the specified parent."""
        endpoint = f"{self.base_url}/users/{user_email}/mailFolders/{parent_id}/childFolders"
        payload = {"displayName": folder_name}
        try:
            response = requests.post(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json().get('id')
        except Exception as e:
            logger.error(f"Error creating folder {folder_name}: {e}")
            return None

    def _get_or_create_task_list_id(self, user_email, list_name):
        """
        Fetches the ID of a Microsoft To Do task list. 
        If a list with 'list_name' doesn't exist, it creates one.
        """
        endpoint = f"{self.base_url}/users/{user_email}/todo/lists"
        try:
            # 1. Search existing lists
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            lists = response.json().get('value', [])
            
            for lst in lists:
                if lst.get('displayName') == list_name:
                    return lst['id']
            
            # 2. If not found, create a new list
            logger.info(f"Task list '{list_name}' not found, creating...")
            payload = {"displayName": list_name}
            response = requests.post(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json().get('id')
            
        except Exception as e:
            logger.error(f"Error getting/creating task list '{list_name}': {e}")
            if isinstance(e, requests.exceptions.RequestException) and e.response is not None and e.response.status_code == 401:
                logger.error("HINT: Ensure the App has 'Tasks.ReadWrite.All' Application Permission in Azure Portal.")
            return None

    def _get_default_task_list_id(self, user_email):
        """
        Finds the default 'Tasks' list in Microsoft To Do.
        Used as a fallback if a specific named list cannot be found or created.
        """
        endpoint = f"{self.base_url}/users/{user_email}/todo/lists"
        try:
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            lists = response.json().get('value', [])
            
            # 1. Look for the system 'default' list
            for lst in lists:
                if lst.get('wellknownListName') == 'default':
                    return lst['id']
            
            # 2. Fallback: Just return the first available list
            if lists:
                return lists[0]['id']
                
            return None
        except Exception as e:
            logger.error(f"Error fetching task lists: {e}")
            if isinstance(e, requests.exceptions.RequestException) and e.response is not None and e.response.status_code == 401:
                logger.error("HINT: Ensure the App has 'Tasks.ReadWrite.All' Application Permission in Azure Portal.")
            return None

    def create_todo_task(self, user_email, title, content, list_name=None, due_date=None):
        """
        Creates a new task in Microsoft To Do.
        
        Args:
            user_email: The user's email.
            title: The task subject.
            content: The detailed description/body of the task.
            list_name: (Optional) The name of the To Do list to add this to.
            due_date: (Optional) Due date in 'YYYY-MM-DD' format.
            
        Returns:
            dict: The created task object from the API response.
        """
        list_id = None
        
        # Determine the target list
        if list_name:
            list_id = self._get_or_create_task_list_id(user_email, list_name)
            
        if not list_id:
             # Fallback to default list if specific list retrieval failed
            if list_name:
                logger.warning(f"Could not use list '{list_name}', falling back to default.")
            list_id = self._get_default_task_list_id(user_email)

        if not list_id:
            logger.error("Could not find a valid To Do task list.")
            return None

        # Prepare Task Creation Payload
        endpoint = f"{self.base_url}/users/{user_email}/todo/lists/{list_id}/tasks"
        payload = {
            "title": title,
            "body": {
                "content": content,
                "contentType": "text"
            }
        }
        
        # Handle Due Date and Reminder
        if due_date:
            # Set the Due Date to Noon UTC (safe common ground)
            payload["dueDateTime"] = {
                "dateTime": f"{due_date}T12:00:00",
                "timeZone": "UTC"
            }

            # Reminder Logic: Set a reminder 2 days before the deadline.
            try:
                due_dt_obj = datetime.datetime.strptime(due_date, "%Y-%m-%d")
                reminder_dt_obj = due_dt_obj - datetime.timedelta(days=2)
                
                # Set reminder time to 14:00 UTC (approx. 9:00 AM EST)
                reminder_dt_obj = reminder_dt_obj.replace(hour=14, minute=0, second=0)
                
                payload["reminderDateTime"] = {
                    "dateTime": reminder_dt_obj.isoformat(),
                    "timeZone": "UTC"
                }
            except ValueError:
                logger.error(f"Invalid due_date format for reminder calculation: {due_date}")
        
        try:
            response = requests.post(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            logger.info(f"Created task: '{title}' in list (id: {list_id})")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating task: {e}")
            return None

    def get_attachments(self, user_email, message_id):
        """
        Fetches file attachments (specifically images) for a message.
        This allows the LLM to 'see' images attached to emails.
        """
        endpoint = f"{self.base_url}/users/{user_email}/messages/{message_id}/attachments"
        
        try:
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            attachments = response.json().get('value', [])
            
            # Filter solely for image file attachments
            image_attachments = []
            for att in attachments:
                if att.get('@odata.type') == '#microsoft.graph.fileAttachment':
                    if att.get('contentType', '').startswith('image/'):
                        image_attachments.append({
                            'name': att.get('name'),
                            'contentDetails': att.get('contentBytes'), # Base64 encoded content
                            'contentType': att.get('contentType')
                        })
            return image_attachments
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching attachments: {e}")
            return []

    def create_subscription(self, user_email, notification_url):
        """
        Creates a webhook subscription to listen for 'created' events in the Inbox.
        Graph API will send a POST to 'notification_url' whenever a new email arrives.
        """
        endpoint = f"{self.base_url}/subscriptions"
        
        # Subscriptions have a max lifetime (usually ~3 days). 
        # We set it to ~2 days to be safe. It must be renewed periodically.
        expiration = (datetime.datetime.utcnow() + datetime.timedelta(days=2)).isoformat() + "Z"

        client_state = os.getenv("CLIENT_STATE", "secretClientState").strip()
        
        # DEBUG LOGGING: robustly check inputs
        logger.info("--- SUBSCRIPTION DEBUG INFO ---")
        logger.info(f"Target Email: '{user_email}'")
        logger.info(f"Notification URL: '{notification_url}'")
        logger.info(f"Client State present: {bool(client_state)}")
        logger.info(f"Client State length: {len(client_state) if client_state else 0}")
        logger.info("-------------------------------")

        payload = {
            "changeType": "created",
            "notificationUrl": notification_url,
            "resource": f"users/{user_email}/mailFolders/Inbox/messages", # Listen to Inbox
            "expirationDateTime": expiration,
            "clientState": client_state, # Security token to validate webhook
            "includeResourceData": False # Explicitly disable rich notifications to avoid ExtensionError
        }
        
        logger.info(f"DEBUG: Full Payload: {payload}")
        
        try:
            response = requests.post(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            logger.info("Subscription created successfully.")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating subscription: {e}")
            if e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return None

    def renew_subscription(self, subscription_id):
        """
        Extends the expiration time of an existing subscription by another 2 days.
        """
        endpoint = f"{self.base_url}/subscriptions/{subscription_id}"
        expiration = (datetime.datetime.utcnow() + datetime.timedelta(days=2)).isoformat() + "Z"
        
        payload = {
            "expirationDateTime": expiration
        }
        
        try:
            response = requests.patch(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            logger.info(f"Subscription {subscription_id} renewed.")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error renewing subscription {subscription_id}: {e}")
            return None

    def renew_all_subscriptions(self):
        """
        Convenience method to list all active subscriptions and renew them.
        This is intended to be called by a scheduled job (e.g., Cloud Scheduler).
        """
        endpoint = f"{self.base_url}/subscriptions"
        try:
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            subs = response.json().get('value', [])
            
            renewed_count = 0
            for sub in subs:
                sub_id = sub['id']
                logger.info(f"Found existing subscription: {sub_id}, authenticating renewal...")
                if self.renew_subscription(sub_id):
                    renewed_count += 1
            
            return renewed_count
        except Exception as e:
            logger.error(f"Error listing/renewing subscriptions: {e}")
            return 0
