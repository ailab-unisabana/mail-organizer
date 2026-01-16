import time
import json
import logging
import os
from dotenv import load_dotenv
from src.auth import AuthManager
from src.graph import GraphClient
from src.llm import LLMProcessor

# Configure logging
# Logs will be output to both the console (StreamHandler) and a file (FileHandler).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("mail_organizer.log")
    ]
)
logger = logging.getLogger(__name__)

def load_config(path="config.json"):
    """
    Loads the Application Configuration.
    Expects a JSON file defining categories, folder names, and LLM instructions.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_folder_name_for_category(category_name, config):
    """
    Maps an LLM-determined category name to the corresponding Outlook folder path.
    Example: 'Financial' -> 'Inbox/Invoices'
    """
    if not category_name:
        return None
    for cat in config.get('categories', []):
        if cat['name'] == category_name:
            return cat['folder_name']
    return None

def process_emails(client, llm, config, target_email, specific_message_id=None):
    """
    Core Business Logic: Fetches, Analyzes, and Acts on emails.
    
    This function is called by the Webhook Server (src/server.py) whenever a new email notification arrives.
    
    Args:
        client (GraphClient): Initialized Graph API client.
        llm (LLMProcessor): Initialized LLM wrapper.
        config (dict): App configuration.
        target_email (str): The user email to process.
        specific_message_id (str): ID of the specific email to process (from webhook).
    """
    emails = []
    
    # 1. Fetch Email Data
    if specific_message_id:
        logger.info(f"Fetching specific message ID: {specific_message_id}")
        msg = client.get_message(target_email, specific_message_id)
        if msg:
            emails = [msg]
        else:
            logger.warning(f"Message {specific_message_id} not found or error fetching.")
            return
    else:
        # Fallback: If no ID provided, check recent unread emails.
        # This is useful for initial testing or catching up if notifications were missed.
        logger.info(f"Checking for new emails for {target_email}...")
        emails = client.get_unread_emails(target_email)
    
    if not emails:
        logger.info("No emails found to process.")
        return

    # 2. Process Each Email
    for email in emails:
        message_id = email['id']
        subject = email.get('subject', 'No Subject')
        # We prefer the raw content. In a more advanced version, we might parse HTML to plain text.
        body = email.get('body', {}).get('content', '') 
        
        logger.info(f"Processing email: {subject}")
        
        # 3. Get Attachments (Images only)
        # We need to fetch these separately to pass to Gemini.
        image_data = []
        if email.get('hasAttachments'):
             image_data = client.get_attachments(target_email, message_id)

        # 4. LLM Analysis
        # Determine category, actionable status, tasks, and due dates.
        analysis = llm.analyze_email(subject, body, image_data)
        logger.info(f"Analysis result: {analysis}")
        
        category = analysis.get('category')
        is_actionable = analysis.get('is_actionable')
        task_title = analysis.get('task_title')
        
        # 5. Move Email
        # Based on category, find the target folder and move the email.
        folder_name = get_folder_name_for_category(category, config)
        
        if folder_name:
            if client.move_email(target_email, message_id, folder_name):
                 logger.info(f"Moved to {folder_name}")
            else:
                 logger.error(f"Failed to move to {folder_name}")
        else:
             logger.info("No category assigned or category not found in config. Leaving in Inbox.")
             # If no category, we will default any task to the default Task List.
             folder_name = None 

        # 6. Create Task (Sync to Microsoft To Do)
        if is_actionable:
            title = task_title if task_title else f"Follow up: {subject}"
            content = f"Source Email: {subject}\nSummary: {analysis.get('summary')}"
            due_date = analysis.get('due_date')
            
            # Smart List Selection:
            # If the email was categorized to "Reader/DIA", we try to put the task in a "DIA" list.
            list_name = folder_name.split('/')[-1] if folder_name else None
            
            client.create_todo_task(target_email, title, content, list_name=list_name, due_date=due_date)

import uvicorn
import threading
from pyngrok import ngrok
from src.server import app, processors

def main():
    """
    Application Entry Point.
    
    Orchestration Steps:
    1. Load environment variables & config.
    2. Initialize Service Clients (Auth, Graph, LLM).
    3. Inject dependencies into the Server module.
    4. Start the FastAPI Webhook Server in a background thread.
    5. Determine the Webhook URL (Production vs. Dev/Ngrok).
    6. Subscribe to Microsoft Graph notifications.
    7. Keep the main process running to listen for events.
    """
    load_dotenv()
    config = load_config()
    target_email = os.getenv("TARGET_EMAIL", "").strip()
    
    if not target_email:
        logger.error("TARGET_EMAIL not defined in .env")
        return

    # Initialize Services
    auth_manager = AuthManager()
    client = GraphClient(auth_manager)
    llm = LLMProcessor(config)
    
    # 1. Setup Server Processors (Manual Dependency Injection)
    processors["graph_client"] = client
    processors["llm_processor"] = llm
    processors["config"] = config
    processors["target_email"] = target_email
    
    logger.info("Starting Mail Organizer (Webhook Mode)...")
    
    # 2. Start Server in Background Thread
    # We use a background thread for uvicorn so the main thread can continue to setup ngrok and subscriptions.
    port = int(os.getenv("PORT", 8000))
    server_thread = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "0.0.0.0", "port": port, "log_level": "info"}, daemon=True)
    server_thread.start()
    
    # Give server a moment to start
    time.sleep(2)

    # 3. Webhook Setup
    # To receive notifications from Microsoft, we need a public HTTPS URL.
    webhook_url_env = os.getenv("WEBHOOK_URL", "").strip()
    
    # Check if running in Cloud Run (K_SERVICE is automatically set by Cloud Run)
    is_cloud_run = os.getenv("K_SERVICE") is not None

    if webhook_url_env:
        # PRODUCTION MODE (Cloud Run, Azure App Service, etc.)
        # The URL is fixed and provided by the environment.
        logger.info(f"Running in PRODUCTION mode. Using provided Webhook URL: {webhook_url_env}")
        notification_url = f"{webhook_url_env}/webhook"
        
    elif is_cloud_run:
        # PRODUCTION MODE but WEBHOOK_URL is missing.
        # This allows the container to start so we can get the URL, then update env vars.
        logger.warning("Running in Cloud Run but WEBHOOK_URL is NOT set. Skipping subscription creation.")
        notification_url = None
        
    else:
        # DEVELOPMENT MODE
        # Use ngrok to tunnel localhost to the internet.
        try:
            public_url = ngrok.connect(port).public_url
            logger.info(f"ngrok tunnel \"{public_url}\" -> \"http://localhost:{port}\"")
            notification_url = f"{public_url}/webhook"
        except Exception as e:
            logger.error(f"Error starting ngrok: {e}")
            # If ngrok fails in local dev, we probably want to stop. 
            # But let's keep it running just in case user wants to debug server only.
            notification_url = None

    # 4. Create Subscription
    # Tell Microsoft Graph to start sending 'created' events for the Inbox to our URL.
    if notification_url:
        # Normalize URL: Remove trailing slash if present
        notification_url = notification_url.rstrip('/')
        logger.info(f"Targeting Notification URL: {notification_url}")

        # Retry Logic: Subscription creation might fail if the app isn't reachable yet
        max_retries = 5
        base_delay = 5  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Subscription attempt {attempt}/{max_retries}...")
                subscription = client.create_subscription(target_email, notification_url)
                
                if subscription:
                    logger.info(f"Authorized and subscribed! ID: {subscription['id']}")
                    break # Success!
                
            except Exception as e:
                logger.error(f"Error creating subscription (Attempt {attempt}): {e}")
            
            if attempt < max_retries:
                delay = base_delay * attempt
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
        else:
             logger.error("Failed to create subscription after all retries. Check logs/firewall.")
    else:
        logger.info("Skipping subscription creation (no notification URL).")

    # 5. Keep Process Alive
    # usage: The background thread handles the server, the main thread just waits.
    # This loop is critical to keep the container running.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if not webhook_url_env and not is_cloud_run:
            ngrok.kill()

if __name__ == "__main__":
    main()
