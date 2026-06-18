import os
import json
import subprocess
import tempfile
import re

from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser


# ----------------------------------------
# MODELO DE SAÍDA ESTRUTURADA
# ----------------------------------------
class ContraexemploInput(BaseModel):
    analise_vulnerabilidade: str = Field(
        description="Explicação detalhada de qual cenário/caso de borda quebra o código."
    )
    nome_funcao_alvo: str = Field(
        description="O nome exato da função Python que está sendo testada."
    )
    codigo_pytest: str = Field(
        description=(
            "O código completo de um teste usando a biblioteca 'pytest'. "
            "O teste DEVE passar inputs maliciosos (nulos, extremos, tipos errados) "
            "criados para falhar o código original."
        )
    )


MODEL = OllamaLLM(model="llama3.1:8b", temperature=0.1, format="json")
PARSER = JsonOutputParser(pydantic_object=ContraexemploInput)

TEMPLATE = """
Você é um Engenheiro de QA (Garantia de Qualidade) Sênior e um Hacker de chapéu branco especialista em Python.
Sua missão é analisar o REQUISITO e o CÓDIGO fornecidos e encontrar CASOS DE BORDA ou FALHAS LÓGICAS (valores nulos, vazios, extremos, tipos incorretos) que o desenvolvedor esqueceu de tratar.

Você deve gerar um caso de teste usando a biblioteca 'pytest' focado em quebrar ou expor a falha do código fornecido.

{format_instructions}

IMPORTANTE: No campo 'codigo_pytest', lembre-se de importar a função fazendo: `from codigo_candidato import <nome_da_funcao>`.

ATENÇÃO REGRAS CRÍTICAS:
1. Sua resposta deve começar com '{{' e terminar com '}}'.
2. Dentro do campo 'codigo_pytest', use apenas aspas duplas normais e quebras de linha padrão. NUNCA use aspas triplas dentro do JSON, pois isso quebra o formato.

REQUISITO: {requisito}
CÓDIGO DO DESENVOLVEDOR: {codigo}
"""

PROMPT = ChatPromptTemplate.from_template(
    template=TEMPLATE,
    partial_variables={"format_instructions": PARSER.get_format_instructions()},
)

CHAIN = PROMPT | MODEL | PARSER


def _extract_function_name(code: str) -> str:
    """Pega o nome da primeira função definida no código, como fallback."""
    match = re.search(r"def\s+(\w+)\s*\(", code)
    return match.group(1) if match else "main"


def run_critic(requirements: str, code: str, log_callback=None) -> dict:
    """
    Executa o Agente 2 (crítico) sobre um código real.

    Args:
        requirements: o requisito original em linguagem natural (vindo do Agente 1).
        code: o código Python gerado pelo Agente 1.
        log_callback: função opcional chamada com strings de log conforme o agente avança
                      (usada para enviar progresso para a interface web).

    Returns:
        dict com as chaves:
            status: "REPROVADO" | "APROVADO" | "ERRO"
            analise_vulnerabilidade: str
            nome_funcao_alvo: str
            codigo_pytest: str
            stdout_pytest: str
            relatorio_texto: str  (relatório pronto para exibir na UI)
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)

    log("Analisando código com llama3.1:8b para encontrar casos de borda…")

    try:
        resposta_agente = CHAIN.invoke({
            "requisito": requirements,
            "codigo": code,
        })
    except Exception as exc:
        log(f"Erro ao chamar o modelo: {exc}")
        return {
            "status": "ERRO",
            "analise_vulnerabilidade": "",
            "nome_funcao_alvo": "",
            "codigo_pytest": "",
            "stdout_pytest": "",
            "relatorio_texto": f"Erro ao executar o Agente 2: {exc}",
        }

    analise = resposta_agente.get("analise_vulnerabilidade", "")
    nome_funcao = resposta_agente.get("nome_funcao_alvo") or _extract_function_name(code)
    codigo_pytest = resposta_agente.get("codigo_pytest", "")

    log(f"Vulnerabilidade encontrada: {analise[:120]}…" if len(analise) > 120 else f"Vulnerabilidade encontrada: {analise}")
    log("Gerando teste pytest adversarial…")

    # ── grava os arquivos em um diretório temporário e roda pytest ──────────
    with tempfile.TemporaryDirectory() as tmpdir:
        candidato_path = os.path.join(tmpdir, "codigo_candidato.py")
        teste_path = os.path.join(tmpdir, "test_agente_critico.py")

        with open(candidato_path, "w", encoding="utf-8") as f:
            f.write(code.strip())

        with open(teste_path, "w", encoding="utf-8") as f:
            f.write(codigo_pytest.strip())

        log("Executando pytest…")

        try:
            resultado_terminal = subprocess.run(
                ["pytest", "test_agente_critico.py", "-v"],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=30,
            )
            stdout = resultado_terminal.stdout + resultado_terminal.stderr
        except Exception as exc:
            stdout = f"Erro ao executar pytest: {exc}"
            resultado_terminal = None

    bug_confirmado = bool(
        resultado_terminal is not None
        and ("FAILED" in stdout or resultado_terminal.returncode != 0)
    )

    if bug_confirmado:
        status = "REPROVADO"
        log("Bug confirmado — o código falhou no teste adversarial.")
    else:
        status = "APROVADO"
        log("O código resistiu ao teste adversarial.")

    # ── monta um relatório de texto pronto para exibir na interface ─────────
    linhas = [
        "=" * 60,
        "RELATÓRIO DO AGENTE CRÍTICO (Agente 2)",
        "=" * 60,
        f"Status:        {status}",
        f"Função testada: {nome_funcao}",
        "",
        "-" * 60,
        "ANÁLISE DA VULNERABILIDADE",
        "-" * 60,
        analise,
        "",
        "-" * 60,
        "TESTE GERADO (pytest)",
        "-" * 60,
        codigo_pytest,
        "",
        "-" * 60,
        "SAÍDA DO PYTEST",
        "-" * 60,
        stdout.strip(),
        "",
        "=" * 60,
    ]
    relatorio_texto = "\n".join(linhas)

    return {
        "status": status,
        "analise_vulnerabilidade": analise,
        "nome_funcao_alvo": nome_funcao,
        "codigo_pytest": codigo_pytest,
        "stdout_pytest": stdout,
        "relatorio_texto": relatorio_texto,
    }


# ----------------------------------------
# EXECUÇÃO DIRETA (modo standalone, mantém compatibilidade com uso via terminal)
# ----------------------------------------
if __name__ == "__main__":
    mock_requisito = (
        "Crie uma função chamada 'calcular_media' que receba uma lista de "
        "números e retorne a média deles."
    )
    mock_codigo_com_bug = """
def calcular_media(numeros):
    soma = sum(numeros)
    return soma / len(numeros)
"""
    resultado = run_critic(mock_requisito, mock_codigo_com_bug, log_callback=print)
    print(resultado["relatorio_texto"])
