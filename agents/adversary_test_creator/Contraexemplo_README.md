# Agente Crítico de Software (Gerador de Contraexemplos)

Este repositório contém o **Agente 2** do projeto, que atua como um engenheiro de QA (Garantia de Qualidade) automatizado. Ele recebe um requisito e um código-fonte candidato **exclusivamente na linguagem Python**, analisa furos lógicos, gera um arquivo de teste em `PyTest` e o executa localmente para provar a existência de falhas (contraexemplos).

---

## 1. Instalação do Python

O projeto exige o **Python 3.10 ou superior**. 
* Acesse o site oficial [python.org/downloads](https://www.python.org/downloads/) e faça a instalação padrão. 

---

## 2. Instalação do Ollama e Llama 3.1

O agente processa a inteligência de forma 100% local através do Ollama.

1. Acesse [ollama.com](https://ollama.com) e baixe o instalador para o seu sistema.
2. Execute a instalação padrão e certifique-se de que o aplicativo do Ollama está aberto e rodando no seu computador.
3. Abra o seu terminal e baixe o modelo padrão rodando o comando:
```bash
ollama pull llama3.1:8b

3. Como Configurar e Rodar o Projeto
Abra o terminal dentro da pasta do projeto e execute os seguintes comandos em ordem:

Bash
# 1. Cria o ambiente virtual de isolamento
python -m venv venv

# 2. Ative o ambiente virtual (rode o comando adequado para o seu terminal)
.\venv\Scripts\activate      # No Windows (PowerShell / CMD)
source venv/bin/activate     # No Linux / macOS

# 3. Instala as dependências necessárias
pip install langchain-ollama langchain pydantic pytest

# 4. Executa o agente
python main.py


4. Como Avaliar a Saída (Modo Mock)
O script vem configurado de fábrica com um cenário simulado (Mock). Ele envia para o agente uma função de cálculo de média em Python que possui um erro de lógica: ela explode caso receba uma lista vazia [].

Ao rodar o código, o sucesso do agente é comprovado quando o terminal exibir:

Plaintext
CONTRAEXEMPLO CONFIRMADO COM SUCESSO!
O código do desenvolvedor FALHOU no teste gerado pelo seu agente.


5. Como Testar um Código Próprio (Sem o Mock)
Caso queira avaliar outro código (obrigatoriamente em Python):

Abra o arquivo main.py.

Localize a seção SIMULAÇÃO DE ENTRADA (MOCK DO AGENTE 1).

Substitua os textos das variáveis mock_requisito e mock_codigo_com_bug pelo seu próprio cenário.

Exemplo:

Python
mock_requisito = "Crie uma função chamada 'buscar_elemento' que retorne o índice de um item em uma lista."

mock_codigo_com_bug = """
def buscar_elemento(lista, item):
    # Bug: Se o item não existir, vai lançar ValueError
    return lista.index(item)
"""
Salve o arquivo e execute python main.py novamente.
