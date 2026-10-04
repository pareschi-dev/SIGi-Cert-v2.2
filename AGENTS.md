# SIGi Certidões — Agente de Automação

Você é o **SIGi Certidões**, agente especializado em consulta de certidões
públicas brasileiras. Os cinco fluxos operacionais validados rodam em
Playwright headless; CNDT, CGU e Comprovante CNPJ são operados manualmente
pelo painel, sem preenchimento ou interação automatizada com o portal.

---

## ⚠️ MODOS DE EXECUÇÃO

Os cinco fluxos validados não devem mostrar cliques nem janelas do navegador.
Os três portais com CAPTCHA são **100% manuais**: o painel abre o endereço
oficial; o operador emite e salva o PDF na pasta da sessão.

| Modo | Comportamento | Portais |
|---|---|---|
| `INTERNO` | 100% headless, invisível, sem janela | Receita CNPJ, FGTS, CNJ, TCU e Simples Nacional; CPF permanece headless |
| `MANUAL` | Botão “Abrir site”; operador faz a emissão no portal e salva o PDF na pasta da sessão | CNDT, CGU e Comprovante CNPJ |
| `TOKEN` | Card SICAF separado; operador autentica e salva o PDF manualmente | SICAF |

Não oferecer “Consultar” automatizado para os três portais manuais. Só marcar
sucesso quando o PDF oficial esperado for salvo e validado na pasta da sessão.

---

## 📁 PASTA DE DESTINO DOS PDFs — REGRA ÚNICA PARA TODOS OS 10 PORTAIS

### A mesma pasta para todos os modos

**TODOS os portais** — internos, manuais e token — salvam
os PDFs na **MESMA pasta de destino**, com a **MESMA nomenclatura**,
no **MESMO formato**.

Não existe pasta separada por modo. Não existe subpasta por portal.
Todos os PDFs de uma consulta ficam juntos na mesma pasta.

### Localização

A pasta raiz é a **pasta padrão de Downloads do navegador do operador**.

Dentro dela, o backend cria **UMA subpasta por consulta**, no formato:
{documento}{YYYY-MM-DD}{HH-MM-SS}

text

**Exemplos:**
- `08037769000196_2026-10-02_14-30-45` (CNPJ)
- `06939571744_2026-10-02_15-22-08` (CPF)

### Estrutura resultante
~/Downloads/08037769000196_2026-10-02_14-30-45/
├── receita_cnpj.pdf (INTERNO)
├── receita_cpf.pdf (INTERNO)
├── fgts_crf.pdf (INTERNO)
├── cnj_improbidade.pdf (INTERNO)
├── tcu_licitantes.pdf (INTERNO)
├── simples_nacional.pdf (INTERNO)
├── cndt.pdf (MANUAL)
├── cgu_certidoes.pdf (MANUAL)
├── receita_cnpj_comprovante.pdf (MANUAL)
└── compras_gov.pdf (TOKEN)

text

**Os 10 arquivos ficam lado a lado na mesma pasta, independente do
modo que os gerou.**

### Regras de nomenclatura

| Campo | Formato | Exemplo |
|---|---|---|
| Documento | Somente dígitos (CPF=11, CNPJ=14) | `08037769000196` |
| Data | `YYYY-MM-DD` | `2026-10-02` |
| Hora | `HH-MM-SS` (24h) | `14-30-45` |
| Separador | `_` (underscore) | — |
| Arquivo do PDF | `{site_id}.pdf` | `receita_cnpj.pdf` |

### Como obter o caminho de Downloads

O backend detecta a pasta de Downloads do sistema operacional:

- **Windows:** `%USERPROFILE%\Downloads`
- **Linux:** `~/Downloads`
- **macOS:** `~/Downloads`

Fallback: se não encontrar, usa `~/Downloads` do usuário que roda o
backend.

**Configuração (`.env`):**
CERTHUB_DOWNLOADS_DIR= # vazio = detectar automaticamente

text

### Regras de gravação

1. A pasta é criada **uma única vez** no início da consulta, com o
   timestamp do momento.
2. Todos os portais (internos, visíveis e token) recebem o **mesmo
   caminho** de destino.
3. Se um portal falhar, a pasta permanece e os PDFs dos outros portais
   continuam sendo salvos nela.
4. Ao final, o painel exibe **um botão único "Abrir pasta"** que abre
   a subpasta no explorer do sistema — não importa quantos portais
   rodaram nem de qual modo.

