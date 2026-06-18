"""
Definir os contratos de dados (schemas Pydantic) que a LLM deve respeitar.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class CategoriaFalha(str, Enum):
    """Categorias estritas de falha — a LLM não pode inventar valores fora desta lista."""

    ENTRADA_EXTREMA = "ENTRADA_EXTREMA"
    TIPO_INCORRETO = "TIPO_INCORRETO"
    ESTADO_MUTAVEL = "ESTADO_MUTAVEL"
    ESTOURO_CAPACIDADE = "ESTOURO_CAPACIDADE"
    CORRECAO_LOGICA = "CORRECAO_LOGICA"
    NENHUMA = "NENHUMA"


class Severidade(str, Enum):
    CRITICA = "CRITICA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"
    NENHUMA = "NENHUMA"


class ContraexemploOutput(BaseModel):
    """Schema de saída do agente de análise principal."""

    analise_vulnerabilidade: str = Field(
        description=(
            "Explicação da vulnerabilidade encontrada OU justificativa de que o código "
            "cumpre o requisito sem brechas lógicas reais (quando categoria_falha=NENHUMA)."
        )
    )
    categoria_falha: CategoriaFalha = Field(
        description=(
            "Categoria estrita da falha. Use NENHUMA quando o código cumpre o requisito "
            "e não há brecha lógica real a provar."
        )
    )
    severidade: Severidade = Field(
        description=(
            "Severidade estimada. Use NENHUMA quando categoria_falha=NENHUMA."
        )
    )
    nome_funcao_alvo: str = Field(
        description=(
            "Nome EXATO da função Python analisada. "
            "Quando NENHUMA, informe a função principal mesmo assim."
        )
    )
    codigo_pytest: str = Field(
        default="",
        description=(
            "Código pytest que PROVA a falha. OBRIGATÓRIO quando há vulnerabilidade. "
            "DEVE ser string vazia quando categoria_falha=NENHUMA. "
            "Importar com: from codigo_candidato import <funcao>"
        ),
    )

    @model_validator(mode="after")
    def validar_consistencia_nenhuma(self) -> "ContraexemploOutput":
        if self.categoria_falha == CategoriaFalha.NENHUMA:
            if self.codigo_pytest.strip():
                raise ValueError(
                    "codigo_pytest deve ser vazio quando categoria_falha=NENHUMA"
                )
            if self.severidade != Severidade.NENHUMA:
                raise ValueError(
                    "severidade deve ser NENHUMA quando categoria_falha=NENHUMA"
                )
        elif not self.codigo_pytest.strip():
            raise ValueError(
                "codigo_pytest é obrigatório quando categoria_falha != NENHUMA"
            )
        return self


def codigo_declarado_seguro(resultado: dict) -> bool:
    """True quando a LLM declarou explicitamente que o código está seguro."""
    return resultado.get("categoria_falha") == CategoriaFalha.NENHUMA.value
