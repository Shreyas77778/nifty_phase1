import requests
import time

class NSEOptionChain:
    def __init__(self):
        print("⚙️ NSE Live Option Chain Analytics Initialized...")
        self.base_url = "https://www.nseindia.com/"
        self.api_url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        
        # NSE block na kare isliye hum bilkul ek real browser ki tarah behave karenge
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br"
        }
        self.session = requests.Session()
        self._refresh_cookies()

    def _refresh_cookies(self):
        """NSE requires a valid session cookie before hitting their API."""
        try:
            self.session.get(self.base_url, headers=self.headers, timeout=5)
        except Exception as e:
            pass

    def get_pcr_and_max_pain(self):
        try:
            # 1. Fetch Option Chain Data
            response = self.session.get(self.api_url, headers=self.headers, timeout=5)
            
            # Agar session expire ho gaya (401 Unauthorized), toh cookies refresh karke wapas try karo
            if response.status_code == 401 or response.status_code == 403: 
                self._refresh_cookies()
                response = self.session.get(self.api_url, headers=self.headers, timeout=5)
            
            data = response.json()
            records = data['records']['data']
            spot_price = data['records']['underlyingValue']
            
            total_ce_oi = 0
            total_pe_oi = 0
            strikes_data = []

            # 2. Extract Open Interest for all strikes
            for item in records:
                strike = item.get('strikePrice')
                ce_oi = item.get('CE', {}).get('openInterest', 0)
                pe_oi = item.get('PE', {}).get('openInterest', 0)
                
                total_ce_oi += ce_oi
                total_pe_oi += pe_oi
                
                strikes_data.append({
                    'strike': strike,
                    'ce_oi': ce_oi,
                    'pe_oi': pe_oi
                })
            
            # 3. 🧮 CALCULATE PUT-CALL RATIO (PCR)
            pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else 1.0
            
            # 4. 🧮 CALCULATE MAX PAIN
            max_pain_strike = 0
            min_loss = float('inf')
            
            # CPU bachane ke liye sirf Spot price ke aas-paas (± 1000 points) ki strikes check karenge
            atm_strike = round(spot_price / 50) * 50
            test_strikes = [s['strike'] for s in strikes_data if (atm_strike - 1000) <= s['strike'] <= (atm_strike + 1000)]
            
            for test_strike in test_strikes:
                total_intrinsic_value = 0
                for item in strikes_data:
                    # CE Intrinsic Value (Agar market is test_strike par expire hua)
                    if test_strike > item['strike']:
                        total_intrinsic_value += (test_strike - item['strike']) * item['ce_oi']
                    # PE Intrinsic Value (Agar market is test_strike par expire hua)
                    if test_strike < item['strike']:
                        total_intrinsic_value += (item['strike'] - test_strike) * item['pe_oi']
                
                # Jis strike par Option Sellers ko sabse kam paisa dena padega, wahi Max Pain hai
                if total_intrinsic_value < min_loss:
                    min_loss = total_intrinsic_value
                    max_pain_strike = test_strike
                    
            return {
                "spot_price": spot_price,
                "pcr": pcr,
                "max_pain": max_pain_strike,
                "total_ce_oi": total_ce_oi,
                "total_pe_oi": total_pe_oi
            }
            
        except Exception as e:
            print(f"⚠️ NSE Option Chain Error: {e}")
            return {"spot_price": 0.0, "pcr": 1.0, "max_pain": 0, "total_ce_oi": 0, "total_pe_oi": 0}

# Testing ke liye
if __name__ == "__main__":
    oc = NSEOptionChain()
    data = oc.get_pcr_and_max_pain()
    print("🔥 LIVE OPTIONS DATA 🔥")
    print(f"Spot Price: ₹{data['spot_price']}")
    print(f"PCR (Put-Call Ratio): {data['pcr']}")
    print(f"Max Pain Strike: {data['max_pain']}")