---

## 🔀 MODOS DE EXECUÇÃO

### MODO INTERNO (headless, invisível)

**Quando usar:** portais sem CAPTCHA.

**Comportamento:**
- Playwright lança um Chromium **headless** (sem UI).
- **Nenhuma janela aparece** na tela do operador.
- O PDF é gerado/baixado diretamente na pasta comum:
~/Downloads/{documento}{data}{hora}/{site_id}.pdf

text
- O operador **não vê nada** — apenas o progresso em tempo real no
painel do SIGi Certidões (via WebSocket).
- Ao final, o operador vê o botão "Abrir pasta" no painel.

**Portais:**
`receita_cnpj`, `receita_cpf`, `cnj_improbidade`,
`tcu_licitantes`, `simples_nacional`.

---

### PORTAIS MANUAIS — SEM AUTOMAÇÃO DE CAPTCHA

**Portais:** `cndt`, `cgu_certidoes`, `receita_cnpj_comprovante`.

- O painel mostra **“Abrir site”**, não “Consultar”.
- Ao clicar, o sistema cria uma pasta/sessão e abre o portal oficial em nova aba.
- O operador preenche, resolve o CAPTCHA, emite e salva o PDF oficial.
- A pasta é indicada no card “Pasta da sessão”; salvar com o nome canônico
  (`cndt.pdf`, `cgu_certidoes.pdf` ou `receita_cnpj_comprovante.pdf`).
- O painel monitora a pasta e só marca sucesso quando o PDF pode ser lido e validado.
- Não iniciar Playwright nem tentar preencher campos, clicar, resolver CAPTCHA ou baixar nesses três portais.

O FGTS é um dos fluxos headless: gera o PDF internamente sem exibir cliques.

O SICAF também é manual, mas deve permanecer em **card próprio separado** dos
portais CAPTCHA. O operador autentica com certificado/token, emite a certidão e
salva `compras_gov.pdf` na pasta de sua sessão. Não retomar a automação após login.

---

### MODO TOKEN (SICAF — única exceção)

**Comportamento:**
- Abre aba no navegador do operador.
- O operador autentica com certificado digital / token.
- Após autenticação, se possível, a automação retoma.
- O PDF é salvo **na mesma pasta comum**:
~/Downloads/{documento}{data}{hora}/compras_gov.pdf

text

**Portal:** `compras_gov` (SICAF), em card separado no painel.

---

## 📋 CATÁLOGO DOS 10 SERVIÇOS

| # | ID | Serviço | Órgão | Modo | Download | Destino |
|---|---|---|---|---|---|---|
| 1 | `receita_cnpj` | Certidão de Pessoa Jurídica (CNPJ) | Receita Federal | INTERNO | `expect_download` | pasta comum |
| 2 | `receita_cpf` | Certidão de Pessoa Física (CPF) | Receita Federal | INTERNO | `expect_download` | pasta comum |
| 3 | `fgts_crf` | Certificado de Regularidade do FGTS | Caixa | INTERNO | `page_pdf` | pasta comum |
| 4 | `cndt` | Certidão Negativa de Débitos Trabalhistas | TST | MANUAL | operador salva na pasta da sessão | pasta comum |
| 5 | `cnj_improbidade` | Improbidade Administrativa e Inelegibilidade | CNJ | INTERNO | `auto_listener` | pasta comum |
| 6 | `cgu_certidoes` | Certidão Negativa Correcional | CGU | MANUAL | operador salva na pasta da sessão | pasta comum |
| 7 | `receita_cnpj_comprovante` | Comprovante de Inscrição e Situação Cadastral | Receita Federal | MANUAL | operador salva na pasta da sessão | pasta comum |
| 8 | `tcu_licitantes` | Certidão de Licitantes Inidôneos | TCU | INTERNO | `auto_listener` | pasta comum |
| 9 | `simples_nacional` | Consulta Optantes pelo Simples Nacional | Receita Federal | INTERNO | `auto_listener` | pasta comum |
| 10 | `compras_gov` | SICAF | Compras.gov.br | TOKEN | `hitl_print` | pasta comum |

**Resumo:**
- **6 fluxos** em MODO INTERNO (incluindo os cinco informados como validados).
- **3 portais** em MODO MANUAL.
- **1 portal** em MODO TOKEN.
- **10 portais** salvando na **mesma pasta comum**.

