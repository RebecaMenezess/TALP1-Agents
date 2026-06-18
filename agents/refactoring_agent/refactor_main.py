import sys
import os
import re
import ollama

MODEL = "qwen2.5-coder:7b"
BASE_URL = "http://localhost:11434"

SYSTEM_PROMPT = """
You are a Senior Software Engineer and world-class expert in Martin Fowler's "Refactoring: Improving the Design of Existing Code, 2nd Edition".
Your role is to perform a DEEP, LINE-BY-LINE analysis of Python code, applying ALL of Fowler's refactoring techniques and code smell catalog — including careful identification of FALSE POSITIVES (things that look like smells but aren't) and FALSE NEGATIVES (real smells that are easy to miss).

══════════════════════════════════════════════════
PHASE 1 — CODE SMELLS CATALOG (scan every line)
══════════════════════════════════════════════════
For EVERY smell below, explicitly state: FOUND / NOT FOUND / FALSE POSITIVE (with line reference and reasoning).

NAMING SMELLS:
- Mysterious Name: variables, functions, classes, or modules with unclear names (x, data, temp, flag, do_stuff)
  FALSE POSITIVE RULE: single-letter loop counters (i, j, k) in tight loops are acceptable convention

DUPLICATION SMELLS:
- Duplicated Code: identical or near-identical blocks in multiple places
  FALSE POSITIVE RULE: two blocks that look similar but handle subtly different edge cases are NOT duplicates — read the logic carefully before flagging

FUNCTION SMELLS:
- Long Function: functions with too many lines (>10–15 meaningful lines is suspicious)
  FALSE POSITIVE RULE: a long function that is a clear, ordered step-by-step algorithm may be intentionally long for readability
- Long Parameter List: more than 3–4 parameters signals a missing abstraction
  FALSE POSITIVE RULE: if the function is a low-level utility deliberately designed for flexibility, a longer list may be justified
- Flag Argument: boolean parameters that switch behavior inside the function
- Dead Code: unreachable code, unused imports, functions never called

DATA SMELLS:
- Global Data: module-level mutable state that any function can change
  FALSE POSITIVE RULE: constants (ALL_CAPS) are not global data smells
- Mutable Data: data structures mutated in multiple places, making state hard to track
- Data Clumps: the same group of 3+ variables that always appear together (should become a class/dataclass)
- Primitive Obsession: using raw strings/ints/dicts where a small class or dataclass would add clarity
  FALSE POSITIVE RULE: a plain string for a URL or a dict for a config file is often fine — only flag when the primitive is being used as a domain concept with behavior
- Temporary Field: an instance variable that is only set in some code paths, leaving it None/empty in others

COUPLING SMELLS:
- Feature Envy: a function that references another class's data more than its own
- Inappropriate Intimacy: two classes that access each other's private details too freely
- Message Chains: a.b().c().d() — a chain of 3+ calls navigating object structure
  FALSE POSITIVE RULE: fluent builder APIs (.filter().map().sort()) are intentional design, not a smell
- Middle Man: a class whose methods only delegate to another class — it adds no value
- Divergent Change: one class that changes for multiple unrelated reasons
- Shotgun Surgery: one change that forces edits in many unrelated places

CONDITIONAL SMELLS:
- Repeated Switches / if-elif chains: switching on the same type/tag in multiple places
  FALSE POSITIVE RULE: a single, small if-elif that maps values is fine — the smell is repetition across multiple functions
- Nested Conditionals: if blocks nested more than 2 levels deep without guard clauses
- Speculative Generality: abstract hooks, unused parameters, or base classes that exist "for future use"

INHERITANCE SMELLS:
- Refused Bequest: a subclass that inherits methods it doesn't need or that it overrides to do nothing
- Alternative Classes with Different Interfaces: two classes that do the same thing with different method names
- Lazy Element: a class or function so small it should be inlined

COMMENT SMELLS:
- Explaining Comment: a comment that exists to explain what the code does — the code itself should be readable enough. Extract Function and rename instead.
  FALSE POSITIVE RULE: comments explaining WHY (a non-obvious business rule, a workaround for a known bug, a constraint from an external system) are GOOD and must NOT be removed

══════════════════════════════════════════════════
PHASE 2 — FALSE POSITIVE ANALYSIS
══════════════════════════════════════════════════
After the smell scan, list every case where code APPEARS to need refactoring but DOES NOT. Explain why each is a false positive.

══════════════════════════════════════════════════
PHASE 3 — FALSE NEGATIVE HUNT
══════════════════════════════════════════════════
Actively look for smells that are easy to miss (Primitive Obsession, Feature Envy, Temporary Fields, hidden side effects, Data Clumps, Divergent Change, dead imports/unused variables).

══════════════════════════════════════════════════
OUTPUT FORMAT — MANDATORY STRUCTURE
══════════════════════════════════════════════════
## 1. Code Smell Scan
## 2. False Positive Summary
## 3. False Negative Alerts
## 4. Refactoring Plan
## 5. Refactored Code
```python
# complete refactored code here
```
## 6. Changes Made

══════════════════════════════════════════════════
ABSOLUTE RULES
══════════════════════════════════════════════════
1. NEVER change behavior — only structure.
2. NEVER add features not in the original code.
3. NEVER remove a "WHY" comment — only remove "WHAT" comments.
4. ALWAYS justify each refactoring with the specific Fowler technique by name.
5. ALWAYS flag false positives — it is as important as flagging real smells.
6. ALWAYS do the line-by-line smell scan BEFORE writing the refactored code.
"""


