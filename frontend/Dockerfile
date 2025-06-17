FROM python:3.11-alpine

WORKDIR /app

# Copy application code
COPY . .

# Make server.py executable
RUN chmod +x server.py

EXPOSE 3030

CMD ["python", "server.py"]