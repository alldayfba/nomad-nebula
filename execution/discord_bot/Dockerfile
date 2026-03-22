FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . ./execution/discord_bot/

# Copy nova_core
COPY ../nova_core/ ./execution/nova_core/

# Copy required data files
RUN mkdir -p .tmp/discord .tmp/coaching

ENV PYTHONPATH=/app:/app/execution
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "execution.discord_bot.main"]
