"""
runner/executor.py
------------------
Responsabilidade ÚNICA: isolar toda operação de I/O e execução de processos.
- Cria um diretório temporário (sandbox) por execução, evitando colisões.
- Escreve os arquivos candidato e teste dentro dessa sandbox.
- Executa o pytest via subprocess e retorna o resultado estruturado.
- Decide se o erro é de SINTAXE (corrigível) ou de FALHA LÓGICA (esperada).

Desta forma, main.py nunca toca diretamente em open() ou subprocess.
"""

import subprocess
import tempfile
import shutil
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ResultadoExecucao:
    """Resultado estruturado de uma rodada do pytest."""

    contraexemplo_confirmado: bool
    """True quando o pytest detectou uma falha no código candidato (objetivo do agente)."""

    erro_sintaxe_no_teste: bool
    """True quando o teste gerado pela IA tem erro de sintaxe (precisa autocorreção)."""

    stdout: str
    """Saída completa do pytest."""

    stderr: str
    """Erros de nível de processo (ex: módulo não encontrado)."""

    returncode: int
    """Código de retorno do subprocess."""

    sandbox_path: str = ""
    """Caminho da sandbox usada nesta execução (para inspeção/debug)."""


class TestRunner:
    """
    Executa testes PyTest em uma sandbox isolada.

    Parâmetros
    ----------
    workspace_dir : str | Path
        Diretório raiz onde as sandboxes serão criadas.
        Padrão: ./workspace (relativo ao cwd).
    keep_sandbox : bool
        Se True, mantém os arquivos após execução (útil para debug).
        Se False, apaga o diretório temporário ao finalizar.
    """

    CANDIDATO_FILENAME = "codigo_candidato.py"
    TESTE_FILENAME = "test_agente_critico.py"

    def __init__(
        self,
        workspace_dir: str | Path = "workspace",
        keep_sandbox: bool = True,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.keep_sandbox = keep_sandbox

    def executar(self, codigo_candidato: str, codigo_teste: str) -> ResultadoExecucao:
        """
        Cria uma sandbox, escreve os arquivos, executa pytest e retorna o resultado.

        A sandbox é um subdiretório único gerado pelo tempfile dentro de workspace/,
        garantindo que execuções paralelas ou em loop não colidam.
        """
        sandbox = Path(
            tempfile.mkdtemp(prefix="qa_run_", dir=self.workspace_dir)
        )
        logger.info("Sandbox criada em: %s", sandbox)

        try:
            # ── Escreve os arquivos na sandbox ──────────────────────────────
            candidato_path = sandbox / self.CANDIDATO_FILENAME
            teste_path = sandbox / self.TESTE_FILENAME

            candidato_path.write_text(codigo_candidato.strip(), encoding="utf-8")
            teste_path.write_text(codigo_teste.strip(), encoding="utf-8")
            logger.info("Arquivos gravados na sandbox.")

            # ── Executa o pytest dentro da sandbox ──────────────────────────
            proc = subprocess.run(
                ["pytest", str(teste_path), "--tb=short", "-q"],
                capture_output=True,
                text=True,
                cwd=str(sandbox),   # cwd = sandbox garante que o import funcione
            )

            saida_completa = proc.stdout + proc.stderr

            # ── Classifica o resultado ───────────────────────────────────────
            erro_sintaxe = self._detectar_erro_sintaxe(saida_completa)
            contraexemplo = self._detectar_contraexemplo(
                proc.returncode, proc.stdout, saida_completa, erro_sintaxe
            )

            return ResultadoExecucao(
                contraexemplo_confirmado=contraexemplo,
                erro_sintaxe_no_teste=erro_sintaxe,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                sandbox_path=str(sandbox),
            )

        finally:
            if not self.keep_sandbox:
                shutil.rmtree(sandbox, ignore_errors=True)
                logger.info("Sandbox removida: %s", sandbox)

    @staticmethod
    def resultado_codigo_seguro() -> ResultadoExecucao:
        """Retorno sintético quando a LLM declarou categoria_falha=NENHUMA."""
        return ResultadoExecucao(
            contraexemplo_confirmado=False,
            erro_sintaxe_no_teste=False,
            stdout="Código declarado seguro (NENHUMA). Execução de pytest omitida.",
            stderr="",
            returncode=0,
            sandbox_path="",
        )

    # ── Helpers privados ────────────────────────────────────────────────────

    @staticmethod
    def _detectar_erro_sintaxe(saida: str) -> bool:
        """
        Erros que impedem a execução do teste (corrigíveis via autocorreção).
        ImportError/ModuleNotFoundError permanecem aqui — a autocorreção pode
        ajustar imports inválidos no teste gerado.
        """
        marcadores = [
            "SyntaxError",
            "IndentationError",
            "ERROR collecting",
            "ImportError",
            "ModuleNotFoundError",
            "invalid syntax",
        ]
        return any(m in saida for m in marcadores)

    @staticmethod
    def _detectar_contraexemplo(
        returncode: int,
        stdout: str,
        saida_completa: str,
        erro_sintaxe: bool,
    ) -> bool:
        """
        Contraexemplo confirmado quando pytest executou corretamente mas reportou falha.

        Regra: returncode != 0 + ("failed" ou "error" na saída) + sem erro de sintaxe.

        AssertionError aponta o traceback para o arquivo de teste (esperado) —
        isso significa que o assert verificou o código candidato e a condição
        não foi satisfeita, ou seja, o bug foi encontrado. Não exigimos que a
        stack aponte para codigo_candidato.py, pois pytest.raises() e assert
        legítimos nunca o fazem quando capturam erros do candidato.
        """
        if erro_sintaxe:
            return False

        if returncode == 0:
            return False

        # returncode 5 = nenhum teste coletado (teste vazio ou mal nomeado)
        if returncode == 5:
            return False

        saida_lower = saida_completa.lower()
        return "failed" in saida_lower or "error" in saida_lower
