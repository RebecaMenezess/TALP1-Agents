"""
encapsula toda a comunicação com a LLM. Executa a análise principal e o loop de
autocorreção. Não conhece o sistema de arquivos nem o runner de testes.
"""

import logging
from typing import Optional

from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from agent.schema import ContraexemploOutput
from prompts.templates import ANALISE_E_TESTE_TEMPLATE, AUTOCORRECAO_TEMPLATE

logger = logging.getLogger(__name__)

MAX_TENTATIVAS_ANALISE = 3


class QAAgent:
    """
    Agente de QA baseado em LLM local via Ollama.

    Parâmetros
    ----------
    model_name : str
        Nome do modelo Ollama a ser usado.
        Recomendações por caso de uso:
        - qwen2.5-coder:7b  → melhor fidelidade de JSON + código Python
        - deepseek-coder:6.7b → excelente para análise de lógica
        - llama3.1:8b        → boa opção generalista (padrão original)
    temperature : float
        Temperatura da LLM. Valores baixos (0.05–0.15) reduzem alucinações
        em tarefas de geração de código estruturado.
    max_retries : int
        Número máximo de tentativas no loop de autocorreção.
    """

    def __init__(
        self,
        model_name: str = "qwen2.5-coder:7b",
        temperature: float = 0.1,
        max_retries: int = 3,
    ):
        self.max_retries = max_retries
        self.parser = JsonOutputParser(pydantic_object=ContraexemploOutput)

        self._llm = OllamaLLM(
            model=model_name,
            temperature=temperature,
            format="json",
        )

        # Chain principal: analisa o código e gera o teste
        self._chain_analise = (
            ChatPromptTemplate.from_template(
                template=ANALISE_E_TESTE_TEMPLATE,
                partial_variables={
                    "format_instructions": self.parser.get_format_instructions()
                },
            )
            | self._llm
            | self.parser
        )

        # Chain de autocorreção: recebe o teste quebrado + traceback e corrige
        self._chain_correcao = (
            ChatPromptTemplate.from_template(
                template=AUTOCORRECAO_TEMPLATE,
                partial_variables={
                    "format_instructions": self.parser.get_format_instructions()
                },
            )
            | self._llm
            | self.parser
        )

    def analisar(self, requisito: str, codigo: str) -> dict:
        """
        Executa a análise principal com retry em falhas de parse JSON.

        Raises
        ------
        ValueError
            Se a LLM não retornar um JSON válido após MAX_TENTATIVAS_ANALISE.
        """
        ultima_excecao: Optional[Exception] = None

        for tentativa in range(1, MAX_TENTATIVAS_ANALISE + 1):
            try:
                logger.info(
                    "Iniciando análise com a LLM (tentativa %d/%d)...",
                    tentativa,
                    MAX_TENTATIVAS_ANALISE,
                )
                resultado = self._chain_analise.invoke(
                    {"requisito": requisito, "codigo": codigo}
                )
                logger.info(
                    "Análise concluída. Categoria: %s | Severidade: %s",
                    resultado.get("categoria_falha", "N/A"),
                    resultado.get("severidade", "N/A"),
                )
                return resultado

            except Exception as exc:
                ultima_excecao = exc
                logger.warning(
                    "Falha no parse/validação JSON (tentativa %d/%d): %s",
                    tentativa,
                    MAX_TENTATIVAS_ANALISE,
                    exc,
                )

        raise ValueError(
            f"LLM não retornou JSON válido após {MAX_TENTATIVAS_ANALISE} tentativas: "
            f"{ultima_excecao}"
        )

    def autocorrigir(
        self,
        resultado_anterior: dict,
        traceback_erro: str,
        tentativa: int = 1,
    ) -> Optional[dict]:
        """
        Loop de autocorreção: recebe o resultado anterior e o traceback
        do pytest/python e pede à LLM que corrija o código de teste.

        Retorna None se todas as tentativas falharem.
        """
        if tentativa > self.max_retries:
            logger.error(
                "Autocorreção esgotada após %d tentativas.", self.max_retries
            )
            return None

        logger.info(
            "Tentativa de autocorreção %d/%d...", tentativa, self.max_retries
        )

        try:
            resultado_corrigido = self._chain_correcao.invoke(
                {
                    "teste_anterior": resultado_anterior.get("codigo_pytest", ""),
                    "traceback_erro": traceback_erro,
                }
            )
            logger.info("Autocorreção gerou novo teste. Validando...")
            return resultado_corrigido

        except Exception as exc:
            logger.warning("Falha na tentativa %d de autocorreção: %s", tentativa, exc)
            return None
