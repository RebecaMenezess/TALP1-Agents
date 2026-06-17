# TALP1 Agents

Este repositório contém 3 agentes de IA. Cada agente tem sua própria pasta com o código, configuração e instruções.

## Agentes

### 1. Gerador de Código 
Gera códigos em Python a partir de descrições em linguagem natural.
### 2. Agente Crítico
Gera testes adversariais para encontrar falhas de um código escrito em Python.
### 3. Agente Refatorador
Analisa e refatora códigos em Python.

___

## Como rodar (interface web)

A pasta `program/` tem uma interface web simples: você digita o que quer em uma caixa de texto e acompanha o agente trabalhando em tempo real, direto no navegador. Abaixo estão os passos que precisam ser executados para conseguir rodar a interface.

### 1. Instalar e rodar o Ollama

Instale Ollama no seu computador e depois rode no terminal:

```bash
ollama pull qwen2.5-coder:7b
```

### 2. Instalar as dependências

```bash
pip install -r agents/code_generator/requirements.txt
pip install flask
```

### 3. Rodar a interface

```bash
cd program
python app.py
```

### 4. Abrir no navegador

```
http://localhost:5000
```

Depois que a aplicação abrir, digite o que você quer gerar (ou clique em um dos exemplos) e clique em **Gerar código**.

---

## Observações finais

Para rodar um agente isoladamente, abra a pasta do agente que você deseja executar e siga as instruções do seu README.md. Os agentes isolados estão dentro da pasta "agents".
