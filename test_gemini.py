import os
from google import genai
from dotenv import load_dotenv

# 1. Load the environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ ERROR: GEMINI_API_KEY .env file mein nahi mili!")
    exit()

print("🔌 Connecting to Google Gemini API...\n")

try:
    # 2. Initialize the Client
    client = genai.Client(api_key=api_key)
    
    # 3. Model hum pehle 2.0 try karenge, agar fail hua toh 1.5
    models_to_test = ["gemini-2.0-flash", "gemini-1.5-flash"]
    
    success = False
    for model_name in models_to_test:
        print(f"🤖 Pinging Model: {model_name}...")
        try:
            response = client.models.generate_content(
                model=model_name,
                contents="Reply with exactly this text: 'Hello Boss, your API is working 100% fine!'"
            )
            print(f"✅ CONNECTION SUCCESSFUL with {model_name}!")
            print(f"💬 AI Says: {response.text}\n")
            
            print(f"🎯 SOLUTION: Apni decision_engine.py mein model ka naam '{model_name}' daal do.")
            success = True
            break # Pehla model chal gaya toh loop break kar do
            
        except Exception as e:
            print(f"⚠️ {model_name} failed. Moving to next...\n")
            
    if not success:
        print("❌ Dono models fail ho gaye. Iska matlab tumhari API key par in models ka access nahi hai.")

except Exception as e:
    print("❌ FATAL ERROR: Authentication failed.")
    print(f"Details: {e}")