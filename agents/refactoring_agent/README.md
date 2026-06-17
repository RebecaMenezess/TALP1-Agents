# Refactoring Agent

Agente de IA que refatora código Python usando as técnicas do livro **"Refatoração, 2ª Edição"** de Martin Fowler. Roda localmente via **Ollama** — sem APIs pagas.

## Pré-requisitos

- Python 3.10+
- [Ollama](https://ollama.com) instalado e rodando
- Modelo baixado: `ollama pull llama3.1:8b`

## Instalação

```bash
cd agents/refactoring_agent
pip install -r requirements.txt
```

## Como usar

### Opção 1 — Passar um arquivo `.py`

```bash
python main.py caminho/para/seu_codigo.py
```

### Opção 2 — Colar o código diretamente (ctrl+c / ctrl+v)

```bash
python main.py
```

Cole o código quando solicitado e pressione **Ctrl+D** (Mac/Linux) ou **Ctrl+Z + Enter** (Windows) para finalizar.

## O que o agente faz

O agente analisa o código e aplica as técnicas do catálogo de Fowler, incluindo:

| Categoria | Técnicas |
|---|---|
| Composição de funções | Extract Function, Inline Function, Extract Variable, Replace Temp with Query, Split Variable |
| Lógica condicional | Decompose Conditional, Replace Nested Conditional with Guard Clauses, Consolidate Conditional |
| Organização de dados | Rename Variable, Encapsulate Variable, Replace Derived Variable with Query |
| Movimentação de features | Move Function, Split Loop, Replace Loop with Pipeline, Slide Statements |
| APIs | Rename Function, Parameterize Function, Remove Flag Argument, Separate Query from Modifier |
| Classes | Extract Class, Inline Class, Pull Up Method, Push Down Method |

## Saída

O agente retorna:
1. **Refactoring Analysis** — o que foi identificado e quais técnicas serão aplicadas
2. **Código refatorado** — o código completo após a refatoração
3. **Changes Made** — lista detalhada das mudanças e justificativas
