# Agente Crítico de Software

Este projeto implementa um agente local de QA para código Python. Ele recebe um requisito e um código candidato, usa uma LLM local via Ollama para auditar possíveis falhas lógicas, gera um teste PyTest quando encontra um contraexemplo e executa esse teste em uma sandbox de arquivos.

O objetivo não é apenas "quebrar" o código a qualquer custo. O agente agora trabalha com duas saídas possíveis:

- **Contraexemplo confirmado:** a LLM encontrou uma vulnerabilidade real, gerou um PyTest e o executor confirmou a falha.
- **Código declarado seguro:** a LLM retornou `categoria_falha = "NENHUMA"` e `codigo_pytest = ""`, sinalizando que não encontrou brecha lógica dentro do contrato do requisito.

## Arquitetura

```text
adversary_test_creator/
├── main.py                         # Orquestrador manual para um único requisito/código
├── agent/
│   ├── core.py                     # QAAgent: chamadas ao Ollama, parser JSON e retries
│   └── schema.py                   # Contrato Pydantic com Enums estritos
├── prompts/
│   └── templates.py                # Prompt principal e prompt de autocorreção
├── runner/
│   └── executor.py                 # Sandbox em disco + execução do pytest
├── benchmark/
│   ├── avaliar.py                  # Benchmark com Precision, Recall e F1
│   ├── dataset.json                # Dataset principal com casos complexos
│   └── dataset_avancado.json       # Dataset sênior para stress de FP/FN
└── workspace/                      # Sandboxes geradas em runtime
```

## Fluxo De Execução

### `main.py`

```text
main.py
├── instancia QAAgent
├── instancia TestRunner
├── chama agente.analisar(requisito, codigo)
│   ├── usa ANALISE_E_TESTE_TEMPLATE
│   ├── força JSON via Ollama format="json"
│   ├── valida saída com ContraexemploOutput
│   └── tenta novamente até 3 vezes se o JSON/schema falhar
├── se categoria_falha == "NENHUMA"
│   └── não executa pytest
└── senão
    ├── grava codigo_candidato.py e test_agente_critico.py na sandbox
    ├── roda pytest
    └── se houver erro de sintaxe/import, envia traceback para autocorreção
```

### `benchmark/avaliar.py`

```text
avaliar.py
├── lê dataset JSON
├── executa o mesmo fluxo do QAAgent + TestRunner para cada caso
├── contabiliza VP, FP e FN usando deve_falhar
└── salva relatório JSON com Precision, Recall, F1 e taxa de sintaxe válida
```

## Responsabilidades Dos Arquivos

| Arquivo | Responsabilidade |
| --- | --- |
| `main.py` | Entrada manual do sistema. Útil para testar um único requisito e código candidato. |
| `agent/core.py` | Encapsula a comunicação com Ollama, monta as chains LangChain e aplica retry na análise inicial. |
| `agent/schema.py` | Define o contrato de saída da LLM com Pydantic e Enums estritos. |
| `prompts/templates.py` | Define a postura do agente: auditor rigoroso, categorias válidas e regras de JSON/PyTest. |
| `runner/executor.py` | Cria sandbox, escreve arquivos, roda PyTest e classifica o resultado. |
| `benchmark/avaliar.py` | Mede desempenho do agente em datasets curados. |
| `benchmark/dataset.json` | Dataset principal com casos de lógica, estado mutável, parsing e limites. |
| `benchmark/dataset_avancado.json` | Dataset sênior focado em falsos positivos e falsos negativos. |

## Categorias De Falha

O schema aceita apenas estas categorias:

```text
ENTRADA_EXTREMA
TIPO_INCORRETO
ESTADO_MUTAVEL
ESTOURO_CAPACIDADE
CORRECAO_LOGICA
NENHUMA
```

`NENHUMA` é uma saída especial. Quando usada, o agente deve retornar `severidade = "NENHUMA"` e `codigo_pytest = ""`. O sistema interpreta isso como "não há contraexemplo a executar".

## Como Instalar

O projeto exige Python 3.10+ e Ollama instalado.

1. Instale o Ollama em [ollama.com](https://ollama.com).
2. Baixe o modelo recomendado:

```bash
ollama pull qwen2.5-coder:7b
```

3. Crie e ative um ambiente virtual:

```bash
python -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Linux/macOS
source venv/bin/activate
```

4. Instale as dependências:

```bash
pip install langchain-ollama langchain pydantic pytest
```

## Como Rodar

### Execução manual

Na pasta `agents/adversary_test_creator`:

```bash
python main.py
```

Edite os mocks em `main.py` para testar outro requisito ou código candidato.

### Benchmark principal

```bash
python -m benchmark.avaliar --model qwen2.5-coder:7b --dataset benchmark/dataset.json --output benchmark/relatorio_qwen.json
```

### Benchmark avançado

```bash
python -m benchmark.avaliar --model qwen2.5-coder:7b --dataset benchmark/dataset_avancado.json --output benchmark/relatorio_avancado.json
```

## Como O PyTest É Interpretado

O executor considera um contraexemplo confirmado quando:

- o PyTest retorna `returncode != 0`;
- a saída contém `failed` ou `error`, sem diferenciar maiúsculas/minúsculas;
- não houve erro bruto de sintaxe ou coleta do próprio teste (`SyntaxError`, `IndentationError`, `ERROR collecting`, etc.).

Falhas de `assert` são aceitas como evidência válida. Em PyTest, um `AssertionError` aponta para o arquivo de teste, mas isso é esperado: significa que o teste gerado verificou o comportamento do código candidato e encontrou divergência.

## Autocorreção

Se o teste gerado pela LLM tiver erro de sintaxe, indentação, importação ou coleta, o executor marca `erro_sintaxe_no_teste = True`. O orquestrador então chama `agente.autocorrigir(...)`, enviando:

- o `codigo_pytest` anterior;
- o `stdout + stderr` do PyTest;
- o número da tentativa.

O prompt de autocorreção corrige apenas o teste, preservando o mesmo contraexemplo lógico.

## Formato Dos Datasets

Cada caso de benchmark segue este formato:

```json
{
  "id": "caso_001",
  "descricao": "Descrição legível do cenário",
  "requisito": "Contrato que o código deveria cumprir",
  "codigo_com_bug": "def funcao(): ...",
  "bugs_conhecidos": ["off_by_one", "mutacao_estado"],
  "deve_falhar": true
}
```

Use `"deve_falhar": false` para controles negativos. Esses casos medem falsos positivos: códigos corretos que parecem suspeitos, mas não deveriam gerar contraexemplo.

## Limitações Importantes

- A sandbox atual isola arquivos, não o processo Python. O código roda com as permissões do ambiente local.
- Dependências externas como `pandas` ou `requests` só funcionam se já estiverem instaladas no ambiente ativo.
- O agente depende da qualidade do modelo local. Modelos pequenos podem oscilar entre falsos positivos e falsos negativos.
- O benchmark mede se o agente confirmou um contraexemplo por caso, não se encontrou todos os bugs listados em `bugs_conhecidos`.

## Recomendações De Manutenção

- Ajuste `prompts/templates.py` quando o agente ficar agressivo demais ou conservador demais.
- Ajuste `agent/schema.py` quando precisar mudar categorias, severidade ou campos obrigatórios.
- Ajuste `runner/executor.py` quando a leitura do PyTest estiver classificando errado falhas reais ou erros do teste.
- Ajuste `benchmark/dataset.json` para evolução incremental.
- Use `benchmark/dataset_avancado.json` para stress tests de FP/FN antes de considerar o agente estável.