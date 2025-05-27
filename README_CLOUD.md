# Health Risk Assessment - Cloud Version 🏥☁️

A cloud-ready voice-powered health risk assessment application that runs on Google Cloud Run with real-time speech conversations.

## 🎯 What's Different in the Cloud Version

This version has been completely rebuilt to work in cloud environments:

### ✅ **What Works Now:**
- **Real-time voice conversations** - Browser captures audio, cloud processes it
- **Google Cloud Run deployment** - Fully scalable serverless hosting
- **WebSocket communication** - Live bidirectional communication
- **Professional audio quality** - WebRTC audio capture in browser
- **Voice Activity Detection** - Automatic speech start/stop detection
- **Live transcript updates** - Real-time conversation display
- **Multiple concurrent users** - Each user gets their own session

### 🚫 **What Was Removed:**
- PyAudio (hardware dependency)
- pygame (hardware dependency) 
- All server-side audio capture/playback
- Hardware-specific audio configuration

## 🏗️ Architecture

```
┌─────────────────┐    WebSocket     ┌─────────────────┐    API calls    ┌─────────────────┐
│   Browser       │ ◄─────────────► │  Cloud Run      │ ◄─────────────► │ Google Cloud    │
│                 │                 │                 │                 │                 │
│ • Audio Capture │                 │ • Speech-to-Text│                 │ • Speech API    │
│ • Audio Playback│                 │ • Dialogflow CX │                 │ • TTS API       │
│ • UI Updates    │                 │ • Text-to-Speech│                 │ • Dialogflow CX │
│ • WebRTC        │                 │ • Session Mgmt  │                 │                 │
└─────────────────┘                 └─────────────────┘                 └─────────────────┘
```

## 🚀 Quick Deployment

### Prerequisites
- Google Cloud account with billing enabled
- Docker installed locally
- gcloud CLI installed
- Domain (optional, for custom URLs)

### 1. Setup Google Cloud
```bash
# Install gcloud CLI if not already installed
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Prepare Your Files
```bash
# Clone/download this project
git clone <your-repo>
cd health-assessment-cloud

# Create .env file
cat > .env << EOF
GCP_KEY_PATH=./gcp_key.json
PROJECT_ID=your-gcp-project-id
AGENT_ID=your-dialogflow-agent-id
LOCATION_ID=us-central1
LANGUAGE_CODE=en-US
EOF

# Add your Google Cloud service account key
# Download from Google Cloud Console > IAM & Admin > Service Accounts
# Save as: gcp_key.json
```

### 3. Deploy to Cloud Run
```bash
# Edit deploy_cloud_run.sh with your project details
nano deploy_cloud_run.sh  # Update PROJECT_ID, REGION, SERVICE_NAME

# Run deployment
./deploy_cloud_run.sh
```

### 4. Done! 🎉
Your app will be available at: `https://your-service-name-hash-region.a.run.app`

## 🔧 Manual Deployment (Alternative)

If you prefer manual control:

```bash
# Build and push image
docker build -t gcr.io/YOUR_PROJECT_ID/health-assessment .
docker push gcr.io/YOUR_PROJECT_ID/health-assessment

# Deploy to Cloud Run
gcloud run deploy health-assessment \
    --image gcr.io/YOUR_PROJECT_ID/health-assessment \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --max-instances 10 \
    --timeout 300 \
    --port 8080
```

## 🎮 Usage

1. **Open the app** in your browser (HTTPS required for microphone access)
2. **Click "Start Health Assessment"** 
3. **Allow microphone access** when prompted
4. **Wait for the AI greeting** - it will speak first
5. **Speak your response** when you see the "🎤 Listening" indicator
6. **Continue the conversation** - the AI will guide you through health questions
7. **View live transcript** as the conversation progresses
8. **Download transcript** when completed

## 🔒 Security & Privacy

### HTTPS Required
- Browser microphone APIs require HTTPS
- Cloud Run provides HTTPS by default
- Custom domains need SSL certificates

### Data Handling
- Audio is processed in real-time (not stored permanently)
- Transcripts are temporarily stored in memory
- For HIPAA compliance, add:
  - Data encryption at rest
  - Audit logging
  - User consent mechanisms
  - Data retention policies

### Authentication (Optional)
Add user authentication for production:
```bash
# Deploy with authentication required
gcloud run deploy health-assessment \
    --no-allow-unauthenticated \
    # ... other options
```

## 🛠️ Development

### Local Testing
```bash
# Install dependencies
pip install -r requirements_cloud.txt

# Run locally
python app_cloud.py

# Access at: http://localhost:8080
# Note: Microphone requires HTTPS in production
```

### Environment Variables
```bash
# Required
GCP_KEY_PATH=./gcp_key.json
PROJECT_ID=your-project-id
AGENT_ID=your-dialogflow-agent-id
LOCATION_ID=us-central1

# Optional
LANGUAGE_CODE=en-US
PORT=8080
```

## 📊 Monitoring & Logs

### View Logs
```bash
# Real-time logs
gcloud logs tail --service=health-assessment

# Filter by severity
gcloud logs read --service=health-assessment --filter="severity>=ERROR"
```

### Metrics
- Visit Google Cloud Console > Cloud Run > your-service
- Monitor: CPU usage, memory, request count, latency
- Set up alerts for high error rates

## 🔧 Troubleshooting

### Common Issues

**1. Microphone Access Denied**
- Ensure HTTPS (required for getUserMedia)
- Check browser permissions
- Try different browser

**2. Audio Not Playing**
- Check browser audio settings
- Ensure speakers/headphones connected
- Try different browser

**3. Transcription Errors**
- Check Google Cloud Speech API quotas
- Verify service account permissions
- Check audio quality/background noise

**4. Dialogflow Errors**
- Verify agent ID and location
- Check Dialogflow CX agent configuration
- Ensure proper training data

**5. Deployment Fails**
- Check Docker is running
- Verify gcloud authentication
- Ensure all environment variables set

### Debug Mode
```bash
# Enable debug logging
gcloud run services update health-assessment \
    --set-env-vars "FLASK_DEBUG=true"
```

## 🎯 Production Considerations

### Scaling
- Default: 1-10 instances, 80 concurrent requests
- Adjust based on usage:
```bash
gcloud run services update health-assessment \
    --max-instances 50 \
    --concurrency 100
```

### Cost Optimization
- Cloud Run pricing: Pay per request + CPU time
- Estimated cost: $0.10-0.50 per 1000 conversations
- Use `--min-instances 0` for cost savings (cold starts)

### Performance
- Use `--min-instances 1` for faster response times
- Consider regional deployment for global users
- Monitor latency and adjust resources

## 📞 Support

### Getting Help
1. Check logs first: `gcloud logs tail --service=health-assessment`
2. Review Google Cloud Run documentation
3. Check Dialogflow CX agent configuration
4. Verify Google Cloud API quotas and billing

### Common Commands
```bash
# Update service
gcloud run services update health-assessment --region us-central1

# Scale service  
gcloud run services update health-assessment --max-instances 20

# Delete service
gcloud run services delete health-assessment --region us-central1

# View service details
gcloud run services describe health-assessment --region us-central1
```

## 🎉 Success!

You now have a fully functional, cloud-deployed health risk assessment application with:
- ✅ Real-time voice conversations
- ✅ Professional audio quality  
- ✅ Scalable cloud infrastructure
- ✅ Live transcript generation
- ✅ Multi-user support
- ✅ Production-ready deployment

The app will automatically scale based on demand and only costs money when being used! 