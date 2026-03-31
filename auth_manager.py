import os
from SmartApi import SmartConnect
import pyotp
from dotenv import load_dotenv

load_dotenv()

class SmartSession:
    def __init__(self):
        self.client_id = os.getenv("ANGEL_CLIENT_ID")
        self.password = os.getenv("ANGEL_PASSWORD") # Ye apka 4-digit PIN hai
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET")
        
        # Jo API Key aapne image mein dikhayi, wahi yahan aayegi (.env file se)
        self.api_key = os.getenv("ANGEL_MARKET_KEY") 
        self.obj = None

    def login(self):
        try:
            # 1. TOTP Generate karna
            totp = pyotp.TOTP(self.totp_secret).now()
            
            # 2. Angel One SmartConnect Object banana
            self.obj = SmartConnect(api_key=self.api_key)
            
            # 3. Session create karna
            data = self.obj.generateSession(self.client_id, self.password, totp)
            
            if data['status']:
                print("✅ Login Successful! Session Tokens generated.")
                
                # --- WebSocket Support (CRITICAL FIX) ---
                # Naye SmartWebSocketV2 ko jwtToken aur feedToken dono chahiye hote hain
                session_data = data.get('data', {})
                
                self.obj.feed_token = session_data.get('feedToken')
                self.obj.jwt_token = session_data.get('jwtToken')
                self.obj.refresh_token = session_data.get('refreshToken')
                
                # Backup if feedToken is not in session_data
                if not self.obj.feed_token:
                    try:
                        self.obj.feed_token = self.obj.getfeedToken()
                    except: pass
                    
                return self.obj
            else:
                print(f"❌ Login Failed: {data['message']}")
                return None
        except Exception as e:
            print(f"⚠️ Auth Error: {str(e)}")
            return None

# Test the connection
if __name__ == "__main__":
    session = SmartSession()
    smart_api_client = session.login()
    if smart_api_client:
        print(f"✅ Feed Token Found: {str(smart_api_client.feed_token)[:15]}...")
        print(f"✅ JWT Token Found: {str(smart_api_client.jwt_token)[:15]}...")