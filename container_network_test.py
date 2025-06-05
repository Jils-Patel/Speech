#!/usr/bin/env python3

import os
import socket
import requests
from dotenv import load_dotenv

def test_dns_resolution():
    """Test DNS resolution"""
    try:
        ip = socket.gethostbyname('api.twilio.com')
        print(f"✓ DNS resolution for api.twilio.com: {ip}")
        return True
    except Exception as e:
        print(f"✗ DNS resolution failed: {e}")
        return False

def test_basic_connectivity():
    """Test basic internet connectivity"""
    try:
        response = requests.get('https://httpbin.org/ip', timeout=10)
        print(f"✓ Basic internet connectivity: {response.status_code}")
        return True
    except Exception as e:
        print(f"✗ Basic internet connectivity failed: {e}")
        return False

def test_twilio_api():
    """Test Twilio API connectivity"""
    try:
        response = requests.get('https://api.twilio.com', timeout=10)
        print(f"✓ Twilio API connectivity: {response.status_code}")
        return True
    except Exception as e:
        print(f"✗ Twilio API connectivity failed: {e}")
        return False

def test_twilio_client():
    """Test Twilio client"""
    try:
        from twilio.rest import Client
        
        # Load environment variables
        load_dotenv()
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        if not account_sid or not auth_token:
            print("✗ Twilio credentials not found")
            return False
            
        client = Client(account_sid, auth_token)
        account = client.api.accounts(account_sid).fetch()
        print(f"✓ Twilio client works: {account.friendly_name}")
        return True
        
    except Exception as e:
        print(f"✗ Twilio client failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Container Network Test ===")
    print(f"Python version: {os.sys.version}")
    print(f"Working directory: {os.getcwd()}")
    
    print("\n1. DNS Resolution Test:")
    test_dns_resolution()
    
    print("\n2. Basic Connectivity Test:")
    test_basic_connectivity()
    
    print("\n3. Twilio API Test:")
    test_twilio_api()
    
    print("\n4. Twilio Client Test:")
    test_twilio_client()
    
    print("\n=== Test Complete ===") 