"""
Orquestrador principal — THIN CONTROLLER.
Responsabilidade: conectar os módulos e exibir o resultado no terminal.
NÃO contém lógica de negócio, prompts, I/O de arquivos ou subprocess.
"""

import json
import logging
import sys

from agent.core import QAAgent
from agent.schema import codigo_declarado_seguro
from runner.executor import TestRunner

# ── Configuração de logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


# ── Configurações ───────────────────────────────────────────────────────────
#
# Trocas o modelo conforme 
MODEL_NAME = "qwen2.5-coder:7b"
MAX_RETRIES_AUTOCORRECAO = 3


# =====================================================================
# SIMULAÇÃO DE ENTRADA (MOCK DO AGENTE 1 / REQUISITO DO USUÁRIO)
# Substitua estas variáveis para testar seu próprio código.
# =====================================================================
mock_requisito = (
    "Crie uma função chamada 'calcular_media' que receba uma lista de números "
    "e retorne a média deles."
)

mock_codigo_com_bug = """
def calcular_media(numeros):
    soma = sum(numeros)
    return soma / len(numeros)
"""


# ── Execução principal ──────────────────────────────────────────────────────

if __name__ == "__main__":
    agente = QAAgent(model_name=MODEL_NAME, max_retries=MAX_RETRIES_AUTOCORRECAO)
    runner = TestRunner(workspace_dir="workspace", keep_sandbox=True)

    print("\n" + "=" * 60)
    print("  AGENTE CRÍTICO DE SOFTWARE — Gerador de Contraexemplos")
    print("=" * 60)

    # ── ETAPA 1: Análise lógica ─────────────────────────────────────────────
    print("\n[ETAPA 1] Analisando código com a LLM...")
    try:
        resultado_agente = agente.analisar(
            requisito=mock_requisito,
            codigo=mock_codigo_com_bug,
        )
    except Exception as exc:
        logger.error("Falha na análise da LLM: %s", exc)
        sys.exit(1)

    print(f"\n  Vulnerabilidade:  {resultado_agente.get('analise_vulnerabilidade', '')}")
    print(f"  Categoria:        {resultado_agente.get('categoria_falha', 'N/A')}")
    print(f"  Severidade:       {resultado_agente.get('severidade', 'N/A')}")
    print(f"  Função alvo:      {resultado_agente.get('nome_funcao_alvo', 'N/A')}")

    # ── ETAPA 2: Execução do teste + loop de autocorreção ───────────────────
    print("\n[ETAPA 2] Executando teste na sandbox...")
    if codigo_declarado_seguro(resultado_agente):
        print("\n  Código declarado SEGURO pela LLM (categoria_falha=NENHUMA).")
        print("  Pytest omitido — nenhum contraexemplo a validar.")
        resultado_exec = TestRunner.resultado_codigo_seguro()
        tentativa = 0
    else:
        resultado_exec = runner.executar(
            codigo_candidato=mock_codigo_com_bug,
            codigo_teste=resultado_agente["codigo_pytest"],
        )
        tentativa = 0

    while resultado_exec.erro_sintaxe_no_teste and tentativa < MAX_RETRIES_AUTOCORRECAO:
        tentativa += 1
        print(f"\n  ⚠ Erro de sintaxe no teste gerado. Acionando autocorreção (tentativa {tentativa}/{MAX_RETRIES_AUTOCORRECAO})...")

        traceback = resultado_exec.stdout + resultado_exec.stderr
        resultado_corrigido = agente.autocorrigir(
            resultado_anterior=resultado_agente,
            traceback_erro=traceback,
            tentativa=tentativa,
        )

        if resultado_corrigido is None:
            print("  Autocorreção esgotada. Abortando.")
            break

        resultado_agente = resultado_corrigido
        resultado_exec = runner.executar(
            codigo_candidato=mock_codigo_com_bug,
            codigo_teste=resultado_agente["codigo_pytest"],
        )

    # ── ETAPA 3: Relatório final ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTADO DA VALIDAÇÃO")
    print("=" * 60)

    if resultado_exec.contraexemplo_confirmado:
        print("\n  ✅ CONTRAEXEMPLO CONFIRMADO COM SUCESSO!")
        print("  O código do desenvolvedor FALHOU no teste gerado pelo agente.\n")

        relatorio = {
            "status": "REPROVADO",
            "modelo_usado": MODEL_NAME,
            "categoria_falha": resultado_agente.get("categoria_falha", ""),
            "severidade": resultado_agente.get("severidade", ""),
            "motivo": resultado_agente.get("analise_vulnerabilidade", ""),
            "tentativas_autocorrecao": tentativa,
            "sandbox": resultado_exec.sandbox_path,
        }
        print(json.dumps(relatorio, indent=4, ensure_ascii=False))

    elif resultado_exec.erro_sintaxe_no_teste:
        print("\n  ⚠ O teste gerado possui erro de sintaxe irrecuperável.")
        print("  Dica: tente um modelo com maior fidelidade de código (qwen2.5-coder).")
        print("\n--- Saída do terminal ---")
        print(resultado_exec.stdout or resultado_exec.stderr)

    elif codigo_declarado_seguro(resultado_agente):
        print("\n  ✅ CÓDIGO APROVADO — auditoria concluiu conformidade com o requisito.")
        print(f"  Justificativa: {resultado_agente.get('analise_vulnerabilidade', '')}")

    else:
        print("\n  O código RESISTIU ao ataque do agente crítico.")
        print("  Nenhuma falha foi disparada pelo caso de teste gerado.")

    if resultado_exec.sandbox_path:
        print(f"\n  Arquivos de inspeção em: {resultado_exec.sandbox_path}")
    print("=" * 60)
