# Ngrok Multi-Device Demo (Testing Only)

Use this when you want to demo different roles on different devices, such as:
- Driver on laptop
- Owner on phone

## 1) Backend setup

Update `backend/.env` for test mode:

```env
PORT=8000
ENABLE_NGROK_TESTING=true
CORS_ORIGINS=http://localhost:5173,http://localhost:5174
```

Start backend:

```powershell
cd backend
npm run dev
```

Expose backend with ngrok:

```powershell
ngrok http 8000
```

Copy the HTTPS backend URL (example: `https://abc123.ngrok-free.app`).

## 2) Frontend setup

Set API/socket URL in `frontend/.env` to the backend ngrok URL:

```env
VITE_SERVER_URL="https://abc123.ngrok-free.app"
```

Start frontend:

```powershell
cd frontend
npm run dev:demo
```

Expose frontend with ngrok:

```powershell
ngrok http 5173
```

Open the frontend ngrok URL on phone/laptop and use the app normally.

## 3) Important notes

- This mode is for demos/testing only.
- Keep `ENABLE_NGROK_TESTING=false` (or unset) for regular local development.
- Ngrok URLs change on restart unless you use a reserved domain.
- If login fails after URL change, clear browser cookies and sign in again.