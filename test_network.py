#!/usr/bin/env python3

import os
import requests
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment variables
load_dotenv()

def test_basic_connectivity():
    """Test basic internet connectivity"""
    try:
        response = requests.get('https://httpbin.org/ip', timeout=10)
        print(f"✓ Basic internet connectivity: {response.status_code}")
        print(f"  Your IP: {response.json()}")
        return True
    except Exception as e:
        print(f"✗ Basic internet connectivity failed: {e}")
        return False

def test_twilio_api_direct():
    """Test direct API call to Twilio"""
    try:
        response = requests.get('https://api.twilio.com', timeout=10)
        print(f"✓ Direct Twilio API access: {response.status_code}")
        return True
    except Exception as e:
        print(f"✗ Direct Twilio API access failed: {e}")
        return False

def test_twilio_client():
    """Test Twilio client initialization and basic API call"""
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        if not account_sid or not auth_token:
            print("✗ Twilio credentials not found in environment")
            return False
            
        print(f"Account SID: {account_sid[:10]}...")
        
        client = Client(account_sid, auth_token)
        
        # Try to fetch account info (simple API call)
        account = client.api.accounts(account_sid).fetch()
        print(f"✓ Twilio client works: Account {account.friendly_name}")
        return True
        
    except Exception as e:
        print(f"✗ Twilio client failed: {e}")
        return False

def test_dns_resolution():
    """Test DNS resolution for Twilio"""
    import socket
    try:
        ip = socket.gethostbyname('api.twilio.com')
        print(f"✓ DNS resolution for api.twilio.com: {ip}")
        return True
    except Exception as e:
        print(f"✗ DNS resolution failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Network Connectivity Test ===")
    
    print("\n1. Testing DNS resolution...")
    test_dns_resolution()
    
    print("\n2. Testing basic internet connectivity...")
    test_basic_connectivity()
    
    print("\n3. Testing direct Twilio API access...")
    test_twilio_api_direct()
    
    print("\n4. Testing Twilio client...")
    test_twilio_client()
    
    print("\n=== Test Complete ===") 