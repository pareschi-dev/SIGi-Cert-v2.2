# Arquitetura do CertHub

## Visão geral

O CertHub foi estruturado em camadas para separar os pontos de entrada, o núcleo reutilizável e os portais específicos.

## Camadas

### 1. Core

Responsável pela infraestrutura comum:

- validação de CPF/CNPJ
- leitura e escrita de PDFs
- logger estruturado
- retry e tratamento de erro
- detecção de CAPTCHA e mediação humana assistida (sem resolução automatizada)
- gestão de browser e proxy

### 2. Portals

Cada portal fica encapsulado em uma classe com a mesma API:

- `name`: identificador do portal
- `url`: URL base
- `emit()`: executa a operação e retorna `EmissionResult`

A base comum garante validação inicial, hash e cálculo de tempo de execução.

### 3. Solvers

Módulos legados não devem resolver CAPTCHA nem criar tokens:

- `CaptchaSolver`: retorna somente `MANUAL_REVIEW`
- `HCaptchaSolver`: compatibilidade que falha de forma segura; nenhuma chamada externa

### 4. CLI

A interface principal é o comando `certhub` / `python -m certhub.main`.

Os comandos principais:

- `--version`
- `listar-portais`
- `validar-config`
- `emitir --portal fgts --documento <doc>`

## Fluxo de emissão

1. Entrada do usuário com portal + documento.
2. Validação do documento.
3. Criação da solicitação (`EmissionRequest`).
4. Se o fluxo estiver implementado, executar no modo de navegador previsto; CAPTCHA exige ação humana.
5. Obter o PDF diretamente do portal, validar `%PDF-` e calcular SHA-256.
6. Gravar os PDFs lado a lado na pasta única `{documento}_{data}_{hora}` sob Downloads.
7. Fluxos ainda incompletos e wrappers legados retornam falha; nunca criam certificados sintéticos.

Os dez IDs do catálogo estão habilitados e roteados para fluxos Playwright individuais. Os fluxos de Receita CPF, CNDT, CGU, comprovante CNPJ, TCU, Simples Nacional e SICAF foram acrescentados; CAPTCHA e certificado/token aguardam ação humana no navegador do operador. A habilitação indica que existe um fluxo e tratamento de erro, não que cada seletor foi certificado contra mudanças dos portais em produção. Antes de uso operacional, valide os seletores e o PDF de cada órgão; a CGU pode exigir sessão autenticada e o SICAF exige certificado/token.

## Extensão

Para adicionar um novo portal, basta:

1. Criar módulo em `src/certhub/portals/`
2. Implementar `emit()` usando a base `BasePortal`
3. Exportar a classe em `src/certhub/portals/__init__.py`
4. registrar no `PORTAL_REGISTRY` do CLI
5. adicionar testes de integração ou de contrato
