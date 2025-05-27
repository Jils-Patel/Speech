#!/usr/bin/env python3
"""
Local testing script for the cloud-ready health assessment app.
Run this before deploying to Cloud Run to catch any issues early.
"""

import os
import sys
import time
import requests
import subprocess
from threading import Thread

def check_requirements():
    """Check if all required files and dependencies exist."""
    print("🔍 Checking requirements...")
    
    required_files = [
        'app_cloud.py',
        'requirements_cloud.txt', 
        'templates/index_cloud.html',
        '.env',
        'gcp_key.json'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        return False
    
    print("✅ All required files present")
    
    # Check environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    required_env_vars = ['GCP_KEY_PATH', 'PROJECT_ID', 'AGENT_ID', 'LOCATION_ID']
    missing_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        return False
    
    print("✅ All environment variables present")
    return True

def install_dependencies():
    """Install required dependencies."""
    print("📦 Installing dependencies...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements_cloud.txt'], 
                      check=True, capture_output=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def test_google_cloud_apis():
    """Test Google Cloud API connectivity."""
    print("🌐 Testing Google Cloud API connectivity...")
    
    try:
        from google.cloud import texttospeech
        from google.cloud import speech_v1 as speech
        from google.cloud import dialogflowcx_v3beta1 as dialogflowcx
        
        # Test TTS client
        tts_client = texttospeech.TextToSpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
        print("✅ Text-to-Speech client initialized")
        
        # Test Speech client  
        speech_client = speech.SpeechClient.from_service_account_json(os.getenv("GCP_KEY_PATH"))
        print("✅ Speech-to-Text client initialized")
        
        # Test Dialogflow CX client
        LOCATION_ID = os.getenv("LOCATION_ID")
        api_endpoint = f"{LOCATION_ID}-dialogflow.googleapis.com:443"
        client_options = {"api_endpoint": api_endpoint}
        dialogflow_client = dialogflowcx.SessionsClient(client_options=client_options)
        print("✅ Dialogflow CX client initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ Google Cloud API test failed: {e}")
        return False

def start_local_server():
    """Start the Flask app locally."""
    print("🚀 Starting local server...")
    
    try:
        # Start server in background
        process = subprocess.Popen([sys.executable, 'app_cloud.py'], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
        
        # Wait a bit for server to start
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is None:
            print("✅ Server started successfully")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"❌ Server failed to start:")
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            return None
            
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return None

def test_endpoints():
    """Test basic HTTP endpoints."""
    print("🔗 Testing HTTP endpoints...")
    
    base_url = "http://localhost:8080"
    
    try:
        # Test main page
        response = requests.get(f"{base_url}/", timeout=10)
        if response.status_code == 200:
            print("✅ Main page loads successfully")
        else:
            print(f"❌ Main page failed: {response.status_code}")
            return False
            
        # Check if the response contains expected content
        if "Health Risk Assessment" in response.text:
            print("✅ Page content looks correct")
        else:
            print("❌ Page content doesn't match expected")
            return False
            
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🏥 Health Assessment App - Local Testing")
    print("=" * 50)
    
    # Run checks
    checks = [
        ("Requirements", check_requirements),
        ("Dependencies", install_dependencies), 
        ("Google Cloud APIs", test_google_cloud_apis),
    ]
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            print(f"\n❌ {check_name} check failed. Please fix the issues above.")
            return False
    
    # Start server and test
    print(f"\n🚀 Server Testing:")
    server_process = start_local_server()
    
    if server_process:
        try:
            time.sleep(2)  # Give server time to fully start
            
            if test_endpoints():
                print("\n🎉 All tests passed!")
                print("✅ Your app is ready for Cloud Run deployment")
                print("\nNext steps:")
                print("1. Edit deploy_cloud_run.sh with your project details")
                print("2. Run: ./deploy_cloud_run.sh")
                print("3. Test the deployed app with real voice interactions")
                
            else:
                print("\n❌ Endpoint tests failed")
                
        finally:
            # Clean up
            print("\n🧹 Cleaning up...")
            server_process.terminate()
            server_process.wait()
            print("✅ Server stopped")
    
    return True

if __name__ == "__main__":
    main() 