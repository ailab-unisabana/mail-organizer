from dotenv import load_dotenv
import os

load_dotenv()
print("GROQ_API_KEY present:", "GROQ_API_KEY" in os.environ)
print("GOOGLE_API_KEY present:", "GOOGLE_API_KEY" in os.environ)
