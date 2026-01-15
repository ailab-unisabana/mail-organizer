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
    def __init__(self, config):
        """
        Initialize LLMProcessor with configuration.
        config: dict loaded from config.json
        """
        self.config = config
        groq_api_key = os.getenv("GROQ_API_KEY")
        google_api_key = os.getenv("GOOGLE_API_KEY")

        if not groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set.")
        
        self.groq_client = Groq(api_key=groq_api_key)
        self.genai_client = genai.Client(api_key=google_api_key)
        
        # Model Configuration
        self.signature_model = "openai/gpt-oss-20b"
        self.classification_model = "openai/gpt-oss-120b"
        self.vision_model = "gemini-2.0-flash-lite"

    def _remove_signature_groq(self, body):
        """
        Uses a small Groq model to identify and remove the email signature.
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
                temperature=0.1,
                max_tokens=1024
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error removing signature: {e}")
            return body # Fallback to original body

    def _describe_images_gemini(self, image_data_list):
        """
        Uses Gemini to describe images.
        image_data_list: list of dicts with 'contentDetails' (base64 string) and 'name'.
        """
        descriptions = []
        if not image_data_list:
            return descriptions

        for img_data in image_data_list:
            try:
                b64_data = img_data.get('contentDetails')
                if not b64_data:
                    continue
                
                # Decode base64 to bytes and convert to Image object
                image_bytes = base64.b64decode(b64_data)
                image = Image.open(io.BytesIO(image_bytes))
                
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
        Constructs the system prompt from config.
        """
        instructions = self.config.get('llm_instructions', [])
        if isinstance(instructions, list):
            instructions_text = "\n".join(instructions)
        else:
            instructions_text = str(instructions)

        categories = self.config.get('categories', [])
        categories_text = "\n".join([f"- {c['name']}: {c['description']}" for c in categories])
        
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
            "summary": "short summary including insight from images if relevant"
        }}
        """
        return prompt

    def analyze_email(self, subject, body, image_data_list=None):
        """
        Analyzes the email content using Groq (classification) and Gemini (images).
        1. Remove signature (Groq Small).
        2. Describe images (Gemini).
        3. Classify and extract tasks (Groq Large).
        """
        
        # 1. Clean Body
        cleaned_body = self._remove_signature_groq(body)
        
        # 2. Describe Images
        image_descriptions = []
        if image_data_list:
            logger.info(f"Processing {len(image_data_list)} images with Gemini...")
            image_descriptions = self._describe_images_gemini(image_data_list)
        
        # 3. Construct Full Context
        images_text = "\n\n".join(image_descriptions)
        
        # TRUNCATION FIX: Limit body and images to ~15k chars to avoid 413 errors
        # This is a rough safety limit.
        max_body_char = 15000
        if len(cleaned_body) > max_body_char:
            cleaned_body = cleaned_body[:max_body_char] + "\n...(truncated)..."
            
        full_content = f"Subject: {subject}\n\nBody:\n{cleaned_body}\n\nImage Descriptions:\n{images_text}"
        
        # Ensure total length isn't absurd
        if len(full_content) > 20000:
             full_content = full_content[:20000] + "\n...(truncated total)..."

        # 4. Classification System Prompt
        system_prompt = self._build_classification_prompt()
        
        try:
            response = self.groq_client.chat.completions.create(
                model=self.classification_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_content}
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Error in LLM analysis: {e}", exc_info=True)
            return {
                "category": "Important",
                "is_actionable": False,
                "task_title": None,
                "summary": "Error analyzing email (LLM failure)."
            }
