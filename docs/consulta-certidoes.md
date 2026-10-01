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
3. O macro CNJ preenche `#num_cpf_cnpj`, clica `#btnPesquisarRequerido` e, quando disponível, aciona apenas `#btnCertidaoNegativa`. O macro Receita CNPJ preenche `niContribuinte`, clica “Emitir Certidão”, escolhe “Consultar Certidão” se houver certidão válida e baixa a primeira linha pela ação “2ª Via”. O macro FGTS preenche `mainForm:txtInscricao1` somente com dígitos, deixa `mainForm:uf` vazio, clica “Consultar”, abre o link CRF, clica “Visualizar” e “Imprimir”, salvando a página do certificado em PDF. Os outros sete links são manuais enquanto seus macros são desenvolvidos.
4. O progresso por site é persistido e transmitido em `/api/v1/consultas/{id}/stream`.
5. O download só termina em `sucesso` após validar a assinatura `%PDF-`; o arquivo fica em `output/consultas/{consulta_id}/{site}.pdf`.

## CAPTCHA

CAPTCHAs de imagem são capturados e apresentados no painel; a resposta humana é preenchida no formulário original. Para reCAPTCHA e hCaptcha, a pessoa resolve o desafio na janela aberta pelo portal e confirma no painel. Não há OCR, solver externo ou injeção de token neste fluxo. O prazo de espera é de cinco minutos.

## Estados

- `pendente`: aguardando vaga no executor local.
- `rodando`: página aberta, formulário em andamento.
- `aguardando_captcha`: depende de ação humana.
- `sucesso`: um PDF foi realmente baixado e validado estruturalmente.
- `erro`: portal indisponível, seletor alterado ou download não verificável.

## Limites operacionais e LGPD

O executor atual usa `ThreadPoolExecutor` e SQLite local, não Celery/Redis/PostgreSQL. Não há autenticação nem isolamento entre usuários; não exponha a API à rede. O CPF/CNPJ completo fica temporariamente na memória e é entregue ao processo Playwright; não é persistido em tabela nem incluído em eventos. Hashes de CPF/CNPJ não são anônimos e ainda são dados pessoais; restrinja e retenha o banco conforme a política local. Máscara e auditoria ficam registradas.

Os seletores de CNJ, Receita e FGTS foram observados nas páginas correspondentes e podem mudar sem aviso. Os outros sete macros não estão implementados. Antes de uso real, valide os termos e o conteúdo do PDF diretamente na fonte emissora. Um download válido não comprova sozinho a situação jurídica consultada.