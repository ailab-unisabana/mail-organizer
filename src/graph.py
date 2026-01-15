import requests
import logging
import datetime
import os

logger = logging.getLogger(__name__)

class GraphClient:
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.base_url = "https://graph.microsoft.com/v1.0"

    def _get_headers(self):
        token = self.auth_manager.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_unread_emails(self, user_email):
        """Fetches unread emails from the Inbox."""
        endpoint = f"{self.base_url}/users/{user_email}/mailFolders/Inbox/messages"
        params = {
            "$filter": "isRead eq false",
            "$top": 10,
            "$select": "id,subject,body,from,receivedDateTime,hasAttachments",
            "$orderby": "receivedDateTime desc"
        }
        
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json().get('value', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching emails: {e}")
            if e.response is not None:
                logger.error(f"Response: {e.response.text}")
                if e.response.status_code == 401:
                    logger.error("HINT: Check Azure 'Mail.Read' permissions.")
            return []

    def get_message(self, user_email, message_id):
        """Fetches a specific message by ID."""
        endpoint = f"{self.base_url}/users/{user_email}/messages/{message_id}"
        # params same as get_unread for consistency
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
        """Moves an email to a specific folder. Creates folder if it doesn't exist."""
        # 1. Get (or create) folder ID by path
        folder_id = self._get_folder_id(user_email, folder_name)
            
        if not folder_id:
            logger.error(f"Could not find or create folder: {folder_name}")
            return False
            
        # 2. Move email
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
        Resolves a folder path (e.g. 'Inbox/Important') to an ID. 
        Creates the folder if it doesn't exist.
        """
        parts = folder_path.split('/')
        current_id = "msgfolderroot" # Top of hierarchy
        
        # If path starts with Inbox, mapping it to well-known name might be safer, 
        # but 'Inbox' usually sits at msgfolderroot too.
        # Let's iterate.
        
        for part in parts:
            found_id = self._find_child_folder(user_email, current_id, part)
            if not found_id:
                logger.info(f"Folder '{part}' not found in '{current_id}', creating...")
                found_id = self._create_child_folder(user_email, current_id, part)
                if not found_id:
                    return None
            current_id = found_id
            
        return current_id

    def _find_child_folder(self, user_email, parent_id, folder_name):
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
        Fetches the ID of a specific task list by name. Creates it if it doesn't exist.
        """
        endpoint = f"{self.base_url}/users/{user_email}/todo/lists"
        try:
            # 1. Search for existing list
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            lists = response.json().get('value', [])
            
            for lst in lists:
                if lst.get('displayName') == list_name:
                    return lst['id']
            
            # 2. Create if not found
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
        """Fetches the ID of the default To Do task list."""
        endpoint = f"{self.base_url}/users/{user_email}/todo/lists"
        try:
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            lists = response.json().get('value', [])
            
            # 1. Try to find the 'default' known list
            for lst in lists:
                if lst.get('wellknownListName') == 'default':
                    return lst['id']
            
            # 2. Fallback: Return the first list if available
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
        Creates a task in a specific list. 
        If list_name is provided, it tries to find/create that list.
        Otherwise falls back to default.
        due_date: Optional string in YYYY-MM-DD format.
        """
        list_id = None
        
        if list_name:
            list_id = self._get_or_create_task_list_id(user_email, list_name)
            
        if not list_id:
             # Fallback to default if specific list fail or not provided
            if list_name:
                logger.warning(f"Could not use list '{list_name}', falling back to default.")
            list_id = self._get_default_task_list_id(user_email)

        if not list_id:
            logger.error("Could not find a valid To Do task list.")
            return None

        # Create the task
        endpoint = f"{self.base_url}/users/{user_email}/todo/lists/{list_id}/tasks"
        payload = {
            "title": title,
            "body": {
                "content": content,
                "contentType": "text"
            }
        }
        
        if due_date:
            # Graph API expects 'dueDateTime': {'dateTime': '...', 'timeZone': '...'}
            # We append a default time (e.g., end of day or noon) or just date if supported.
            # To Do tasks usually just have a date. 
            # Format: YYYY-MM-DDT09:00:00 (Setting a morning time)
            # Actually, for 'dueDate' property of todoTask, it uses 'dateTimeTimeZone' resource type.
            # Let's try setting T12:00:00 UTC to be safe.
            payload["dueDateTime"] = {
                "dateTime": f"{due_date}T12:00:00",
                "timeZone": "UTC"
            }

            # Reminder Logic: 2 days before deadline at 9am
            try:
                due_dt_obj = datetime.datetime.strptime(due_date, "%Y-%m-%d")
                reminder_dt_obj = due_dt_obj - datetime.timedelta(days=2)
                # Set to 14:00 UTC (which is 9:00 AM UTC-5)
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
        """Fetches attachments for a specific message."""
        endpoint = f"{self.base_url}/users/{user_email}/messages/{message_id}/attachments"
        
        try:
            response = requests.get(endpoint, headers=self._get_headers())
            response.raise_for_status()
            attachments = response.json().get('value', [])
            
            # Filter for file attachments (images)
            image_attachments = []
            for att in attachments:
                if att.get('@odata.type') == '#microsoft.graph.fileAttachment':
                    if att.get('contentType', '').startswith('image/'):
                        image_attachments.append({
                            'name': att.get('name'),
                            'contentDetails': att.get('contentBytes'),
                            'contentType': att.get('contentType')
                        })
            return image_attachments
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching attachments: {e}")
            return []

    def create_subscription(self, user_email, notification_url):
        """
        Creates a subscription for new emails in the Inbox.
        notification_url: Public HTTPS URL where Graph will send notifications.
        """
        endpoint = f"{self.base_url}/subscriptions"
        
        # Expiration must be less than 3 days (4230 minutes). 
        # Making it ~2 days from now.
        expiration = (datetime.datetime.utcnow() + datetime.timedelta(days=2)).isoformat() + "Z"

        payload = {
            "changeType": "created",
            "notificationUrl": notification_url,
            "resource": f"users/{user_email}/mailFolders/Inbox/messages",
            "expirationDateTime": expiration,
            "clientState": os.getenv("CLIENT_STATE", "secretClientState") # Use env var for security
        }
        
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
        Renews an existing subscription.
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
        Fetches all current subscriptions and renews them.
        Useful for stateless renewal (e.g. Cloud Scheduler).
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
