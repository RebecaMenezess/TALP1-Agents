import os
import json
import subprocess

from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser



#parte 1 - Análise de Casos de Borda Lógicos
class ContraexemploInput(BaseModel):
    analise_vulnerabilidade: str = Field(description="Explicação detalhada de qual cenário/caso de borda quebra o código.")
    nome_funcao_alvo: str = Field(description="O nome exato da função Python que está sendo testada.")
    codigo_pytest: str = Field(description="O código completo de um teste usando a biblioteca 'pytest'. O teste DEVE passar inputs maliciosos (nulos, extremos, tipos errados) criados para falhar o código original.")


model = OllamaLLM(model="llama3.1:8b", temperature=0.1, format="json") # Baixa temperatura para maior precisão, evitando respostas criativas ou alucinaçõesa
parser = JsonOutputParser(pydantic_object=ContraexemploInput)

template = """
Você é um Engenheiro de QA (Garantia de Qualidade) Sênior e um Hacker de chapéu branco especialista em Python.
Sua missão é analisar o REQUISITO e o CÓDIGO fornecidos e encontrar CASOS DE BORDA ou FALHAS LÓGICAS (valores nulos, vazios, extremos, tipos incorretos) que o desenvolvedor esqueceu de tratar.

Você deve gerar um caso de teste usando a biblioteca 'pytest' focado em quebrar ou expor a falha do código fornecido.

{format_instructions}

IMPORTANTE: No campo 'codigo_pytest', lembre-se de importar a função fazendo: `from codigo_candidato import <nome_da_funcao>`.

ATENÇÃO REGRAS CRÍTICAS:
1. Sua resposta deve começar com '{{' e terminar com '}}'.
2. Dentro do campo 'codigo_pytest', use apenas aspas duplas normais e quebras de linha padrão. NUNCA use aspas triplas (文字\"\"\"文字) dentro do JSON, pois isso quebra o formato.

REQUISITO: {requisito}
CÓDIGO DO DESENVOLVEDOR: {codigo}
"""

prompt = ChatPromptTemplate.from_template(
    template=template,
    partial_variables={"format_instructions": parser.get_format_instructions()}
)


#Prompt -> Envia pro Modelo -> Traduz o resultado para JSON/Pydantic.
chain = prompt | model | parser 


# =====================================================================
# SIMULAÇÃO DE ENTRADA (MOCK DO AGENTE 1 / REQUISITO DO USUÁRIO)
# =====================================================================
mock_requisito = "Crie uma função chamada 'calcular_media' que receba uma lista de números e retorne a média deles."
# O código abaixo tem um bug clássico: se a lista vier vazia [], o Python lança ZeroDivisionError
mock_codigo_com_bug = """
def calcular_media(numeros):
    soma = sum(numeros)
    return soma / len(numeros)
"""



if __name__ == "__main__":
    print(" [ETAPA 1] Iniciando análise lógica com Llama 3.1...")
    
    try:
        # Chama a inteligência do agente
        resposta_agente = chain.invoke({
            "requisito": mock_requisito,
            "codigo": mock_codigo_com_bug
        })
        
        print("\n Analise do Agente Crítico:")
        print(f"-> {resposta_agente['analise_vulnerabilidade']}")




#parte 2 - Geração de Código de Teste
        print("\n [ETAPA 2] Gravando arquivos para validação física...")
        
        # Salva o código original do desenvolvedor em um arquivo
        with open("codigo_candidato.py", "w", encoding="utf-8") as f:
            f.write(mock_codigo_com_bug.strip())
            
        # Salva o teste PyTest gerado pela IA em outro arquivo
        with open("test_agente_critico.py", "w", encoding="utf-8") as f:
            f.write(resposta_agente['codigo_pytest'].strip())
            
        print("-> Arquivos 'codigo_candidato.py' e 'test_agente_critico.py' criados com sucesso.")

#parte 3 - Execução e Captura de Stack Trace

        print("\n🧪 [ETAPA 3] Executando PyTest via Subprocess para validar o contraexemplo...")
        
        # Executa o pytest no terminal e captura o resultado
        resultado_terminal = subprocess.run(
            ["pytest", "test_agente_critico.py"],
            capture_output=True,
            text=True
        )
        
        print("\n================== RESULTADO DA VALIDAÇÃO ==================")
        
        # Se o pytest encontrou uma falha no código candidato, o contraexemplo funcionou!
        if "FAILED" in resultado_terminal.stdout or resultado_terminal.returncode != 0:
            print(" CONTRAEXEMPLO CONFIRMADO COM SUCESSO!")
            print("O código do desenvolvedor FALHOU no teste gerado pelo seu agente.")
            print("\n--- Relatório Final para enviar ao Agente 1 (Gerador) ---")
            
            relatorio_final = {
                "status": "REPROVADO",
                "motivo": resposta_agente['analise_vulnerabilidade'],
                "erro_detectado_no_terminal": "Falha na execução do teste (ZeroDivisionError ou similar)."
            }
            print(json.dumps(relatorio_final, indent=4, ensure_ascii=False))
            
        else:
            print(" O código resistiu ao ataque do agente crítico.")
            print("Nenhum bug foi disparado pelo caso de teste gerado.")
            
    except Exception as e:
        print(f"\n Ocorreu um erro no pipeline do agente: {e}")
        print("Dica: Certifique-se de que a LLM gerou o JSON no formato correto.")
        
    finally:
        print("\n Arquivos gerados e mantidos na pasta para inspeção.")
        # Limpeza opcional dos arquivos após a execução
        #if os.path.exists("codigo_candidato.py"):
        #    os.remove("codigo_candidato.py")
        #if os.path.exists("test_agente_critico.py"):
        #    os.remove("test_agente_critico.py")