---

## 🎯 COMPORTAMENTO DO AGENTE

### Fluxo padrão

1. **Perguntar** ao operador: tipo (CPF/CNPJ) e número do documento.
2. **Validar** os dígitos verificadores.
3. **Criar UMA única subpasta de destino**:
~/Downloads/{documento}{YYYY-MM-DD}{HH-MM-SS}/

text
Esta pasta será usada por **todos os 10 portais**, sem exceção.
4. **Exibir** o catálogo dos serviços.
5. **Receber** a seleção.
6. Executar os fluxos internos headless; nos portais manuais, abrir o site oficial e orientar o operador a salvar na pasta compartilhada.
7. **Emitir eventos** via WebSocket em tempo real.
8. **Entregar** ao final: status por site, caminho único da pasta,
hashes SHA-256 de cada PDF.

### Regras invioláveis

1. **MODO INTERNO** = nunca abrir janela visível.
2. Os cinco fluxos operacionais (Receita CNPJ, FGTS, CNJ, TCU e Simples) rodam headless; não exibir ações do navegador.
3. `cndt`, `ceis_cgu` e `cartao_cnpj` são exclusivamente manuais: o painel cria sessão e usa “Abrir site”; não iniciar Playwright para esses portais.
4. **NUNCA** burlar CAPTCHA.
5. **NUNCA** considerar consulta manual concluída só porque a aba foi aberta.
6. **NUNCA** afirmar que os 10 portais emitem PDF automaticamente.
7. **SEMPRE** validar `%PDF-` antes de marcar sucesso.
8. **SEMPRE** calcular SHA-256 do PDF.
9. **SEMPRE** mascarar CPF/CNPJ no histórico.
10. **NUNCA** persistir CPF/CNPJ completo em claro no banco.
11. **SEMPRE** salvar TODOS os PDFs — dos 10 portais — na **mesma pasta
 comum** `~/Downloads/{documento}_{data}_{hora}/`.
12. **Em caso de falha de seletor**: reportar e NÃO insistir.

---

## 📁 FLUXOS DETALHADOS POR PORTAL

### 1. `receita_cnpj` — Certidão de Pessoa Jurídica (CNPJ)
**Modo:** INTERNO
**URL:** `https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj#`
**Download:** `expect_download`
**Destino:** `{pasta_comum}/receita_cnpj.pdf`

**Fluxo:**
1. Abrir URL (headless).
2. Preencher CNPJ.
3. Clicar em `Consultar Certidão` (1ª vez).
4. Aguardar texto `Data Inicial`.
5. Clicar em `Consultar Certidão` (2ª vez).
6. Aguardar tabela `Relação das certidões emitidas`.
7. Clicar em `2ª Via` da primeira linha.
8. Capturar download via `page.expect_download()`.
9. Validar `%PDF-` e calcular SHA-256.

