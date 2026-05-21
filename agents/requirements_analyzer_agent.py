# This agent was created to test the functionality of reading requisites. It won't be one of the final agents of the project

import ollama

MODEL = "codellama:7b"

SYSTEM_PROMPT = """
You are a software requirements analysis expert.

Your task is to read requirement documents and extract the information in a structured way.

Rules:
- Return ONLY the extracted requirements
- No explanations
- No markdown
"""

def read_requirements_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def analyze_requirements(requirements_text):
    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": requirements_text
            }
        ]
    )

    return response["message"]["content"].strip()


def main():
    requirements_text = read_requirements_file("requirements.txt")
    analysis = analyze_requirements(requirements_text)
    print("\nRequirements Analysis:\n")
    print(analysis)
    print('\n')


if __name__ == "__main__":
    main()
