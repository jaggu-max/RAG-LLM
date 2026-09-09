# Nexus-RAG

> Intelligent Retrieval-Augmented Generation System

## Overview

Nexus-RAG is a full-stack RAG application that enables intelligent document ingestion, hybrid search, and AI-powered question answering across multiple file formats.

## Tech Stack

- **Backend:** Python, FastAPI, ChromaDB, Gemini/LMStudio
- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Infrastructure:** Docker, Docker Compose

## Quick Start

```bash
# Clone the repo
git clone <repo-url>
cd nexus-rag

# Start with Docker
docker-compose up --build

# Or run locally
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Project Structure

```
nexus-rag/
├── backend/          # FastAPI backend + RAG pipeline
├── frontend/         # React + TypeScript frontend
├── docker-compose.yml
└── README.md
```

## License

MIT
