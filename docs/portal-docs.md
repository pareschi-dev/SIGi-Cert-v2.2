# Estado das integrações de portais

Os dez portais estão roteados para fluxos Playwright. Os fluxos só retornam sucesso depois de obter e validar o PDF; seletor ou estado não reconhecido resulta em erro. Os seletores são sujeitos a mudanças e devem ser verificados no portal oficial antes de uso real.

| Portal | Modo definido | Estado da integração |
|---|---|---|
| Receita CNPJ | INTERNO | Macro com consulta em etapas, segunda via e validação de PDF. |
| FGTS/CRF | VISÍVEL | Abre a aba do operador via CDP, executa consulta/visualização, abre a página oficial de impressão e gera automaticamente o PDF na pasta da consulta. |
| CNJ | INTERNO | Pesquisa e emite somente certidão negativa; resultado positivo falha explicitamente. |
| Receita CPF | INTERNO | Solicita CPF e data de nascimento, percorre consulta/resultado e baixa segunda via. |
| CNDT | VISÍVEL/CAPTCHA | Abre no Chrome via CDP, pausa para CAPTCHA, retoma emissão e baixa PDF. |
| CGU | VISÍVEL/CAPTCHA | Seleciona ente privado/certidão, consulta, trata CAPTCHA e baixa o resultado; sessão autenticada pode ser exigida pelo portal. |
| Comprovante CNPJ | VISÍVEL/CAPTCHA | Preenche CNPJ, aguarda hCaptcha/resultado e imprime a página oficial em PDF. |
| TCU | INTERNO | Alterna para CPF quando necessário, emite, aguarda e baixa a certidão. |
| Simples Nacional | INTERNO | Consulta CNPJ, aguarda Situação Atual, abre mais informações e baixa PDF ou imprime a página oficial. |
| SICAF | TOKEN | Aguarda autenticação por certificado/token e confirmação do operador com a certidão aberta; gera PDF da página oficial. |

## Regras de CAPTCHA

- Não usar OCR, serviços pagos de resolução, tokens simulados ou injeção de token.
- O CAPTCHA deve ser resolvido por uma pessoa no portal oficial.
- Portais VISÍVEL, VISÍVEL/CAPTCHA e TOKEN usam o navegador do operador por CDP (`CERTHUB_CDP_URL`, padrão `http://127.0.0.1:9222`).
- Se o seletor, o fluxo ou o download esperado não existir, marcar erro; não declarar sucesso por abrir o portal.

## Arquivos

Cada consulta cria uma pasta `{documento}_{YYYY-MM-DD}_{HH-MM-SS}` em Downloads. Os PDFs usam o ID do portal como nome e ficam diretamente nessa pasta. Nenhum wrapper legado pode fabricar PDF ou retornar sucesso sem obter o arquivo oficial, validar `%PDF-` e calcular SHA-256.
