# Deployment Guide

## 1) Environment Setup

Create environment files from examples:

- Copy backend/.env.example to backend/.env
- Copy frontend/.env.example to frontend/.env
- Copy AI-Layer/.env.example to AI-Layer/.env

Fill in all required credentials before deployment.

## 2) Local Production Build Validation

### Backend
- cd backend
- npm ci
- npm run start

### Frontend
- cd frontend
- npm ci
- npm run build
- npm run start

### AI Layer
- cd AI-Layer
- python -m venv .venv
- .venv\Scripts\activate
- pip install -r requirements.txt
- python gateway.py

## 3) Docker Deployment

From repository root:

- docker compose build
- docker compose up -d

Services:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000/health
- AI Layer: http://localhost:9001/health

## 4) Deployment Checklist

- backend/.env contains valid DB and API keys
- AI-Layer/.env contains MONGO and GEMINI keys
- CORS_ORIGINS matches deployed frontend domain
- ENABLE_NGROK_TESTING is false in production
- JWT_SECRET is rotated and strong
- Cloudinary and Razorpay production keys are configured

## 5) Suggested Production Hosts

- Frontend: Vercel or Netlify
- Backend: Render / Railway / Fly.io / VM container
- AI Layer: VM container or Azure Container Apps
- Database: MongoDB Atlas

## 6) Canonical Production AI URL

- Canonical AI base URL: https://steamypot-ai-layer.onrender.com
- Backend `AI_LAYER_URL` must point to the canonical AI base URL
- If you use an alias URL such as `https://steamypot-ai.onrender.com`, verify that it is mapped to the active AI service deployment in Render

## 7) Post-Deploy Smoke Tests

- GET /health on backend and AI Layer returns 200
- GET https://steamypot-ai-layer.onrender.com/health returns 200
- GET https://steamypot-ai-layer.onrender.com/api/review/health returns 200
- POST https://steamypot-ai-layer.onrender.com/api/review/summarize with a valid payload returns 200
- Sign-in works and cookie is set
- Home page loads restaurants
- Food assistant responds
- Contact recommendations return data
