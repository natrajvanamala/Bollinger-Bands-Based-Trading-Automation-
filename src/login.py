import os
import pyotp
from SmartApi import SmartConnect
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ===== YOUR CREDENTIALS (from .env file) =====
# Try to read from environment variables first
ANGEL_API_KEY = os.getenv("ANGEL_API_KEY")
ANGEL_CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
ANGEL_PASSWORD = os.getenv("ANGEL_PASSWORD")
ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

# If not found in .env, use hardcoded values (ONLY FOR DEVELOPMENT)
# ⚠️ WARNING: Remove these hardcoded values in production!
if not ANGEL_API_KEY:
    ANGEL_API_KEY = "k7Zh4jRP"  # Replace with your actual key
if not ANGEL_CLIENT_ID:
    ANGEL_CLIENT_ID = "A123456"  # Replace with your actual client ID
if not ANGEL_PASSWORD:
    ANGEL_PASSWORD = "YourPassword"  # Replace with your actual password
if not ANGEL_TOTP_SECRET:
    ANGEL_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # Replace with your actual TOTP secret

# Global angel object
angel = None

def login():
    global angel
    
    # Return cached login if already logged in
    if angel is not None:
        return angel
    
    try:
        angel = SmartConnect(api_key=ANGEL_API_KEY)
        totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
        data = angel.generateSession(ANGEL_CLIENT_ID, ANGEL_PASSWORD, totp)
        
        if not data.get("status"):
            print("❌ Login failed:", data)
            angel = None
            return None
        
        print("✅ Angel Login Successful")
        return angel
    
    except Exception as e:
        print("🚨 Login Error:", e)
        angel = None
        return None

# Auto-login when imported
angel = login()
