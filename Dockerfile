FROM python:3.10-slim

WORKDIR /app

# Force Python output to be unbuffered (useful for logs)
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Hugging Face Spaces expects the app to run on port 7860
EXPOSE 7860

# Start the FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
