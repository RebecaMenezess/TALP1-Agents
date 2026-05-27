from typing import TypedDict
import subprocess
import tempfile
import os
import re
import sys
import ast
import json

import ollama
from langgraph.graph import StateGraph, END


# ----------------------------------------
# LOAD CONFIG
# ----------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "llm_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    _config = json.load(_f)

MODEL          = _config.get("model", "qwen2.5-coder:7b")
BASE_URL       = _config.get("base_url", "http://localhost:11434")
TEMPERATURE    = _config.get("temperature", 0.2)
MAX_TOKENS     = _config.get("max_tokens", 2048)
MAX_ITERATIONS = _config.get("max_iterations", 3)


# ----------------------------------------
# PROMPTS
# ----------------------------------------

SYSTEM_PROMPT = """
You are a senior Python software engineer.

Generate high-quality executable Python programs.

MANDATORY INPUT VALIDATION RULES — apply to every program you write:

1. NEVER call int(input(...)) or float(input(...)) directly.
   ALWAYS assign input to 'raw' first, then convert inside try/except.

2. MANDATORY TWO-STEP PATTERN — use this EXACT structure for every numeric input:

    while True:
        raw = input("Enter a number: ").strip()
        try:
            value = int(raw)   # or float(raw)
            break
        except ValueError:
            print(f"Invalid input: '{raw}' is not a valid number. Please try again.")

   NEVER write: value = int(input(...))
   NEVER write: raw = int(input(...).strip())
   'raw' MUST be assigned BEFORE the try block so it is accessible in the except block.

3. EVERY input() call must be inside a while True loop so the user is
   re-prompted when they enter something invalid.

4. EVERY except block must print a message that tells the user:
   - What they typed (include the raw value in the message)
   - Why it was not accepted
   Example: print(f"Invalid input: '{raw}' is not a number. Please enter a numeric value.")

5. EVERY string input must check for empty/whitespace and re-prompt:
   if not value:
       print("Invalid input: value cannot be empty.")
       continue

6. EVERY input() result must be stripped: raw = input(...).strip()

7. Choose the correct numeric type — this is critical:
   - Use int() ONLY for: how many items, count, quantity, number of rows/columns, index.
   - Use float() for: measurements, scores, prices, temperatures, weights, salaries,
     percentages, statistical values (mean/median/std dev), or anything that could
     be decimal (3.14) or negative (-5). When in doubt, use float().
   - If the requirement mentions mean, median, average, std dev, statistics,
     or general "numbers" → the VALUES must use float(), not int().

8. Only validate uniqueness (duplicate check) if the requirements explicitly ask for it.

9. Only validate a numeric range (e.g. > 0) if the requirements explicitly require it.

10. If the program computes something, make sure ALL required outputs are printed.

11. Do NOT define helper functions that are never called.
    Do NOT add logic that the requirements did not ask for.

IMPORTANT — OUTPUT RULES:
- Return ONLY executable Python code.
- Do NOT use markdown fences (no ```).
- Do NOT include any text before or after the code.
- The output must run directly with: python script.py
"""


class AgentState(TypedDict):
    requirements: str
    code: str
    critique: str
    iteration: int


# ----------------------------------------
# AST UTILITIES
# ----------------------------------------

def get_node_ranges(tree, node_type):
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, node_type):
            start = node.lineno
            end = getattr(node, 'end_lineno', node.lineno)
            ranges.append((start, end))
    return ranges


def line_inside_ranges(lineno, ranges):
    return any(s <= lineno <= e for s, e in ranges)


def get_function_names(tree):
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def get_called_function_names(tree):
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
    return called


def get_all_conversion_calls(tree):
    """Return line numbers of int() and float() calls."""
    int_lines, float_lines = [], []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id == 'int':
            int_lines.append(node.lineno)
        elif node.func.id == 'float':
            float_lines.append(node.lineno)
    return int_lines, float_lines


def get_input_call_lines(tree):
    return [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'input'
    ]


def is_while_true(node):
    test = node.test
    return isinstance(test, ast.Constant) and test.value is True


def get_while_true_ranges(tree):
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and is_while_true(node):
            start = node.lineno
            end = getattr(node, 'end_lineno', node.lineno)
            ranges.append((start, end))
    return ranges


def get_try_blocks(tree):
    """Return all ast.Try nodes."""
    return [node for node in ast.walk(tree) if isinstance(node, ast.Try)]


