import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

try:
    client = genai.Client(api_key=api_key)
    print("Listing models accessible with your API Key...\n")
    
    # Google se available models ki list mangwana
    for model in client.models.list():
        print(f"✅ Available: {model.name}")
        
except Exception as e:
    print(f"❌ FATAL ERROR: {e}")