#!/bin/bash
# CircuitSense — Automated Cloud Run Deployment
# #GeminiLiveAgentChallenge
gcloud run deploy circuitsense \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=${GEMINI_API_KEY} \
  --port 8080 \
  --memory 512Mi \
  --timeout 300
