# Consulta de certidões no navegador

## Iniciar localmente

1. Instale as dependências Python com `pip install -e .`.
2. Instale o frontend com `cd frontend; npm install; npm run build`.
3. Instale o browser com `python -m playwright install chromium`.
4. Inicie a API com `python -m uvicorn certhub.web:app --host 127.0.0.1 --port 8001`.
5. Abra `http://127.0.0.1:8001`.

## Fluxo

1. O usuário informa CPF ou CNPJ, marca a fonte desejada e inicia a macro; não é solicitado motivo/finalidade.
2. A API valida os dígitos e grava hash e máscara do documento; o identificador completo segue apenas em memória para as tarefas.
3. A API roteia os dez portais para macros próprios. Receita CPF também exige data de nascimento; SICAF exige autenticação com certificado/token. Os portais permanecem independentes, então falha de um não impede os demais.
4. O progresso por site é persistido e transmitido em `/api/v1/consultas/{id}/stream`.
5. A API cria uma pasta única `{documento}_{YYYY-MM-DD}_{HH-MM-SS}` em Downloads e todos os PDFs da consulta ficam lado a lado como `{site_id}.pdf`. Configure outra raiz com `CERTHUB_DOWNLOADS_DIR`.

## CAPTCHA

CAPTCHAs devem ser concluídos por uma pessoa no portal oficial. Não há OCR, solver externo, token simulado ou injeção de token. Antes de usar portais VISÍVEL/CAPTCHA ou TOKEN, inicie o Chrome do operador com depuração remota local habilitada (`--remote-debugging-port=9222`); uma janela comum já aberta não aceita conexão CDP. Confirme que `http://127.0.0.1:9222/json/version` responde. Se a porta for diferente, configure `CERTHUB_CDP_URL` no ambiente ou em `.env` (o backend lê ambos). O backend cria e fecha apenas a aba da consulta; não fecha o navegador nem o contexto do operador.

## Estados

- `pendente`: aguardando vaga no executor local.
- `rodando`: página aberta, formulário em andamento.
- `aguardando_captcha`: depende de ação humana.
- `sucesso`: um PDF real foi recebido do portal, sua assinatura `%PDF-` foi validada e SHA-256 foi calculado.
- `erro`: portal indisponível, seletor alterado ou download não verificável.

## Limites operacionais e LGPD

O executor atual usa `ThreadPoolExecutor` e SQLite local, não Celery/Redis/PostgreSQL. Não há autenticação nem isolamento entre usuários; não exponha a API à rede. O CPF/CNPJ completo fica temporariamente na memória e não é gravado em colunas, resultados ou eventos. O nome da pasta e o caminho absoluto são retornados na API para cumprir o contrato da consulta; mantenha a API local e proteja os registros do operador. Hashes simples de CPF/CNPJ são enumeráveis e continuam sendo dados pessoais; restrinja e retenha o banco conforme a política local.

Os seletores e as etapas dos dez portais podem mudar sem aviso. Os fluxos foram cobertos com testes simulados, mas não foram executadas emissões de ponta a ponta nos dez portais durante a validação. A CGU pode exigir sessão autenticada no portal; nesse caso a automação falha claramente sem solicitar credenciais nem afirmar sucesso. O SICAF exige certificado/token e que o operador deixe a certidão correspondente ao CNPJ aberta antes de confirmar. Antes de uso real, valide os termos e o conteúdo do PDF diretamente na fonte emissora. Um download válido não comprova sozinho a situação jurídica consultada.