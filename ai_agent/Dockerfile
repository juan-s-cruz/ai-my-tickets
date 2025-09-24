# ---- base image ----
FROM python:3.12-slim

ENV TZ=Europe/Copenhagen

# Install system packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app


# Install Python deps first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose port for runserver
EXPOSE 8100

# ---------- Local dev ----------
CMD ["python", "main.py"]