def add_line_numbers(code: str) -> str:
    lines = code.splitlines()
    width = len(str(len(lines))) if lines else 1
    return "\n".join(f"{str(i + 1).rjust(width)} | {line}" for i, line in enumerate(lines))


def extract_refactored_code(full_response: str) -> str:
    """Extrai apenas o bloco de código Python da seção '## 5. Refactored Code'."""
    match = re.search(r"```python\s*\n([\s\S]*?)```", full_response)
    if match:
        return match.group(1).strip()
    return ""


def run_refactor(code: str, critic_report: str = "", log_callback=None) -> dict:
    """
    Executa o Agente 3 (refatorador) sobre um código real.

    Args:
        code: o código Python a ser refatorado (normalmente o gerado pelo Agente 1).
        critic_report: relatório de texto opcional vindo do Agente 2, usado como
                       contexto extra para o modelo saber quais bugs já foram encontrados.
        log_callback: função opcional chamada com strings de log conforme o agente avança.

    Returns:
        dict com as chaves:
            full_analysis: texto completo retornado pelo modelo (fases 1-6)
            refactored_code: apenas o código refatorado, extraído da resposta
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)

    log("Numerando linhas do código…")
    numbered = add_line_numbers(code)

    context_block = ""
    if critic_report:
        context_block = (
            "\n\nO Agente Crítico (QA) já analisou este código e encontrou o seguinte:\n"
            f"{critic_report}\n\n"
            "Leve esses problemas em consideração ao propor a refatoração — "
            "se possível, corrija o bug identificado como parte da refatoração estrutural."
        )

    user_message = (
        "Perform a DEEP LINE-BY-LINE analysis of the Python code below, "
        "following the mandatory output format (phases 1–6).\n\n"
        "The code is shown with line numbers for precise references:\n\n"
        f"```python\n{numbered}\n```"
        f"{context_block}"
    )

    log("Chamando qwen2.5-coder:7b para análise de refatoração (pode levar 1-2 min)…")

    try:
        client = ollama.Client(host=BASE_URL)
        response = client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            options={"temperature": 0.1},
            stream=True,
        )

        full_response = ""
        for chunk in response:
            token = chunk["message"]["content"]
            full_response += token

    except Exception as exc:
        log(f"Erro ao chamar o modelo: {exc}")
        return {
            "full_analysis": f"Erro ao executar o Agente 3: {exc}",
            "refactored_code": "",
        }

    log("Análise de refatoração concluída.")
    refactored_code = extract_refactored_code(full_response)

    if refactored_code:
        log("Código refatorado extraído com sucesso.")
    else:
        log("Não foi possível extrair um bloco de código refatorado da resposta.")

    return {
        "full_analysis": full_response,
        "refactored_code": refactored_code,
    }


# ----------------------------------------
# EXECUÇÃO DIRETA (modo standalone, mantém compatibilidade com uso via terminal)
# ----------------------------------------
def read_code_from_file(path: str) -> str:
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}")
        sys.exit(1)
    if not path.endswith(".py"):
        print(f"Warning: '{path}' does not have a .py extension.")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_code_from_stdin() -> str:
    print("Paste your Python code below.")
    print("When done, press Enter then Ctrl+D (Mac/Linux) or Ctrl+Z + Enter (Windows):\n")
    lines = []
    try:
        for line in sys.stdin:
            lines.append(line)
    except KeyboardInterrupt:
        pass
    return "".join(lines)


def main():
    if len(sys.argv) == 2:
        path = sys.argv[1]
        print(f"\nReading code from: {path}\n")
        code = read_code_from_file(path)
    else:
        code = read_code_from_stdin()

    if not code.strip():
        print("Error: no code provided.")
        sys.exit(1)

    line_count = len(code.splitlines())
    print("\n" + "=" * 65)
    print("  REFACTORING AGENT — Deep Analysis · Martin Fowler's Catalog")
    print(f"  {line_count} lines · False Positive + False Negative Detection")
    print("=" * 65 + "\n")

    result = run_refactor(code, log_callback=print)
    print(result["full_analysis"])


if __name__ == "__main__":
    main()
