FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data and logs directories
RUN mkdir -p data logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python3", "bluesky_monitor_v2.py", "--auto"]
