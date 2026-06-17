import json
import os
import sys
import threading
import queue
import subprocess
import tempfile

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


# ── Executor do Agente 1 (roda em uma thread) ────────────────────────────────
def run_agent1(run_id: str, requirements: str):
    try:
        # Resolve o caminho do agente com base na estrutura de pastas:
        # app.py está em /program
        # O agente está em /agents/code/generator
        base_dir = os.path.dirname(os.path.abspath(__file__))
        agent_dir = os.path.abspath(os.path.join(base_dir, "..", "agents", "code_generator"))
        
        # Importa o agente inline para que o Flask não precise reiniciar ao alterar o código
        sys.path.insert(0, agent_dir)
        import importlib, types

        _push(run_id, "agent_status", {"agent": 1, "status": "running", "msg": "Gerando código…"})

        # ── faz um monkey-patch nos métodos do agente para capturar as linhas de log ──
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
            result = original_improve(state)
            return result

        def patched_save(state):
            result = original_save(state)
            _push(run_id, "log", {"agent": 1, "msg": "O código gerado salvo."})
            return result

        cga.generate_code  = patched_generate
        cga.validate_code_node = patched_validate
        cga.improve_code   = patched_improve
        cga.save_outputs   = patched_save

        # recria o grafo com os nós modificados (patched)
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

        code = final_state.get("code", "")
        _push(run_id, "agent_status", {"agent": 1, "status": "done", "msg": "Concluído"})
        _push(run_id, "code", {"code": code})

    except Exception as exc:
        _push(run_id, "agent_status", {"agent": 1, "status": "error", "msg": str(exc)})
    finally:
        # restaura os originais
        try:
            cga.generate_code      = original_generate
            cga.validate_code_node = original_validate
            cga.improve_code       = original_improve
            cga.save_outputs       = original_save
        except Exception:
            pass
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

    thread = threading.Thread(target=run_agent1, args=(run_id, requirements), daemon=True)
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
