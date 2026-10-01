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
- detecção e resolução de captcha
- gestão de browser e proxy

### 2. Portals

Cada portal fica encapsulado em uma classe com a mesma API:

- `name`: identificador do portal
- `url`: URL base
- `emit()`: executa a operação e retorna `EmissionResult`

A base comum garante validação inicial, hash e cálculo de tempo de execução.

### 3. Solvers

Módulos específicos usados para classificar ou resolver captchas:

- `OCRSolver`: OCR de texto simples
- `HCaptchaSolver`: integração com 2Captcha

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
4. Resolução do captcha quando necessário.
5. Emissão e download do PDF.
6. Persistência do arquivo e cálculo do SHA-256.
7. Registro do resultado em `EmissionResult`.

## Extensão

Para adicionar um novo portal, basta:

1. Criar módulo em `src/certhub/portals/`
2. Implementar `emit()` usando a base `BasePortal`
3. Exportar a classe em `src/certhub/portals/__init__.py`
4. registrar no `PORTAL_REGISTRY` do CLI
5. adicionar testes de integração ou de contrato
