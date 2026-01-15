# Mail Organizer Agent

An intelligent email assistant that categorizes emails and creates tasks in Microsoft To Do using LLMs (Groq & Google Gemini).

## Architecture

- **Event-Driven**: Uses Microsoft Graph Webhooks to listen for new emails in real-time.
- **Categorization**: Uses Groq (Llama/Mixtral via API) to categorize emails based on `config.json`.
- **Vision**: Uses Google Gemini to analyze image attachments.
- **Task Management**: Automatically creates tasks in Microsoft To Do lists corresponding to the email category.

## Project Structure

- **`main.py`**: The entry point of the application. It orchestrates the lifecycle:
    1.  Starts the **FastAPI server** (from `src/server.py`) in a background thread.
    2.  Starts **ngrok** to create a public tunnel to your local server.
    3.  Calls `src/graph.py` to **create a Webhook Subscription** using the ngrok URL.
    4.  Keeps the application running to listen for events.

- **`src/` Directory**:
    -   **`server.py`**: A FastAPI application.
        -   **Webhook Endpoint**: Listens at `POST /webhook` for notifications from Microsoft.
        -   **Validation**: Handles the "Validation Token" handshake required by Microsoft Graph during subscription creation.
        -   **Deduplication**: Maintains a cache to ignore duplicate notifications for the same email.
        -   **Processing**: When a valid notification arrives, it triggers the email processing logic.
    -   **`graph.py`**: The Microsoft Graph API client.
        -   `create_subscription(user, url)`: Sends a POST request to Graph to start listening.
        -   `get_message(id)`: Fetches a specific email by ID.
        -   `move_email(id, folder)`: Moves emails to folders.
        -   `create_todo_task(...)`:  Creates tasks in Microsoft To Do.
    -   **`llm.py`**: Handles interactions with Large Language Models (Groq for text, Gemini for vision).
    -   **`auth.py`**: Manages Azure Active Directory authentication using `MSAL`, acquiring tokens for the application.

- **`config.json`**: Defines your email categories, LLM system prompts, and folder mappings.
- **`scripts/`**: Contains utility scripts for debugging or simpler manual tests.
- **`tests/`**: Contains unit tests to verify logic in isolation.

## Setup & Running

1.  **Install Dependencies**:
    ```bash
    uv sync
    ```

2.  **Environment Variables**:
    Create a `.env` file with:
    - `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`
    - `GROQ_API_KEY`, `GOOGLE_API_KEY`
    - `TARGET_EMAIL`

3.  **Run**:
    ```bash
    uv run main.py
    ```
    This will start an ngrok tunnel and the FastAPI server.

## Testing

Run unit tests:
```bash
uv run python -m unittest discover tests
```
