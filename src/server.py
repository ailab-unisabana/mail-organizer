import logging
import datetime
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn
import os
import sys

# Add root to path so we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We will inject these dependencies from main.py at runtime.
# This design is a simple manual dependency injection pattern. 
# It allows the server to access the initialized clients (Graph, LLM) without rebuilding them per request.
# In a production-grade heavy app, consider using FastAPI's 'Depends' system.
processors = {
    "graph_client": None,
    "llm_processor": None,
    "config": None,
    "target_email": None
}

import time
# A simple in-memory cache to prevent processing the same message ID multiple times quickly.
# Useful because webhooks can sometimes be retried by the sender.
processed_cache = {}

logger = logging.getLogger(__name__)
app = FastAPI()

def process_notification_job(notification):
    """
    Background job to process an incoming webhook notification from Microsoft Graph.
    
    This function runs asynchronously to avoid blocking the HTTP response to Microsoft.
    Microsoft expects a 202 Accepted response almost immediately (< 3 sec).
    """
    try:
        logger.info("Processing notification in background...")
        client = processors["graph_client"]
        llm = processors["llm_processor"]
        config = processors["config"]
        target_email = processors["target_email"]
        
        # Ensure dependencies are ready
        if not all([client, llm, config, target_email]):
            logger.error("Processors not initialized properly.")
            return

        # Extract Resource ID (Message ID) from the notification payload.
        # Graph API sends a 'resourceData' object containing the ID of the item that changed.
        resource_data = notification.get("resourceData", {})
        message_id = resource_data.get("id")
        
        if message_id:
            logger.info(f"Notification for specific message ID: {message_id}")
            
            # --- DEDUPLICATION LOGIC ---
            current_time = time.time()
            # 1. Clean up old cache entries (> 5 minutes aka 300s) to prevent memory leaks
            keys_to_remove = [k for k, t in processed_cache.items() if current_time - t > 300]
            for k in keys_to_remove:
                del processed_cache[k]
                
            # 2. Check if we just processed this ID
            if message_id in processed_cache:
                logger.info(f"Skipping duplicate processing for message ID: {message_id}")
                return
                
            # 3. Mark as processed
            processed_cache[message_id] = current_time
            # ---------------------------
            
        else:
            logger.warning("Notification did not contain resourceData invalid ID.")
            # If we don't get an ID, we can't efficiently act. 
            # We could scan the Inbox, but let's stick to event-driven for now.
            return

        # Trigger the main business logic
        # We import here to avoid circular dependencies during initial module load
        from main import process_emails 
        
        # Pass specific ID to the processor so it only handles this one email
        process_emails(client, llm, config, target_email, specific_message_id=message_id)
        
    except Exception as e:
        logger.error(f"Error in background processing: {e}")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    The main Webhook endpoint listening for Microsoft Graph notifications.
    
    Handles two types of requests:
    1. Validation Request: Microsoft sends a 'validationToken' query param. We must echo it back plain text.
    2. Notification Payload: A POST with a JSON body containing change events.
    """
    # 1. Validation Handshake (Happens when creating/renewing subscription)
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        logger.info("Received validation token handshake.")
        # Must return *content-type* text/plain and the token as the body
        return PlainTextResponse(validation_token, status_code=200)

    # 2. Notification Handling (Actual events)
    try:
        payload = await request.json()
        logger.info(f"Received webhook payload: {payload}")
        
        if "value" in payload:
            for notification in payload["value"]:
                # Check for lifecycle notifications (e.g., 'reauthorizationRequired')
                # For now, we only care about data changes.
                if notification.get("userInputData"):
                   pass 

                # SECURITY: Validate clientState
                # Ensure this request actually comes from our subscription by checking the shared secret.
                expected_state = os.getenv("CLIENT_STATE", "secretClientState")
                if notification.get("clientState") != expected_state:
                    logger.warning("Received webhook with invalid clientState. Ignoring.")
                    continue
                   
                # Enqueue the heavy processing job to background tasks
                background_tasks.add_task(process_notification_job, notification)
                
        # Must return 202 Accepted quickly to acknowledge receipt
        return Response(status_code=202)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return Response(status_code=500)

@app.post("/renew")
async def renew_subscriptions(request: Request):
    """
    Endpoint for Cloud Scheduler (or Cron) to trigger renewal of active subscriptions.
    Secured by checking the same CLIENT_STATE as a query parameter.
    """
    # 1. Security Check
    expected_state = os.getenv("CLIENT_STATE", "secretClientState")
    
    # We verify the request has the correct secret token
    token = request.query_params.get("clientState")
    if token != expected_state:
        return Response(content="Unauthorized", status_code=401)
        
    # 2. Perform Renewal
    client = processors["graph_client"]
    if not client:
        return Response(content="Graph client not initialized", status_code=500)
        
    count = client.renew_all_subscriptions()
    return {"status": "success", "renewed": count}

@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "alive"}