def conversion_inside_try(tree):
    """
    Return line numbers of int()/float() calls that are INSIDE a try block
    AND whose try block has a corresponding except with a print statement.
    """
    handled_lines = set()
    for try_node in get_try_blocks(tree):
        try_start = try_node.lineno
        try_end = getattr(try_node, 'end_lineno', try_node.lineno)
        for handler in try_node.handlers:
            has_print = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == 'print'
                for n in ast.walk(handler)
            )
            if has_print:
                for node in ast.walk(try_node):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in ('int', 'float')
                        and try_start <= node.lineno <= try_end
                    ):
                        handled_lines.add(node.lineno)
    return handled_lines


# ----------------------------------------
# EXECUTE CODE TO CHECK FOR RUNTIME ERRORS
# ----------------------------------------
def try_execute_code(code: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = os.path.join(tmpdir, "generated_code.py")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            [sys.executable, "-c",
             f"import ast, sys; ast.parse(open('{code_path}').read()); "
             f"import importlib.util; "
             f"spec = importlib.util.spec_from_file_location('m', '{code_path}'); "
             f"mod = importlib.util.module_from_spec(spec)"],
            capture_output=True, text=True, timeout=10
        )

        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            return f"SyntaxError: {e}"

        if result.returncode != 0 and result.stderr.strip():
            return result.stderr.strip()

    return None


# ----------------------------------------
# REQUIREMENT COVERAGE TABLE
# ----------------------------------------
REQUIREMENT_COVERAGE_TABLE = [
    ("mean",               r'\bmean\b',                      "mean computation"),
    ("average",            r'\bmean\b|\baverage\b',          "average/mean computation"),
    ("median",             r'\bmedian\b',                    "median computation"),
    ("standard deviation", r'\bstdev\b|\bstandard_deviation\b|\bstd\b', "standard deviation computation"),
    ("std",                r'\bstdev\b|\bstd\b',             "standard deviation computation"),
    ("gcd",                r'\bgcd\b',                       "GCD computation"),
    ("lcm",                r'\blcm\b',                       "LCM computation"),
    ("factorial",          r'\bfactorial\b',                 "factorial computation"),
    ("fibonacci",          r'\bfibonacci\b|\bfib\b',         "Fibonacci computation"),
    ("prime",              r'\bprime\b|\bis_prime\b',        "prime number check"),
    ("palindrome",         r'\bpalindrome\b',                "palindrome check"),
    ("sort",               r'\bsort\b|\bsorted\b',           "sorting"),
    ("reverse",            r'\breverse\b|\b::-1\b',          "reversal"),
    ("csv",                r'\bcsv\b|\bwriter\b',            "CSV file writing"),
    ("xlsx",               r'\bopenpyxl\b|\bxlsxwriter\b',  "xlsx file creation"),
    ("json",               r'\bjson\b',                      "JSON handling"),
    ("txt",                r'\bopen\b.*\.txt|\.txt.*\bopen\b', "text file writing"),
    ("stack",              r'\bstack\b|\bappend\b.*\bpop\b', "stack operations"),
    ("queue",              r'\bqueue\b|\bdeque\b',           "queue operations"),
    ("linked list",        r'\blinked.?list\b|\bListNode\b', "linked list"),
    ("uppercase",          r'\bupper\b',                     "uppercase conversion"),
    ("lowercase",          r'\blower\b',                     "lowercase conversion"),
    ("count",              r'\bcount\b',                     "count operation"),
]

FLOAT_SIGNAL_WORDS = [
    "decimal", "float", "price", "cost", "salary", "temperature",
    "measurement", "score", "grade", "average", "mean", "median",
    "standard deviation", "std", "weight", "height", "distance",
    "percentage", "rate", "ratio", "value", "number", "numbers",
    "data", "statistics", "statistical",
]

INT_SIGNAL_WORDS = [
    "how many", "count", "quantity", "number of", "index",
    "id", "identifier", "age", "year", "day", "month",
    "quantity", "amount of items", "items",
]


