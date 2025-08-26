FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Copy everything from worker/ into /app/worker
COPY . /app/worker

# Install requirements
RUN pip install --no-cache-dir -r /app/worker/requirements.txt && \
    pip install --no-cache-dir python-multipart

EXPOSE 8090

# Run the FastAPI app
CMD ["uvicorn", "worker.app.main:app", "--host", "0.0.0.0", "--port", "8090"]
