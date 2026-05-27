# Python Code Generator Agent

An AI agent that turns natural language descriptions into working, validated Python programs.
Built with Ollama (free, runs fully locally, no API key needed) and LangGraph.

## How it works

1. You type a description of the program you want
2. The agent generates Python code using a local LLM
3. A static validator checks the code for structural issues (missing error handling, wrong types, unused functions, etc.)
4. If issues are found, the agent sends the code back to the LLM with the critique and asks it to fix everything
5. Steps 3–4 repeat until the code passes or the iteration limit is reached
6. The final code is saved to `generated_code.py`

## Setup

**1. Install Ollama and pull the model**

Download Ollama, then run:
```bash
ollama pull qwen2.5-coder:7b
```
This downloads ~4 GB and only needs to be done once.

**2. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**3. Run**
```bash
python code_generator_agent.py
```

When prompted, describe the program you want, for example:
```
Build a command-line todo list application with add and remove
```
The generated code is saved to `generated_code.py`.

## Configuration

`llm_config.json` controls which model is used and how. You do not run this file, the agent reads it automatically on startup. No credentials are needed since Ollama runs locally.

```json
{
  "provider": "ollama",
  "model": "qwen2.5-coder:7b",
  "base_url": "http://localhost:11434",
  "temperature": 0.2,
  "max_tokens": 2048,
  "max_iterations": 3
}
```

## Docker (optional)

Docker is an alternative to the Setup steps above, use one or the other, not both.

Ollama must still be installed and running on your host machine, with the model already pulled (ollama pull qwen2.5-coder:7b). Before building, update base_url in llm_config.json:

- Windows / macOS: http://host.docker.internal:11434
- Linux: http://172.17.0.1:11434

Then:
```
bashdocker build -t code-agent .
docker run -it --rm code-agent
```
