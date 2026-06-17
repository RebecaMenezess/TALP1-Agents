"""
agent/schema.py
---------------
Responsabilidade ÚNICA: definir os contratos de dados (schemas Pydantic)
que a LLM deve respeitar. Separar os schemas da lógica facilita a evolução
independente do contrato sem quebrar o pipeline.
"""

from pydantic import BaseModel, Field


class ContraexemploOutput(BaseModel):
    """Schema de saída do agente de análise principal."""

    analise_vulnerabilidade: str = Field(
        description=(
            "Explicação detalhada de qual cenário/caso de borda quebra o código, "
            "incluindo a categoria da falha (entrada extrema, estado mutável, etc.)."
        )
    )
    categoria_falha: str = Field(
        description=(
            "Categoria principal da falha encontrada. Valores possíveis: "
            "ENTRADA_EXTREMA, TIPO_INCORRETO, ESTADO_MUTAVEL, LIMITE_CONTRATO, "
            "CONCORRENCIA, OVERFLOW, UNICODE, OUTRO."
        )
    )
    severidade: str = Field(
        description=(
            "Severidade estimada da falha. Valores: CRITICA, ALTA, MEDIA, BAIXA."
        )
    )
    nome_funcao_alvo: str = Field(
        description="O nome EXATO da função Python que está sendo testada."
    )
    codigo_pytest: str = Field(
        description=(
            "Código completo de um teste usando pytest. "
            "Deve importar com 'from codigo_candidato import <funcao>' e "
            "usar pytest.raises() ou assert para capturar a falha."
        )
    )
