import json
import os
import sys
import threading
import queue

from flask import Flask, render_template, request, Response, stream_with_context

app = Flask(__name__, template_folder='.')

# ── fila de stream por requisição ─────────────────────────────────────────────
# Cada execução de geração ganha sua própria fila; o SSE a esvazia.
_runs: dict[str, queue.Queue] = {}


def _push(run_id: str, event: str, data: dict):
    if run_id in _runs:
        _runs[run_id].put({"event": event, "data": data})


def _done(run_id: str):
    if run_id in _runs:
        _runs[run_id].put(None)          # sentinela


# ── caminhos dos agentes ──────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT1_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "agents", "code_generator"))
AGENT2_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "agents", "adversary_test_creator"))
AGENT3_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "agents", "refactoring_agent"))


# ── Agente 1 — gerador de código ──────────────────────────────────────────────
def run_agent1(run_id: str, requirements: str) -> str:
    """Executa o Agente 1 e retorna o código gerado (string vazia em caso de erro)."""
    sys.path.insert(0, AGENT1_DIR)
    import code_generator_agent as cga

    original_validate = cga.validate_code_node
    original_generate = cga.generate_code
    original_improve  = cga.improve_code
    original_save     = cga.save_outputs

    def patched_generate(state):
        _push(run_id, "log", {"agent": 1, "msg": "Chamando LLM para gerar código…"})
        result = original_generate(state)
        _push(run_id, "log", {"agent": 1, "msg": "Código gerado."})
        return result

    def patched_validate(state):
        _push(run_id, "log", {"agent": 1, "msg": f"Validando (iteração {state['iteration']})…"})
        result = original_validate(state)
        if result["critique"] == "CODE_IS_GOOD":
            _push(run_id, "log", {"agent": 1, "msg": "Validação aprovada."})
        else:
            issues = result["critique"].count("•")
            _push(run_id, "log", {"agent": 1, "msg": f"{issues} problema(s) encontrado(s)."})
        return result

    def patched_improve(state):
        _push(run_id, "log", {"agent": 1, "msg": f"Melhorando código (iteração {state['iteration'] + 1})…"})
        return original_improve(state)

    def patched_save(state):
        result = original_save(state)
        _push(run_id, "log", {"agent": 1, "msg": "generated_code.py salvo."})
        return result

    cga.generate_code      = patched_generate
    cga.validate_code_node = patched_validate
    cga.improve_code       = patched_improve
    cga.save_outputs       = patched_save

    try:
        from langgraph.graph import StateGraph, END
        graph = StateGraph(cga.AgentState)
        graph.add_node("generate", cga.generate_code)
        graph.add_node("validate", cga.validate_code_node)
        graph.add_node("improve",  cga.improve_code)
        graph.add_node("save",     cga.save_outputs)
        graph.set_entry_point("generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges("validate", cga.should_continue,
                                    {"improve": "improve", "end": "save"})
        graph.add_edge("improve", "validate")
        graph.add_edge("save",    END)
        agent_app = graph.compile()

        final_state = agent_app.invoke({
            "requirements": requirements,
            "code": "", "critique": "", "iteration": 0,
        })
        return final_state.get("code", "")
    finally:
        cga.generate_code      = original_generate
        cga.validate_code_node = original_validate
        cga.improve_code       = original_improve
        cga.save_outputs       = original_save
        if AGENT1_DIR in sys.path:
            sys.path.remove(AGENT1_DIR)
        sys.modules.pop("code_generator_agent", None)


# ── Agente 2 — crítico ────────────────────────────────────────────────────────
def run_agent2(run_id: str, requirements: str, code: str) -> dict:
    """Executa o Agente 2 e retorna o dict de resultado (ver critic_main.run_critic)."""
    sys.path.insert(0, AGENT2_DIR)
    try:
        import critic_main

        def log_callback(msg: str):
            _push(run_id, "log", {"agent": 2, "msg": msg})

        return critic_main.run_critic(requirements, code, log_callback=log_callback)
    finally:
        if AGENT2_DIR in sys.path:
            sys.path.remove(AGENT2_DIR)
        sys.modules.pop("critic_main", None)