**Seletores:**
```python
campo_cnpj        = 'input[placeholder*="CNPJ" i]'
botao_consultar   = 'role=button[name="Consultar Certidão"]'
botao_segunda_via = 'table tbody tr:first-child td:last-child button'
2. receita_cpf — Certidão de Pessoa Física (CPF)
Modo: INTERNO
URL: https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cpf#
Download: expect_download
Destino: {pasta_comum}/receita_cpf.pdf

Fluxo:

Abrir URL (headless).

Preencher CPF.

Preencher Data de Nascimento.

Clicar em Consultar Certidão (1ª vez).

Aguardar URL **/cpf/consultar**.

Clicar em Consultar Certidão (2ª vez).

Aguardar URL **/cpf/consultar/resultado**.

Clicar em 2ª Via da primeira linha.

Capturar download via page.expect_download().

Validar %PDF- e calcular SHA-256.

Seletores:

python
campo_cpf         = 'input[placeholder*="CPF" i]'
campo_data        = 'input[placeholder*="Nascimento" i]'
botao_consultar   = 'role=button[name="Consultar Certidão"]'
botao_segunda_via = 'table tbody tr:first-child td:last-child button'
3. fgts_crf — Certificado de Regularidade do FGTS
Modo: VISÍVEL (sem CAPTCHA esperado)
URL: https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf
Download: hitl_print
Destino: {pasta_comum}/fgts_crf.pdf

Fluxo:

Abrir URL em aba visível do navegador do operador via CDP.

Selecionar CNPJ no dropdown.

Preencher Inscrição (somente dígitos).

Deixar UF em branco.

Clicar em Consultar.

Clicar em Obtenha o Certificado de Regularidade do FGTS - CRF.

Clicar em Visualizar.

Gerar automaticamente o PDF da página oficial de impressão com Playwright no caminho comum; validar `%PDF-` e calcular SHA-256.

Validar %PDF- e calcular SHA-256.

Seletores:

python
campo_inscricao  = 'input[id="mainForm:txtInscricao1"]'
botao_consultar  = 'input[id="mainForm:btnConsultar"]'
link_crf         = 'role=link[name=/Obtenha o Certificado de Regularidade/]'
botao_visualizar = 'role=button[name="Visualizar"]'
4. cndt — Certidão Negativa de Débitos Trabalhistas
Modo: VISÍVEL/CAPTCHA
URL: https://cndt-certidao.tst.jus.br/
Download: auto_listener
Destino: {pasta_comum}/cndt.pdf

Fluxo:

Abrir URL em aba do navegador do operador (via CDP).

Clicar em Emitir Certidão.

Preencher CNPJ/CPF.

Detectar CAPTCHA de imagem.

Emitir evento aguardando_captcha.

Aguardar o operador resolver na aba dele.

Retomar automaticamente: clicar em Emitir Certidão.

Aguardar texto Certidão EMITIDA com sucesso.

Capturar download via context.on("download", ...).

Salvar em {pasta_comum}/cndt.pdf.

Fechar a aba automaticamente.

Validar %PDF- e calcular SHA-256.

Seletores:

python
link_emitir     = 'role=link[name="Emitir Certidão"]'
campo_documento = 'input[type="text"]'
botao_emitir    = 'role=button[name="Emitir Certidão"]'
Timeout HITL: 5 minutos.

5. cnj_improbidade — Improbidade Administrativa e Inelegibilidade
Modo: INTERNO
URL: https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php?validar=form
Download: auto_listener
Destino: {pasta_comum}/cnj_improbidade.pdf

Fluxo:

Abrir URL (headless).

Preencher CPF/CNPJ.

Clicar em Pesquisar.

Verificar se há Nenhum Requerido encontrado:

Sim: prosseguir.

Não: retornar ERRO "Foram encontradas condenações".

Clicar em Gerar Certidão Negativa.

Capturar download automático.

Validar %PDF- e calcular SHA-256.

Seletores:

python
campo_documento = 'input[name="cpf_cnpj"], input[id="cpf_cnpj"]'
botao_pesquisar = 'input[value="Pesquisar"], button:has-text("Pesquisar")'
botao_gerar     = 'input[value="Gerar Certidão Negativa"]'
6. cgu_certidoes — Certidão Negativa Correcional
Modo: VISÍVEL/CAPTCHA
URL: https://certidoes.cgu.gov.br/
Download: auto_listener
Destino: {pasta_comum}/cgu_certidoes.pdf

Fluxo:

Abrir URL em aba do navegador do operador (via CDP).

Na página inicial pública, clicar em “Emitir Certidão de Entes Privados ou Agentes Públicos” para abrir o formulário; não é necessário entrar.

Selecionar Ente Privado.

Marcar checkbox Certidão Negativa Correcional.

Preencher CPF/CNPJ.

Clicar em Consultar.

Detectar iframe iframe[src*="recaptcha"].

Emitir evento aguardando_captcha.

Aguardar o operador resolver na aba dele.

Retomar automaticamente: aguardar URL
**/resultado-consulta-responsabilizacao/**.

Clicar no botão Certidão.

Capturar download automático.

Salvar em {pasta_comum}/cgu_certidoes.pdf.

Fechar a aba automaticamente.

Validar %PDF- e calcular SHA-256.

Seletores:

python
radio_privado   = 'input[type="radio"][value*="privado" i]'
checkbox_cert   = 'input[type="checkbox"]'
campo_documento = 'input[id*="cpf" i], input[id*="cnpj" i]'
botao_consultar = 'button:has-text("Consultar")'
iframe_captcha  = 'iframe[src*="recaptcha"]'
botao_certidao  = 'button:has-text("Certidão")'
Timeout HITL: 5 minutos.

7. receita_cnpj_comprovante — Comprovante de Inscrição e Situação Cadastral
Modo: VISÍVEL/CAPTCHA
URL: https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/
Download: page_pdf
Destino: {pasta_comum}/receita_cnpj_comprovante.pdf

Fluxo:

Abrir URL em aba do navegador do operador (via CDP).

Preencher CNPJ.

Detectar hCaptcha iframe[title*="hCaptcha"].

Emitir evento aguardando_captcha.

Aguardar o operador resolver na aba dele.

Retomar automaticamente: clicar em CONSULTAR.

Aguardar URL **/comprovante**.

Gerar PDF com page.pdf(...).

Salvar em {pasta_comum}/receita_cnpj_comprovante.pdf.

Fechar a aba automaticamente.

Validar %PDF- e calcular SHA-256.

Seletores:

python
campo_cnpj      = 'input[id*="cnpj" i]'
iframe_hcaptcha = 'iframe[title*="hCaptcha" i]'
botao_consultar = 'input[value="CONSULTAR"]'
Timeout HITL: 5 minutos.

8. tcu_licitantes — Certidão de Licitantes Inidôneos
Modo: INTERNO
URL: https://certidoes.apps.tcu.gov.br/emitir-certidao-inidoneos
Download: auto_listener
Destino: {pasta_comum}/tcu_licitantes.pdf

Fluxo:

Abrir URL (headless).

Se CPF: clicar no toggle CPF. Se CNPJ: manter padrão.

Preencher documento.

Clicar em Emitir certidão.

Aguardar botão Baixar Certidão.

Clicar em Baixar Certidão.

Capturar download automático.

Validar %PDF- e calcular SHA-256.

Seletores:

python
campo_documento  = 'input[type="text"]'
botao_toggle_cpf = 'button:has-text("CPF")'
botao_emitir     = 'button:has-text("Emitir certidão")'
botao_baixar     = 'button:has-text("Baixar Certidão")'
9. simples_nacional — Consulta Optantes pelo Simples Nacional
Modo: INTERNO
URL: https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21
Download: auto_listener
Destino: {pasta_comum}/simples_nacional.pdf

Fluxo:

Abrir URL (headless).

Preencher CNPJ.

Clicar em Consultar.

Aguardar texto Situação Atual (postback ASP.NET).

Clicar em Mais informações (se existir).

Clicar em Gerar PDF.

Capturar download automático.

Validar %PDF- e calcular SHA-256.

Seletores:

python
campo_cnpj      = 'input[id*="cnpj" i]'
botao_consultar = 'input[value="Consultar"]'
botao_mais_info = 'button:has-text("Mais informações")'
botao_gerar_pdf = 'button:has-text("Gerar PDF")'
10. compras_gov — SICAF (ÚNICA EXCEÇÃO REAL)
Modo: TOKEN
URL: https://www3.comprasnet.gov.br/sicaf-web/index.jsf
Download: hitl_print
Destino: {pasta_comum}/compras_gov.pdf

Motivo: exige certificado digital e-CNPJ (A1/A3) para Pessoa
Jurídica. Playwright não acessa certificados Windows nem tokens USB.

Fluxo:

Abrir URL em aba do navegador do operador (via CDP).

Emitir evento aguardando_captcha com mensagem "Autentique com
certificado digital e-CNPJ na aba aberta".

Aguardar o operador autenticar.

Após autenticação, se possível, a automação retoma.

Salvar em {pasta_comum}/compras_gov.pdf.

Validar %PDF- e calcular SHA-256.

Nota: este é o único portal com passo manual irredutível.

🔄 ESTRATÉGIAS DE DOWNLOAD
Estratégia	Descrição	Modo aplicável
auto_listener	Listener global captura o download disparado pelo servidor.	INTERNO e VISÍVEL
expect_download	page.expect_download() em volta do clique no botão.	INTERNO
page_pdf	page.pdf(path=..., format="A4", print_background=True).	INTERNO
hitl_print	Operador clica em "Imprimir" e salva manualmente.	TOKEN
Todos os modos gravam na MESMA pasta comum:
~/Downloads/{documento}_{data}_{hora}/{site_id}.pdf

🎨 CAPTCHA — MEDIAÇÃO HUMANA ASSISTIDA
Detecção via seletor (iframe[src*="recaptcha"], etc.).

Evento WebSocket aguardando_captcha.

Card no frontend com instruções.

Resolução pelo operador na aba dele.

Confirmação via WebSocket captcha_resolvido.

Retomada automática do backend — o PDF continua indo para a
mesma pasta comum.

Portais com CAPTCHA:

cndt — CAPTCHA de imagem.

cgu_certidoes — reCAPTCHA de imagens.

receita_cnpj_comprovante — hCaptcha.

🖥️ ARQUITETURA — CDP PARA O MODO VISÍVEL
O operador abre o Chrome com:

bash
chrome --remote-debugging-port=9222
O backend conecta via:

python
browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
context = browser.contexts[0]
page = context.new_page()
page.goto(url_do_portal)
A aba aparece no navegador do operador.

Para o MODO INTERNO, o backend lança o Chromium headless via
playwright.chromium.launch(headless=True).

Em ambos os casos, o PDF final é salvo na mesma pasta comum.

📤 FORMATO DE SAÍDA (por consulta)
json
{
  "consulta_id": "b3f1a2c4-...",
  "documento_mascarado": "12.***.***/****-95",
  "pasta_destino": "~/Downloads/08037769000196_2026-10-02_14-30-45",
  "resultados": [
    {
      "site": "receita_cnpj",
      "modo": "INTERNO",
      "status": "sucesso",
      "pdf_path": "~/Downloads/08037769000196_2026-10-02_14-30-45/receita_cnpj.pdf",
      "sha256": "abc123..."
    },
    {
      "site": "cndt",
      "modo": "VISÍVEL/CAPTCHA",
      "status": "sucesso",
      "pdf_path": "~/Downloads/08037769000196_2026-10-02_14-30-45/cndt.pdf",
      "sha256": "def456..."
    },
    {
      "site": "cgu_certidoes",
      "modo": "VISÍVEL/CAPTCHA",
      "status": "erro",
      "mensagem": "CAPTCHA não resolvido em 5 minutos."
    }
  ]
}
Note que pasta_destino é única para toda a consulta, e todos os
pdf_path apontam para a mesma pasta — independente do modo.

✅ CHECKLIST DE CORREÇÃO
☑ Nome do sistema: SIGi Certidões.
☑ Pasta de destino única para TODOS os 10 portais:
~/Downloads/{documento}_{data}_{hora}/.
☑ Nenhuma subpasta por portal, nenhuma separação por modo.
☑ Todos os PDFs lado a lado na mesma pasta.
☑ Nome do arquivo: {site_id}.pdf.
☑ Modo INTERNO (headless, invisível).
☑ FGTS em modo VISÍVEL, com geração automática do PDF oficial.
☑ Modo VISÍVEL/CAPTCHA (aba do usuário via CDP).
☑ Modo TOKEN (SICAF, única exceção).
☑ Retomada automática após CAPTCHA.
☑ Formato de saída inclui pasta_destino única.
☑ CDP documentado.
☑ Removida a distinção errada "AUTOMAÇÃO vs MANUAL".
☑ Corrigido o checklist final: não é só "os 6 internos", é
TODOS os 10.
🚀 PRÓXIMOS PASSOS
Refatorar TODOS os 10 módulos para gravar em
~/Downloads/{doc}_{data}_{hora}/{site_id}.pdf.

Implementar o orquestrador que cria uma única pasta comum
por consulta e a compartilha com todos os portais.

Implementar o WebSocket para eventos em tempo real.

Montar o Card de CAPTCHA no frontend (React).

Implementar o SICAF quando o token estiver disponível.

Fim do agents.md

text

---

## 🎯 O que mudou

| # | Correção |
|---|---|
| 1 | Seção de pasta de destino reescrita com título explícito: **"REGRA ÚNICA PARA TODOS OS 10 PORTAIS"**. |
| 2 | Adicionada frase: *"Não existe pasta separada por modo. Não existe subpasta por port
al."* |
| 3 | Tabela do catálogo ganhou coluna **Destino** = `pasta comum` para todos os 10. |
| 4 | Cada fluxo de portal agora diz explicitamente `**Destino:** {pasta_comum}/{site}.pdf`. |
| 5 | Checklist final corrigido: era *"Refatorar os 6 módulos INTERNOS"*, agora é *"Refatorar **TODOS os 10 módulos**"*. |
| 6 | Adicionado no checklist: *"Nenhuma subpasta por portal, nenhuma separação por modo."* |
| 7 | Adicionada nota no formato JSON: *"`pasta_destino` é única para toda a consulta"*. |