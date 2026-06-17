"""
benchmark/avaliar.py
--------------------
Responsabilidade: Script de benchmark acadêmico para medir a eficácia do
agente local contra um conjunto de casos de teste curados.

Métricas calculadas:
- Precision: dos testes gerados que executaram, quantos realmente falharam o código?
- Recall:    dos bugs conhecidos no dataset, quantos o agente encontrou?
- F1-Score:  média harmônica de Precision e Recall.
- Taxa de Sintaxe Válida: % de testes que executaram sem SyntaxError.
- Tentativas médias de autocorreção por caso.

Como usar:
    python -m benchmark.avaliar --model qwen2.5-coder:7b --dataset benchmark/dataset.json

Dataset esperado (benchmark/dataset.json):
[
  {
    "id": "caso_001",
    "descricao": "Caso clássico de divisão por zero",
    "requisito": "Crie uma função calcular_media ...",
    "codigo_com_bug": "def calcular_media(nums): ...",
    "bugs_conhecidos": ["lista_vazia", "divisao_por_zero"],
    "deve_falhar": true
  },
  ...
]
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Adiciona o diretório raiz do projeto ao path para imports relativos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core import QAAgent
from runner.executor import TestRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark")


# ── Estruturas de dados ─────────────────────────────────────────────────────

@dataclass
class ResultadoCaso:
    id: str
    contraexemplo_confirmado: bool
    erro_sintaxe: bool
    tentativas_autocorrecao: int
    tempo_segundos: float
    categoria_detectada: str = ""
    severidade_detectada: str = ""
    erro: Optional[str] = None


@dataclass
class RelatorioFinal:
    modelo: str
    total_casos: int
    verdadeiros_positivos: int   # agente detectou bug onde havia bug
    falsos_positivos: int        # agente achou bug onde não havia
    falsos_negativos: int        # agente NÃO detectou bug onde havia
    testes_com_sintaxe_valida: int
    precision: float
    recall: float
    f1: float
    taxa_sintaxe_valida: float
    tempo_medio_segundos: float
    casos: list = field(default_factory=list)


# ── Lógica do benchmark ─────────────────────────────────────────────────────

def executar_benchmark(model_name: str, dataset_path: str) -> RelatorioFinal:
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))

    agente = QAAgent(model_name=model_name, max_retries=3)
    runner = TestRunner(workspace_dir="workspace", keep_sandbox=False)

    resultados: list[ResultadoCaso] = []

    for caso in dataset:
        caso_id = caso["id"]
        deve_falhar = caso.get("deve_falhar", True)
        logger.info("── Avaliando caso: %s ──", caso_id)

        inicio = time.time()
        tentativas = 0
        resultado_caso = ResultadoCaso(
            id=caso_id,
            contraexemplo_confirmado=False,
            erro_sintaxe=False,
            tentativas_autocorrecao=0,
            tempo_segundos=0.0,
        )

        try:
            # 1. Análise principal
            resultado_agente = agente.analisar(
                requisito=caso["requisito"],
                codigo=caso["codigo_com_bug"],
            )
            resultado_caso.categoria_detectada = resultado_agente.get("categoria_falha", "")
            resultado_caso.severidade_detectada = resultado_agente.get("severidade", "")

            # 2. Execução com loop de autocorreção
            resultado_exec = runner.executar(
                codigo_candidato=caso["codigo_com_bug"],
                codigo_teste=resultado_agente["codigo_pytest"],
            )

            while resultado_exec.erro_sintaxe_no_teste and tentativas < agente.max_retries:
                tentativas += 1
                traceback = resultado_exec.stdout + resultado_exec.stderr
                resultado_corrigido = agente.autocorrigir(
                    resultado_anterior=resultado_agente,
                    traceback_erro=traceback,
                    tentativa=tentativas,
                )
                if resultado_corrigido is None:
                    break
                resultado_agente = resultado_corrigido
                resultado_exec = runner.executar(
                    codigo_candidato=caso["codigo_com_bug"],
                    codigo_teste=resultado_agente["codigo_pytest"],
                )

            resultado_caso.contraexemplo_confirmado = resultado_exec.contraexemplo_confirmado
            resultado_caso.erro_sintaxe = resultado_exec.erro_sintaxe_no_teste
            resultado_caso.tentativas_autocorrecao = tentativas

        except Exception as exc:
            logger.error("Erro no caso %s: %s", caso_id, exc)
            resultado_caso.erro = str(exc)

        resultado_caso.tempo_segundos = round(time.time() - inicio, 2)
        resultados.append(resultado_caso)
        logger.info(
            "Caso %s → confirmado=%s | sintaxe_ok=%s | tentativas=%d | %.1fs",
            caso_id,
            resultado_caso.contraexemplo_confirmado,
            not resultado_caso.erro_sintaxe,
            tentativas,
            resultado_caso.tempo_segundos,
        )

    # ── Calcula métricas ────────────────────────────────────────────────────
    casos_com_bug = [c for c in dataset if c.get("deve_falhar", True)]
    casos_sem_bug = [c for c in dataset if not c.get("deve_falhar", True)]

    vp = sum(
        1 for r in resultados
        if r.contraexemplo_confirmado
        and any(c["id"] == r.id and c.get("deve_falhar", True) for c in dataset)
    )
    fp = sum(
        1 for r in resultados
        if r.contraexemplo_confirmado
        and any(c["id"] == r.id and not c.get("deve_falhar", True) for c in dataset)
    )
    fn = len(casos_com_bug) - vp

    precision = vp / (vp + fp) if (vp + fp) > 0 else 0.0
    recall = vp / (vp + fn) if (vp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    sintaxe_valida = sum(1 for r in resultados if not r.erro_sintaxe)
    tempo_medio = sum(r.tempo_segundos for r in resultados) / len(resultados)

    relatorio = RelatorioFinal(
        modelo=model_name,
        total_casos=len(resultados),
        verdadeiros_positivos=vp,
        falsos_positivos=fp,
        falsos_negativos=fn,
        testes_com_sintaxe_valida=sintaxe_valida,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        taxa_sintaxe_valida=round(sintaxe_valida / len(resultados), 4),
        tempo_medio_segundos=round(tempo_medio, 2),
        casos=[asdict(r) for r in resultados],
    )
    return relatorio


# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark do Agente de QA")
    parser.add_argument(
        "--model",
        default="qwen2.5-coder:7b",
        help="Nome do modelo Ollama (ex: llama3.1:8b, qwen2.5-coder:7b)",
    )
    parser.add_argument(
        "--dataset",
        default="benchmark/dataset.json",
        help="Caminho para o dataset de benchmark (JSON)",
    )
    parser.add_argument(
        "--output",
        default="benchmark/relatorio.json",
        help="Caminho para salvar o relatório final",
    )
    args = parser.parse_args()

    relatorio = executar_benchmark(args.model, args.dataset)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(relatorio), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print(f"  RELATÓRIO DE BENCHMARK — Modelo: {relatorio.modelo}")
    print("=" * 60)
    print(f"  Total de casos:         {relatorio.total_casos}")
    print(f"  Verdadeiros Positivos:  {relatorio.verdadeiros_positivos}")
    print(f"  Falsos Positivos:       {relatorio.falsos_positivos}")
    print(f"  Falsos Negativos:       {relatorio.falsos_negativos}")
    print(f"  Precision:              {relatorio.precision:.2%}")
    print(f"  Recall:                 {relatorio.recall:.2%}")
    print(f"  F1-Score:               {relatorio.f1:.2%}")
    print(f"  Sintaxe Válida:         {relatorio.taxa_sintaxe_valida:.2%}")
    print(f"  Tempo médio/caso:       {relatorio.tempo_medio_segundos}s")
    print(f"\n  Relatório salvo em: {output_path}")
    print("=" * 60)
