import os
import sys
from dotenv import load_dotenv

load_dotenv(".env")
api_key = os.getenv("GEMINI_API_KEY")

try:
    from google import genai
    client = genai.Client(api_key=api_key)
    
    print("Listing Models...")
    for model in client.models.list():
        name = model.name
        if "gemini" in name:
            print(name)
except Exception as e:
    print("Error:", e)
