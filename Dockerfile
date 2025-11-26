# ==========================================
# Stage 1: Builder (Compilers & Dependency Prep)
# ==========================================
FROM python:3.12-slim-bookworm as builder

# Prevent Python buffering and set Poetry vars
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    PIP_NO_CACHE_DIR=off

# Install build dependencies (gcc, python headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy dependency files first (levarging Docker cache)
COPY pyproject.toml poetry.lock ./

# Install dependencies (CPU versions via lock file)
# --no-root: Don't install the project code yet, just libs
RUN poetry install --no-root --no-ansi

# ==========================================
# Stage 2: Runtime (Production Image)
# ==========================================
FROM python:3.12-slim-bookworm as runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install Runtime System Dependencies
# 1. OCR (Tesseract) & PDF Tools (Poppler) - REQUIRED for your stack
# 2. System Libs for Playwright/OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Install Playwright Browsers (Chromium only to save space)
RUN playwright install chromium

# Copy application code
COPY . .

# Expose the API port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "app.mcp_server:app", "--host", "0.0.0.0", "--port", "8000"]