# ----------------------------------------
# UNIVERSAL STRUCTURAL + SEMANTIC VALIDATOR
# ----------------------------------------
def validate_code(code: str, requirements: str) -> list[str]:
    issues = []
    req = requirements.lower()

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError — the code does not parse: {e}"]

    compile_error = try_execute_code(code)
    if compile_error:
        issues.append(
            f"EXECUTION ERROR — the code fails at load time: {compile_error}. "
            "Fix all syntax and import errors before anything else."
        )
        return issues

    try_ranges        = get_node_ranges(tree, ast.Try)
    while_true_ranges = get_while_true_ranges(tree)
    int_lines, float_lines = get_all_conversion_calls(tree)
    input_lines       = get_input_call_lines(tree)
    defined_fns       = get_function_names(tree)
    called_fns        = get_called_function_names(tree)

    bare_ints = [ln for ln in int_lines if not line_inside_ranges(ln, try_ranges)]
    if bare_ints:
        issues.append(
            f"CHECK FAILED — int() on line(s) {bare_ints} is not inside a try/except block. "
            "Use the mandatory two-step pattern:\n"
            "    raw = input(...).strip()\n"
            "    try:\n"
            "        value = int(raw)\n"
            "        break\n"
            "    except ValueError:\n"
            "        print(f\"Invalid input: '{raw}' is not a valid integer. Please try again.\")"
        )

    bare_floats = [ln for ln in float_lines if not line_inside_ranges(ln, try_ranges)]
    if bare_floats:
        issues.append(
            f"CHECK FAILED — float() on line(s) {bare_floats} is not inside a try/except block. "
            "Use the mandatory two-step pattern:\n"
            "    raw = input(...).strip()\n"
            "    try:\n"
            "        value = float(raw)\n"
            "        break\n"
            "    except ValueError:\n"
            "        print(f\"Invalid input: '{raw}' is not a valid number. Please try again.\")"
        )

    bare_inputs = [ln for ln in input_lines if not line_inside_ranges(ln, while_true_ranges)]
    if bare_inputs:
        issues.append(
            f"CHECK FAILED — input() on line(s) {bare_inputs} is not inside a 'while True' loop. "
            "Every input() must be inside a while True loop so the user is re-prompted on bad input."
        )

    for try_node in get_try_blocks(tree):
        try_has_conversion = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ('int', 'float')
            for n in ast.walk(try_node)
        )
        if not try_has_conversion:
            continue

        for handler in try_node.handlers:
            if handler.type is not None:
                exception_name = (
                    handler.type.id
                    if isinstance(handler.type, ast.Name)
                    else getattr(handler.type, 'attr', '')
                )
                if exception_name not in ('ValueError', 'Exception', ''):
                    continue

            has_print = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == 'print'
                for n in ast.walk(handler)
            )
            if not has_print:
                issues.append(
                    f"CHECK FAILED — except block at line {handler.lineno} handles a numeric "
                    "conversion but does not print an error message. "
                    "The variable 'raw' MUST be assigned before the try block so it is accessible here. "
                    "Required pattern:\n"
                    "    raw = input(...).strip()\n"
                    "    try:\n"
                    "        value = int(raw)  # or float(raw)\n"
                    "        break\n"
                    "    except ValueError:\n"
                    f"        print(f\"Invalid input: '{{raw}}' is not a valid number. Please try again.\")"
                )

    strip_count = len(re.findall(r'\.strip\s*\(\s*\)', code))
    if input_lines and strip_count == 0:
        issues.append(
            "CHECK FAILED — no .strip() calls found. "
            "Every input() result must have .strip() called on it: raw = input(...).strip()"
        )

    has_empty_guard = bool(re.search(r'if\s+not\s+\w+\b', code))
    if input_lines and not has_empty_guard:
        issues.append(
            "CHECK FAILED — no empty-string guard found. "
            "String inputs must check for empty values and re-prompt: "
            "if not value: print(\"Invalid input: value cannot be empty.\"); continue"
        )

    dead_fns = defined_fns - called_fns - {'main'}
    if dead_fns:
        truly_dead = {fn for fn in dead_fns
                      if len(re.findall(rf'\b{re.escape(fn)}\b', code)) == 1}
        if truly_dead:
            issues.append(
                f"CHECK FAILED — function(s) {truly_dead} are defined but never called. "
                "Remove unused functions or use them where appropriate."
            )

    needs_float = any(w in req for w in FLOAT_SIGNAL_WORDS)
    needs_int   = any(w in req for w in INT_SIGNAL_WORDS)
    code_uses_float = bool(float_lines)
    code_uses_int   = bool(int_lines)

    if needs_float and not code_uses_float:
        triggered = [w for w in FLOAT_SIGNAL_WORDS if w in req]
        issues.append(
            f"CHECK FAILED — the requirements mention {triggered} which implies "
            "values that can be decimal or negative, but the code only uses int(). "
            "Use float() to read these values so the user can enter decimals like 3.14 or -5."
        )

    if needs_int and code_uses_float and not code_uses_int:
        if needs_int and not needs_float:
            triggered = [w for w in INT_SIGNAL_WORDS if w in req]
            issues.append(
                f"CHECK FAILED — the requirements mention {triggered} which implies "
                "whole numbers only, but the code uses float() instead of int(). "
                "Use int() for whole-number quantities like counts and indices."
            )

    missing_features = []
    for req_phrase, code_pattern, description in REQUIREMENT_COVERAGE_TABLE:
        if req_phrase in req:
            if not re.search(code_pattern, code, re.IGNORECASE):
                missing_features.append(
                    f"'{req_phrase}' was requested but {description} "
                    f"(pattern: {code_pattern}) was not found in the code"
                )
    if missing_features:
        issues.append(
            "CHECK FAILED — the following features were requested but are missing from the code:\n"
            + "\n".join(f"    • {f}" for f in missing_features)
            + "\nImplement ALL of them."
        )

    return issues


