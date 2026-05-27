import ollama

MODEL = "codellama:7b"

SYSTEM_PROMPT = """
You are an expert Python software engineer.

Generate complete executable Python programs.

Rules:
- Return ONLY Python code
- No explanations 
- No markdown
"""

def generate_code(requirements):
    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": requirements
            }
        ]
    )

    code = response["message"]["content"]

    code = code.replace("```python", "")
    code = code.replace("```", "")

    return code.strip()


def save_code(code):
    with open("generated_code.py", "w", encoding="utf-8") as file:
        file.write(code)


def main():
    requirements = input("\nDescribe the Python code you want to generate: ")
    generated_code = generate_code(requirements)
    print("\nGenerated Code:\n")
    print(generated_code)
    save_code(generated_code)
    print("\nThe code was saved in generated_code.py\n")


if __name__ == "__main__":
    main()
