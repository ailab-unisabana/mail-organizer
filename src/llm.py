import os
import json
import logging
import base64
import io
from groq import Groq
from google import genai
from PIL import Image

logger = logging.getLogger(__name__)

class LLMProcessor:
    """
    Handles all interactions with Large Language Models (LLMs).
    
    This class orchestrates a multi-step analysis pipeline:
    1. Signature Removal: Uses a small, fast model (Groq) to clean email bodies.
    2. Image Analysis: Uses a vision-capable model (Gemini) to describe attachments.
    3. Classification & Extraction: Uses a powerful model (Groq) to categorize the email and extract tasks.
    """
    def __init__(self, config):
        """
        Initialize LLMProcessor with configuration.
        
        Args:
            config (dict): Configuration dictionary loaded from config.json. 
                           Contains categories and instruction prompts.
        """
        self.config = config
        
        # Load API Keys
        groq_api_key = os.getenv("GROQ_API_KEY")
        google_api_key = os.getenv("GOOGLE_API_KEY")

        if not groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set.")
        
        # Initialize Clients
        self.groq_client = Groq(api_key=groq_api_key)
        self.genai_client = genai.Client(api_key=google_api_key)
        
        # Model Configuration
        # 'signature_model': Lightweight model for simple text cleaning tasks.
        self.signature_model = "openai/gpt-oss-20b"
        
        # 'classification_model': Powerful model for complex reasoning and JSON extraction.
        self.classification_model = "openai/gpt-oss-120b"
        
        # 'vision_model': Multimodal model for understanding images.
        self.vision_model = "gemini-2.0-flash-lite"

    def _remove_signature_groq(self, body):
        """
        Uses a small, efficient Groq model to identify and remove the email signature.
        This reduces noise in the context window for the main analysis.
        
        Args:
            body (str): The raw email body text.
            
        Returns:
            str: The cleaned email body.
        """
        if not body:
            return ""

        system_prompt = (
            "You are an email preprocessing assistant. "
            "Your task is to identify the signature in the provided email body and remove it. "
            "Return ONLY the email body content without the signature. "
            "Do not summarize or change the tone. Just output the clean text."
        )

        try:
            response = self.groq_client.chat.completions.create(
                model=self.signature_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body}
                ],
                temperature=0.1, # Low temperature for deterministic output
                max_tokens=1024
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error removing signature: {e}")
            return body # Fallback to original body if cleanup fails

    def _describe_images_gemini(self, image_data_list):
        """
        Uses Google's Gemini Vision model to generate text descriptions for image attachments.
        These descriptions are later fed into the text-based classification model.
        
        Args:
            image_data_list: list of dicts with 'contentDetails' (base64 string) and 'name'.
            
        Returns:
            list: A list of string descriptions for each image.
        """
        descriptions = []
        if not image_data_list:
            return descriptions

        for img_data in image_data_list:
            try:
                b64_data = img_data.get('contentDetails')
                if not b64_data:
                    continue
                
                # Decode base64 to bytes and convert to PIL Image object for the API
                image_bytes = base64.b64decode(b64_data)
                image = Image.open(io.BytesIO(image_bytes))
                
                # Call Gemini API
                response = self.genai_client.models.generate_content(
                    model=self.vision_model,
                    contents=[
                        "Describe this image in detail for the purpose of email context analysis. "
                        "Focus on identifying text, people, objects, and the general mood.",
                        image
                    ]
                )
                
                desc = response.text.strip()
                descriptions.append(f"[Image: {img_data.get('name')}] Description: {desc}")
                
            except Exception as e:
                logger.error(f"Error describing image {img_data.get('name')}: {e}")
                descriptions.append(f"[Image: {img_data.get('name')}] (Error generating description)")
        
        return descriptions

    def _build_classification_prompt(self):
        """
        Constructs the system prompt for the main classification task.
        Dynamically inserts the user-defined categories and instructions from the config.
        """
        # 1. Add User Instructions
        instructions = self.config.get('llm_instructions', [])
        if isinstance(instructions, list):
            instructions_text = "\n".join(instructions)
        else:
            instructions_text = str(instructions)

        # 2. Add Category Definitions
        categories = self.config.get('categories', [])
        categories_text = "\n".join([f"- {c['name']}: {c['description']}" for c in categories])
        
        # 3. Assemble the Full Prompt
        prompt = f"""
        {instructions_text}
        
        Allowed Categories:
        {categories_text}
        
        Instructions:
        - Analyze the email content and assign it to ONE of the allowed categories.
        - If you are UNSURE or if the email does not fit any category clearly, set "category" to null. Do NOT guess.
        - Determine if the email requires a manual action/task from the user.
        
        Return ONLY valid JSON.
        Structure:
        {{
            "category": "category_name_or_null",
            "is_actionable": boolean,
            "task_title": "string or null",
            "due_date": "YYYY-MM-DD or null",
            "summary": "short summary including insight from images if relevant"
        }}
        """
        return prompt

    def analyze_email(self, subject, body, image_data_list=None):
        """
        Orchestrates the full email analysis process.
        
        Args:
            subject (str): Email subject.
            body (str): Email body.
            image_data_list (list): List of image attachments.
            
        Returns:
            dict: JSON object containing 'category', 'task_title', 'due_date', etc.
        """
        
        # 1. Clean Body (Remove Signature)
        # This improves classification accuracy by focusing on the actual message.
        cleaned_body = self._remove_signature_groq(body)
        
        # 2. Describe Images (if any)
        # Converts visual data into text context.
        image_descriptions = []
        if image_data_list:
            logger.info(f"Processing {len(image_data_list)} images with Gemini...")
            image_descriptions = self._describe_images_gemini(image_data_list)
        
        # 3. Construct Full Text Context
        images_text = "\n\n".join(image_descriptions)
        
        # TRUNCATION FIX: Limit body and images to ~15k chars to avoid token limit errors (413)
        # This is a rough safety limit for the input context.
        max_body_char = 15000
        if len(cleaned_body) > max_body_char:
            cleaned_body = cleaned_body[:max_body_char] + "\n...(truncated)..."
            
        full_content = f"Subject: {subject}\n\nBody:\n{cleaned_body}\n\nImage Descriptions:\n{images_text}"
        
        # Double check total length
        if len(full_content) > 20000:
             full_content = full_content[:20000] + "\n...(truncated total)..."

        # 4. Run Classification & Task Extraction
        system_prompt = self._build_classification_prompt()
        
        try:
            # We use JSON mode ('type': 'json_object') to ensure structured output.
            response = self.groq_client.chat.completions.create(
                model=self.classification_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_content}
                ],
                temperature=0.3, # Balanced creativity/strictness for analysis
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Error in LLM analysis: {e}", exc_info=True)
            # Return a safe fallback if LLM fails
            return {
                "category": "Important", # Safe default
                "is_actionable": False,
                "task_title": None,
                "due_date": None,
                "summary": "Error analyzing email (LLM failure)."
            }
