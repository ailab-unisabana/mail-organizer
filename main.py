import time
import json
import logging
import os
from dotenv import load_dotenv
from src.auth import AuthManager
from src.graph import GraphClient
from src.llm import LLMProcessor

# Configure logging
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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_folder_name_for_category(category_name, config):
    if not category_name:
        return None
    for cat in config.get('categories', []):
        if cat['name'] == category_name:
            return cat['folder_name']
    return None

def process_emails(client, llm, config, target_email, specific_message_id=None):
    emails = []
    
    if specific_message_id:
        logger.info(f"Fetching specific message ID: {specific_message_id}")
        msg = client.get_message(target_email, specific_message_id)
        if msg:
            emails = [msg]
        else:
            logger.warning(f"Message {specific_message_id} not found or error fetching.")
            return
    else:
        # Fallback to polling (optional, maybe we only want specific now)
        logger.info(f"Checking for new emails for {target_email}...")
        emails = client.get_unread_emails(target_email)
    
    if not emails:
        logger.info("No emails found to process.")
        return

    for email in emails:
        message_id = email['id']
        subject = email.get('subject', 'No Subject')
        body = email.get('body', {}).get('content', '')  # Note: graph returns HTML or Text. LLM might need text.
        # Ideally we strip HTML or use 'bodyPreview' if sufficient, but let's pass body content.
        # If body.content is HTML, LLM handles it well usually, or we can use beautifulsoup. 
        # For this implementation, we pass raw content.
        
        logger.info(f"Processing email: {subject}")
        
        # 1. Get Attachments (Images)
        image_data = []
        if email.get('hasAttachments'):
             image_data = client.get_attachments(target_email, message_id)

        # 2. Analyze
        analysis = llm.analyze_email(subject, body, image_data)
        logger.info(f"Analysis result: {analysis}")
        
        category = analysis.get('category')
        is_actionable = analysis.get('is_actionable')
        task_title = analysis.get('task_title')
        
        # 3. Handle Category & Move
        folder_name = get_folder_name_for_category(category, config)
        
        if folder_name:
            if client.move_email(target_email, message_id, folder_name):
                 logger.info(f"Moved to {folder_name}")
            else:
                 logger.error(f"Failed to move to {folder_name}")
        else:
             logger.info("No category assigned or category not found in config. Leaving in Inbox.")
             # Update variable for Task List usage (if not categorized, use default list)
             folder_name = None 

        # 4. Handle Task
        if is_actionable:
            title = task_title if task_title else f"Follow up: {subject}"
            content = f"Source Email: {subject}\nSummary: {analysis.get('summary')}"
            
            # List name corresponds to folder name (if categorized), else None (default list)
            list_name = folder_name if folder_name else None
            
            client.create_todo_task(target_email, title, content, list_name=list_name)

import uvicorn
import threading
from pyngrok import ngrok
from src.server import app, processors

def main():
    load_dotenv()
    config = load_config()
    target_email = os.getenv("TARGET_EMAIL")
    
    if not target_email:
        logger.error("TARGET_EMAIL not defined in .env")
        return

    auth_manager = AuthManager()
    client = GraphClient(auth_manager)
    llm = LLMProcessor(config)
    
    # 1. Setup Server Processors
    processors["graph_client"] = client
    processors["llm_processor"] = llm
    processors["config"] = config
    processors["target_email"] = target_email
    
    logger.info("Starting Mail Organizer (Webhook Mode)...")
    
    # 2. Start Server in Background Thread
    # We must start the server FIRST so it can handle the validation handshake.
    port = 8000
    server_thread = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "127.0.0.1", "port": port, "log_level": "info"}, daemon=True)
    server_thread.start()
    
    # Give server a moment to start
    time.sleep(2)

    # 3. Webhook Setup (Ngrok vs Production)
    webhook_url_env = os.getenv("WEBHOOK_URL")
    
    if webhook_url_env:
        # PRODUCTION MODE
        # If a URL is provided (e.g. Cloud Run URL), use it directly.
        logger.info(f"Running in PRODUCTION mode. Using provided Webhook URL: {webhook_url_env}")
        notification_url = f"{webhook_url_env}/webhook"
    else:
        # DEVELOPMENT MODE
        # Start ngrok
        try:
            public_url = ngrok.connect(port).public_url
            logger.info(f"ngrok tunnel \"{public_url}\" -> \"http://localhost:{port}\"")
            notification_url = f"{public_url}/webhook"
        except Exception as e:
            logger.error(f"Error starting ngrok: {e}")
            # In dev, we might want to stop here.
            return

    # 4. Create Subscription
    try:
        # In a real app, we should check existing subscriptions first to avoid duplicates
        # But Graph subscriptions have short lives, usually we assume clean slate or clear old ones.
        # For this prototype: Create new one.
        subscription = client.create_subscription(target_email, notification_url)
        if subscription:
            logger.info(f"Authorized and subscribed! ID: {subscription['id']}")
            
    except Exception as e:
         logger.error(f"Error creating subscription: {e}")
         # Attempt cleanup if ngrok was started?
         if not webhook_url_env:
             ngrok.kill()
         return

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if not webhook_url_env:
            ngrok.kill()

if __name__ == "__main__":
    main()
