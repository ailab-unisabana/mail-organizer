import logging
import datetime
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn
import os
import sys

# Add root to path so we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We will inject these dependencies from main.py
# This is a simple way to share state without a complex DI framework for now.
# in a larger app we might use FastAPI's dependency injection.
processors = {
    "graph_client": None,
    "llm_processor": None,
    "config": None,
    "target_email": None
}

import time
processed_cache = {}

logger = logging.getLogger(__name__)
app = FastAPI()

def process_notification_job(notification):
    """
    Background job to process the notification.
    Microsoft sends a notification when a change happens.
    The notification contains the Resource ID (email ID) but usually just generic info.
    Best practice is to query delta, but for simplicity we can query 'unread emails' again
    or query the specific resource if provided.
    
    Notification payload example:
    {
      "value": [
        {
          "subscriptionId": "...",
          "resource": "Users/.../Messages/...",
          "changeType": "created",
          ...
        }
      ]
    }
    """
    try:
        logger.info("Processing notification in background...")
        client = processors["graph_client"]
        llm = processors["llm_processor"]
        config = processors["config"]
        target_email = processors["target_email"]
        
        if not all([client, llm, config, target_email]):
            logger.error("Processors not initialized properly.")
            return

        # Extract Resource ID (Message ID)
        # Payload shape for created message:
        # { "resourceData": { "id": "..." }, ... }
        resource_data = notification.get("resourceData", {})
        message_id = resource_data.get("id")
        
        if message_id:
            logger.info(f"Notification for specific message ID: {message_id}")
            
            # --- DEDUPLICATION LOGIC ---
            current_time = time.time()
            # 1. Clean up old cache entries (> 5 minutes aka 300s)
            keys_to_remove = [k for k, t in processed_cache.items() if current_time - t > 300]
            for k in keys_to_remove:
                del processed_cache[k]
                
            # 2. Check if already processing/processed
            if message_id in processed_cache:
                logger.info(f"Skipping duplicate processing for message ID: {message_id}")
                return
                
            # 3. Add to cache
            processed_cache[message_id] = current_time
            # ---------------------------
            
        else:
            logger.warning("Notification did not contain resourceData invalid ID.")
            # Fallback to scanning all unread? Or just ignore? 
            # In 'created' event, we expect an ID.
            return

        # Trigger the main processing logic
        from main import process_emails 
        
        # Pass specific ID to avoid reprocessing old emails
        process_emails(client, llm, config, target_email, specific_message_id=message_id)
        
    except Exception as e:
        logger.error(f"Error in background processing: {e}")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. Validation Handshake
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        logger.info("Received validation token handshake.")
        return PlainTextResponse(validation_token, status_code=200)

    # 2. Notification Handling
    try:
        payload = await request.json()
        logger.info(f"Received webhook payload: {payload}")
        
        if "value" in payload:
            for notification in payload["value"]:
                # Check for lifecycle notifications (reauthorizationRequired) can happen too
                if notification.get("userInputData"):
                   pass 

                # SECURITY: Validate clientState
                expected_state = os.getenv("CLIENT_STATE", "secretClientState")
                if notification.get("clientState") != expected_state:
                    logger.warning("Received webhook with invalid clientState. Ignoring.")
                    continue
                   
                # Enqueue job
                background_tasks.add_task(process_notification_job, notification)
                
        # Must return 202 Accepted quickly
        return Response(status_code=202)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return Response(status_code=500)

@app.post("/renew")
async def renew_subscriptions(request: Request):
    """
    Endpoint for Cloud Scheduler to trigger renewal of active subscriptions.
    Secured by CLIENT_STATE check.
    """
    # 1. Security Check
    expected_state = os.getenv("CLIENT_STATE", "secretClientState")
    # For simplicity, passing it as a query param or header. Cloud Scheduler can do OIDC, 
    # but let's use our existing shared secret in query or body for consistency with minimal effort.
    # Let's verify against 'clientState' query param.
    token = request.query_params.get("clientState")
    if token != expected_state:
        return Response(content="Unauthorized", status_code=401)
        
    # 2. Renew
    client = processors["graph_client"]
    if not client:
        return Response(content="Graph client not initialized", status_code=500)
        
    count = client.renew_all_subscriptions()
    return {"status": "success", "renewed": count}

@app.get("/")
def read_root():
    return {"status": "alive"}
