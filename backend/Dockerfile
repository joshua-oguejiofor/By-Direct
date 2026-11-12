# Step 1: Use official lightweight Python 3.12 image
FROM python:3.12-slim


# Step 2: Set the working directory inside the container
WORKDIR /app

# Step 3: Set environment variables to optimize Python execution
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Step 4: Install system dependencies required for compiling drivers (like asyncmy/MySQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Step 5: Install Python dependencies
COPY  requirements.txt .
# --no-cache-dir reduces image size by not storing install cache
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Step 6: Copy the rest of the application code into the container  
COPY . .


# Step 7: run as a normal user, not root
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Step 8: Expose the FastAPI port
EXPOSE 8000

# Step 9: Default command to run the FastAPI application
CMD [ "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1" ]




