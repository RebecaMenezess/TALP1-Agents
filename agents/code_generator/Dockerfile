FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY code_generator_agent.py .
COPY llm_config.json .

# The container connects to Ollama running on the host machine.
# The base_url in llm_config.json should point to host.docker.internal:11434
# when running on Docker Desktop (Windows/Mac), or the host's IP on Linux.

CMD ["python", "code_generator_agent.py"]