# ----------------------------------------
# CLEAN MODEL OUTPUT
# ----------------------------------------
def clean_code(code: str) -> str:
    code = code.replace("```python", "").replace("```", "")
    lines = code.splitlines()
    clean_lines = []
    inside_code = False
    PROSE_STARTERS = (
        "Certainly", "Sure", "Here is", "Here's", "This code",
        "This program", "Note:", "Requirements:", "###", "**", "- **",
    )
    for line in lines:
        stripped = line.strip()
        if not inside_code and any(stripped.startswith(p) for p in PROSE_STARTERS):
            continue
        if not inside_code and (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or stripped.startswith("def ")
            or stripped.startswith("class ")
            or stripped.startswith("#")
            or stripped.startswith("if __name__")
        ):
            inside_code = True
        if inside_code and any(stripped.startswith(p) for p in PROSE_STARTERS):
            break
        if inside_code:
            clean_lines.append(line)
    return "\n".join(clean_lines).strip()


# ----------------------------------------
# CALL OLLAMA MODEL
# ----------------------------------------
def call_model(messages):
    try:
        client = ollama.Client(host=BASE_URL)
        response = client.chat(
            model=MODEL,
            messages=messages,
            options={"temperature": TEMPERATURE, "num_predict": MAX_TOKENS}
        )
        return response["message"]["content"]
    except Exception as error:
        print(f"\nModel error: {error}\n")
        return ""


# ----------------------------------------
# NODE 1 — GENERATE
# ----------------------------------------
def generate_code(state: AgentState):
    print("\n\nGenerating code...\n")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": state["requirements"]}
    ]
    return {"code": clean_code(call_model(messages)), "iteration": 1}


# ----------------------------------------
# NODE 2 — VALIDATE (no LLM)
# ----------------------------------------
def validate_code_node(state: AgentState):
    print(f"\nValidating code (iteration {state['iteration']})...\n")
    issues = validate_code(state["code"], state["requirements"])

    if issues:
        critique = (
            "The following checks FAILED. Fix ALL of them:\n\n"
            + "\n".join(f"  • {i}" for i in issues)
        )
        print(f"\nValidation FAILED ({len(issues)} issue(s)):\n{critique}\n")
        return {"critique": critique}
    else:
        print("\nValidation PASSED.\n")
        return {"critique": "CODE_IS_GOOD"}


# ----------------------------------------
# NODE 3 — IMPROVE
# ----------------------------------------
def improve_code(state: AgentState):
    print(f"\nImproving code (iteration {state['iteration'] + 1})...\n")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Requirements:\n{state['requirements']}\n\n"
                f"Current Code:\n{state['code']}\n\n"
                f"These checks FAILED — fix every single one:\n{state['critique']}\n\n"
                "Return ONLY executable Python code. Do NOT use markdown fences."
            )
        }
    ]
    return {"code": clean_code(call_model(messages)), "iteration": state["iteration"] + 1}


# ----------------------------------------
# ROUTER
# ----------------------------------------
def should_continue(state: AgentState):
    if state["critique"].strip() == "CODE_IS_GOOD":
        print("\nCode approved — saving output.\n")
        return "end"
    if state["iteration"] >= MAX_ITERATIONS:
        print(f"\nMax iterations ({MAX_ITERATIONS}) reached.\n")
        return "end"
    return "improve"


# ----------------------------------------
# SAVE FILE
# ----------------------------------------
def save_outputs(state: AgentState):
    with open("generated_code.py", "w", encoding="utf-8") as f:
        f.write(state["code"])
    print("\nFile saved: generated_code.py\n")
    return {}


# ----------------------------------------
# GRAPH
# ----------------------------------------
graph = StateGraph(AgentState)
graph.add_node("generate", generate_code)
graph.add_node("validate", validate_code_node)
graph.add_node("improve",  improve_code)
graph.add_node("save",     save_outputs)

graph.set_entry_point("generate")
graph.add_edge("generate", "validate")
graph.add_conditional_edges("validate", should_continue,
                             {"improve": "improve", "end": "save"})
graph.add_edge("improve", "validate")
graph.add_edge("save",    END)

app = graph.compile()


# ----------------------------------------
# MAIN
# ----------------------------------------
def main():
    requirements = input("\nDescribe the Python code you want to generate:\n\n\n")
    app.invoke({
        "requirements": requirements,
        "code": "", "critique": "",
        "iteration": 0,
    })
    print("\nGenerated code saved to: generated_code.py")

if __name__ == "__main__":
    main()
