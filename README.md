# Telegram Simulator

A lightweight Telegram-like messaging app built with FastAPI and a modern single-page frontend. It supports multiple channels, secure login, username/password authentication, and media messages (images, video, audio, and documents).

## Features
- Secure user accounts with password hashing using bcrypt
- Registration with username and profile photo
- JWT-based authentication
- Multiple independent channels
- Text messages and file attachments
- Modern Telegram-inspired UI
- Local SQLite storage
- No subscription or invite flow required

## Tech Stack
- Backend: FastAPI
- Frontend: HTML + CSS + JavaScript
- Database: SQLite
- Security: bcrypt + JWT

## Quick Start

1. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Run the app:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Open:
   ```text
   http://localhost:8000
   ```

## Notes
- Default secret key is set for local development. For production, set an environment variable:
  ```bash
  export JWT_SECRET="your-very-secure-random-secret"
  ```
- Uploaded files are stored in the `uploads/` folder.
- The database is created automatically on first run as `telegram_simulator.db`.