# ── Agente 3 — refatorador ────────────────────────────────────────────────────
def run_agent3(run_id: str, code: str, critic_report: str) -> dict:
    """Executa o Agente 3 e retorna o dict de resultado (ver refactor_main.run_refactor)."""
    sys.path.insert(0, AGENT3_DIR)
    try:
        import refactor_main

        def log_callback(msg: str):
            _push(run_id, "log", {"agent": 3, "msg": msg})

        return refactor_main.run_refactor(code, critic_report=critic_report, log_callback=log_callback)
    finally:
        if AGENT3_DIR in sys.path:
            sys.path.remove(AGENT3_DIR)
        sys.modules.pop("refactor_main", None)


# ── Orquestrador — roda os 3 agentes em sequência (em uma thread) ────────────
def run_pipeline(run_id: str, requirements: str):
    try:
        # ── Agente 1 ──────────────────────────────────────────────────────
        _push(run_id, "agent_status", {"agent": 1, "status": "running", "msg": "Gerando código…"})
        code = run_agent1(run_id, requirements)

        if not code.strip():
            _push(run_id, "agent_status", {"agent": 1, "status": "error", "msg": "Nenhum código foi gerado."})
            return

        _push(run_id, "agent_status", {"agent": 1, "status": "done", "msg": "Concluído"})
        _push(run_id, "code", {"code": code})

        # ── Agente 2 ──────────────────────────────────────────────────────
        _push(run_id, "agent_status", {"agent": 2, "status": "running", "msg": "Analisando código e gerando testes…"})
        critic_result = run_agent2(run_id, requirements, code)

        if critic_result["status"] == "ERRO":
            _push(run_id, "agent_status", {"agent": 2, "status": "error", "msg": "Erro ao executar o Agente 2."})
        else:
            _push(run_id, "agent_status", {"agent": 2, "status": "done", "msg": f"Concluído — {critic_result['status']}"})

        _push(run_id, "report", {"report": critic_result["relatorio_texto"]})

        # ── Agente 3 ──────────────────────────────────────────────────────
        _push(run_id, "agent_status", {"agent": 3, "status": "running", "msg": "Refatorando código…"})
        refactor_result = run_agent3(run_id, code, critic_result.get("relatorio_texto", ""))

        if refactor_result["refactored_code"]:
            _push(run_id, "agent_status", {"agent": 3, "status": "done", "msg": "Concluído"})
            _push(run_id, "refactored_code", {"code": refactor_result["refactored_code"]})
        else:
            _push(run_id, "agent_status", {"agent": 3, "status": "error", "msg": "Não foi possível extrair o código refatorado."})

        _push(run_id, "refactor_analysis", {"analysis": refactor_result["full_analysis"]})

    except Exception as exc:
        _push(run_id, "agent_status", {"agent": 0, "status": "error", "msg": str(exc)})
    finally:
        _done(run_id)


# ── Rotas ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    requirements = (data or {}).get("requirements", "").strip()
    if not requirements:
        return {"error": "Nenhum requisito fornecido"}, 400

    import uuid
    run_id = str(uuid.uuid4())
    _runs[run_id] = queue.Queue()

    thread = threading.Thread(target=run_pipeline, args=(run_id, requirements), daemon=True)
    thread.start()

    return {"run_id": run_id}


@app.route("/stream/<run_id>")
def stream(run_id: str):
    if run_id not in _runs:
        return {"error": "Execução desconhecida"}, 404

    def event_stream():
        q = _runs[run_id]
        while True:
            item = q.get()
            if item is None:
                yield "event: done\ndata: {}\n\n"
                _runs.pop(run_id, None)
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
