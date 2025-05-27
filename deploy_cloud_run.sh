#!/bin/bash

# Cloud Run Deployment Script for Health Risk Assessment App

set -e

# Configuration - Update these values
PROJECT_ID="abiding-center-460016-k1"
REGION="us-central1"
SERVICE_NAME="health-assessment-app"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying Health Risk Assessment App to Cloud Run${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ Error: gcloud CLI is not installed${NC}"
    echo "Please install gcloud CLI: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Error: .env file not found${NC}"
    echo "Please create a .env file with your Google Cloud configuration:"
    echo "GCP_KEY_PATH=./gcp_key.json"
    echo "PROJECT_ID=your-project-id"
    echo "AGENT_ID=your-agent-id"
    echo "LOCATION_ID=your-location-id"
    echo "LANGUAGE_CODE=en-US"
    exit 1
fi

# Check if GCP key file exists
if [ ! -f "gcp_key.json" ]; then
    echo -e "${RED}❌ Error: gcp_key.json file not found${NC}"
    echo "Please add your Google Cloud service account key as gcp_key.json"
    exit 1
fi

echo -e "${YELLOW}📋 Pre-deployment checklist:${NC}"
echo "✓ gcloud CLI installed"
echo "✓ Docker installed"
echo "✓ .env file exists"
echo "✓ gcp_key.json exists"

# Set the project
echo -e "${YELLOW}🔧 Setting up Google Cloud project...${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}🔌 Enabling required Google Cloud APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable speech.googleapis.com
gcloud services enable texttospeech.googleapis.com
gcloud services enable dialogflow.googleapis.com

# Build the Docker image
echo -e "${YELLOW}🐳 Building Docker image...${NC}"
docker build -t $IMAGE_NAME .

# Push the image to Google Container Registry
echo -e "${YELLOW}📤 Pushing image to Google Container Registry...${NC}"
docker push $IMAGE_NAME

# Deploy to Cloud Run
echo -e "${YELLOW}🚀 Deploying to Cloud Run...${NC}"
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --max-instances 10 \
    --timeout 300 \
    --concurrency 80 \
    --port 8080 \
    --set-env-vars "GCP_KEY_PATH=./gcp_key.json" \
    --set-env-vars "PROJECT_ID=${PROJECT_ID}"

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo -e "${GREEN}🌐 Your Health Risk Assessment app is now available at:${NC}"
echo -e "${GREEN}${SERVICE_URL}${NC}"

echo -e "\n${YELLOW}📝 Next steps:${NC}"
echo "1. Visit the URL above to test your application"
echo "2. Make sure your Dialogflow CX agent is properly configured"
echo "3. Test the voice conversation functionality"
echo "4. Monitor logs with: gcloud logs tail --service=$SERVICE_NAME"

echo -e "\n${YELLOW}🔍 Useful commands:${NC}"
echo "View logs: gcloud logs tail --service=$SERVICE_NAME"
echo "Update service: gcloud run services update $SERVICE_NAME --region=$REGION"
echo "Delete service: gcloud run services delete $SERVICE_NAME --region=$REGION" 