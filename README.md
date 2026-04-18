# Taskera AI

<p align="center">
  <em>A powerful, stateful AI agent built with FastAPI, LangGraph, and Gemini.</em>
</p>

Taskera AI is a multi-modal AI assistant capable of processing complex queries autonomously. By utilizing persistent user sessions, dynamic tool usage, and an event-driven architecture, Taskera AI acts as a comprehensive personal assistant. It handles text, voice, documents, and images—all while seamlessly scheduling your life and securely managing your data.

---

## ✨ Key Features

- 🧠 **Stateful AI Agent**: Powered by **Google Gemini 2.5 Flash Lite** and **LangGraph**, the agent maintains context across multi-turn conversations and decides dynamically which tools to use.
- 🎙️ **Voice Interactions**: Speak to your assistant naturally. Integrated with **Whisper** for accurate speech-to-text and high-quality Text-to-Speech (TTS) for spoken responses.
- 📄 **Document RAG & OCR**: 
  - **Retrieval-Augmented Generation (RAG)**: Upload PDFs, Word documents, or text files and instantly chat with your data.
  - **Optical Character Recognition (OCR)**: Extract and analyze text from uploaded images (PNG, JPG, JPEG).
- 🛠️ **Unified Tooling (MCP)**: Utilizes the **Model Context Protocol (MCP)** via JSON-RPC to execute a diverse suite of tools:
  - Web Search (DuckDuckGo, Headless Browser)
  - Wikipedia & Weather Search
  - Calendar & Event Management (via Supabase)
  - Background Research Task Scheduling
  - Calculation & Translation
- 🔒 **Robust Security & Auth**: Protects user data with JWT-based authentication, Google OAuth integration, rate-limiting (SlowAPI), prompt injection detection, and strict Content Security Policies (CSP).
- 💻 **Modern Frontend**: A responsive, vanilla JavaScript frontend featuring an intuitive chat interface, inline file attachments, Markdown rendering, and real-time audio playback.

## 🏗️ Architecture

Taskera AI is divided into a robust API backend and a lightweight, fast frontend.

### Backend Stack
- **Framework**: FastAPI (Python)
- **AI & Orchestration**: LangChain, LangGraph, Google Gemini API
- **Database & Memory**: Supabase, custom memory checkpointing for persistent agent states
- **Tool Communication**: MCP (Model Context Protocol)
- **Authentication**: Authlib (Google OAuth), PyJWT

### Frontend Stack
- **Language**: Vanilla JavaScript (ES6+), HTML5, CSS3 (Tailwind implied by utility classes)
- **Features**: MediaRecorder API for voice capture, dynamic DOM manipulation for chat histories, and fully responsive design.

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- Node.js (Optional, if using a bundler for frontend)
- Supabase Account (for database and calendar tracking)
- Google Cloud Console Account (for Gemini API Key and OAuth credentials)

### Environment Variables
Ensure the following environment variables are configured in your `.env` file:

```env
GOOGLE_API_KEY=your_gemini_api_key
JWT_SECRET_KEY=your_jwt_secret
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
GOOGLE_REDIRECT_URI=http://localhost:7860/auth/google/callback
FRONTEND_URL=http://localhost:8080
MCP_SERVER_URL=http://127.0.0.1:7860/mcp
```

### Running the Application

1. **Install Dependencies**:
    Use the potery for that
   ```bash
   poetry install
   ```

2. **Start the Backend**:
   ```bash
   uvicorn app.mcp_server:app --host 0.0.0.0 --port 7860 --reload
   ```

3. **Start the Frontend**:
   Serve the `frontend/` directory using any static file server (e.g., Live Server, Python's `http.server`).

## 🛡️ License
This project is licensed under the MIT License.
