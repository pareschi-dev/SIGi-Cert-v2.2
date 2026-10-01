# SIG-Certidões

## Sistema Inteligente de Gestão

Documento-base para apresentação executiva em PowerPoint.

---

## Slide 1 — Visão geral

### SIG-Certidões

Central para organizar consultas de certidões públicas brasileiras em um único painel.

### Proposta

- Reunir os principais portais oficiais em um catálogo único.
- Reduzir a troca manual entre sites e formulários.
- Padronizar a entrada de CPF/CNPJ.
- Automatizar os fluxos que já possuem integração operacional.
- Manter acesso direto aos portais cuja consulta ainda depende da interação manual.
- Registrar consultas e documentos gerados no ambiente local.

---

## Slide 2 — Problema atendido

O processo tradicional exige que o usuário:

- Abra vários portais públicos diferentes.
- Identifique qual serviço corresponde ao CPF ou CNPJ.
- Preencha repetidamente os mesmos dados.
- Resolva CAPTCHAs e mudanças de tela de cada órgão.
- Acompanhe individualmente a emissão dos documentos.
- Organize os PDFs obtidos e confira sua origem.

O SIG-Certidões concentra essa jornada em uma única interface e direciona cada consulta para a fonte oficial correspondente.

---

## Slide 3 — O que o sistema entrega

### No painel web

- Identificação do tipo de documento: CPF ou CNPJ.
- Campo único para informar o documento.
- Catálogo com 10 serviços oficiais.
- Checkbox para selecionar uma ou várias certidões.
- Botão individual **Consultar** em cada linha.
- Botão **Consultar selecionadas** para uma operação em lote.
- Abertura de portais manuais em novas abas.
- Consulta automatizada nos fluxos integrados.
- Histórico local das solicitações realizadas.
- Download automático quando a automação recebe um PDF válido.

### Na API

- Validação de CPF e CNPJ.
- Criação de consultas com identificador único.
- Persistência local de consulta, sites e eventos.
- Atualização de eventos por WebSocket.
- Mediação de CAPTCHA humano.
- Download protegido dos PDFs gerados.

---

## Slide 4 — Portais disponíveis

O catálogo atual contém 10 serviços oficiais:

| Serviço exibido | Órgão | Operação atual |
| --- | --- | --- |
| Compras.gov.br · Acesse sua Conta | Compras.gov.br | Acesso direto ao portal |
| Certidão de Pessoa Jurídica (CNPJ) | Receita Federal | Automação integrada |
| Certidão de Pessoa Física (CPF) | Receita Federal | Acesso direto ao portal |
| Certificado de Regularidade do FGTS (CRF) | Caixa Econômica Federal | Automação integrada |
| Certidão Negativa de Débitos Trabalhistas (CNDT) | Tribunal Superior do Trabalho | Acesso direto ao portal |
| Cadastro Nacional de Condenações Cíveis por Ato de Improbidade Administrativa e Inelegibilidade | Conselho Nacional de Justiça | Automação integrada |
| Sistema de Certidões da Controladoria-Geral da União | CGU | Acesso direto ao portal |
| Comprovante de Inscrição e de Situação Cadastral (CNPJ) | Receita Federal | Acesso direto ao portal |
| Certidão de Licitantes Inidôneos (TCU) | Tribunal de Contas da União | Acesso direto ao portal |
| Consulta Optantes pelo Simples Nacional | Receita Federal | Acesso direto ao portal |

Todos os acessos utilizam os endereços oficiais cadastrados no catálogo da aplicação.

---

## Slide 5 — Automação integrada

Atualmente existem três fluxos Playwright operacionais:

### CNJ

1. Abre o Cadastro Nacional de Condenações Cíveis por Ato de Improbidade Administrativa e Inelegibilidade.
2. Preenche o CPF/CNPJ formatado.
3. Executa a pesquisa.
4. Aguarda a opção de certidão negativa ou identifica a opção positiva.
5. Emite e salva o PDF quando a opção negativa está disponível.

### Receita Federal — CNPJ

1. Abre a página de Certidão de Pessoa Jurídica.
2. Preenche o CNPJ formatado.
3. Clica em **Emitir Certidão**.
4. Detecta aviso de certidão válida ou tabela de resultados.
5. Permite a resolução humana de reCAPTCHA/hCaptcha na janela oficial.
6. Consulta a certidão existente quando necessário.
7. Localiza a certidão mais recente e sua segunda via.
8. Salva o PDF baixado e calcula seu hash SHA-256.

### FGTS — CRF

1. Abre a Consulta de Regularidade do Empregador.
2. Envia somente os dígitos do CNPJ.
3. Mantém a UF em branco quando aplicável.
4. Executa a consulta.
5. Localiza o link do Certificado de Regularidade do FGTS.
6. Clica em **Visualizar**.
7. Clica em **Imprimir**.
8. Gera o PDF automaticamente.
9. Valida se o arquivo gerado começa com a assinatura de PDF e calcula seu hash.

---

## Slide 6 — Acesso manual aos demais portais

Os sete serviços sem automação Playwright não ficam indisponíveis.

Ao clicar em **Consultar**, o sistema abre o endereço oficial em uma nova aba. Isso permite que o operador continue o procedimento diretamente no órgão responsável, com a sessão e os desafios apresentados pelo próprio portal.

Esse modelo é usado para:

- Compras.gov.br.
- Receita Federal — CPF.
- CNDT.
- CGU.
- Comprovante de Inscrição e de Situação Cadastral.
- TCU.
- Simples Nacional.

---

## Slide 7 — Fluxo de uso no painel

1. O usuário acessa o SIG-Certidões.
2. Seleciona CPF ou CNPJ.
3. Informa o documento.
4. Marca uma ou mais certidões.
5. Clica em **Consultar** na linha ou em **Consultar selecionadas**.
6. O sistema separa automaticamente:
   - Portais integrados: enviados para a fila de automação.
   - Portais manuais: abertos em novas abas oficiais.
7. Quando necessário, o usuário resolve o CAPTCHA na janela real do portal.
8. Os PDFs automatizados são salvos no diretório local de consultas.
9. O histórico local registra a solicitação e os portais envolvidos.

---

## Slide 8 — CAPTCHA e interação humana

O sistema não tenta burlar CAPTCHA.

### Como funciona

- CAPTCHAs de imagem podem ser apresentados no painel para resposta do operador.
- reCAPTCHA e hCaptcha devem ser resolvidos na janela visível do portal oficial.
- O sistema aguarda a conclusão humana.
- O token não é copiado nem injetado artificialmente.
- Após a confirmação, a automação continua o fluxo.

Essa abordagem mantém o operador no controle da etapa que exige validação humana e reduz o risco de uso incompatível com as regras dos portais.

---

## Slide 9 — Segurança e privacidade

### Documento consultado

- CPF/CNPJ é validado antes do envio.
- A API normaliza a entrada e remove a formatação para validação.
- O banco registra documento mascarado e hash do documento, não o número completo em claro na consulta.
- A interface informa que o identificador completo permanece somente em memória durante a consulta.

### Arquivos

- PDFs ficam organizados por consulta e por portal.
- Cada PDF automatizado recebe hash SHA-256.
- O download é disponibilizado pela API somente para o site pertencente à consulta.
- A validação atual confirma a estrutura básica do PDF, não o conteúdo jurídico.

### Observação

O sistema deve ser utilizado em ambiente autorizado e os documentos devem ser conferidos na fonte emissora.

---

## Slide 10 — Arquitetura técnica

### Frontend

- React 19.
- TypeScript.
- Vite.
- Interface responsiva para desktop e celular.
- Marca SIG-Certidões e identidade institucional própria.

### Backend

- Python 3.11 ou superior.
- FastAPI.
- Uvicorn.
- Pydantic para contratos e validações.
- SQLite para persistência local.
- ThreadPoolExecutor para execução dos sites.

### Automação

- Playwright com Chromium.
- Seletores específicos por portal.
- Navegador visível quando a interação humana é necessária.
- Geração e validação local de PDFs.

### Comunicação

- REST para catálogo, consultas, CAPTCHA e download.
- WebSocket para eventos da consulta.

---

## Slide 11 — Dados registrados

O banco local possui estruturas para:

- Consultas.
- Sites associados a cada consulta.
- Auditoria da operação.
- CAPTCHAs pendentes.
- Eventos de execução.

Uma consulta possui identificador único e pode reunir vários portais. Os eventos permitem acompanhar a evolução da operação sem expor o CPF/CNPJ completo na interface de histórico.

---

## Slide 12 — CLI e operação técnica

Além do painel web, o projeto possui CLI para operações técnicas e testes controlados.

### Exemplos

```bash
python -m certhub.main --version
python -m certhub.main listar-portais
python -m certhub.main emitir --portal cnj --documento 12.345.678/0001-95 --hitl
python -m certhub.main emitir --portal receita_cnpj --documento 12.345.678/0001-95 --hitl
python -m certhub.main emitir --portal fgts --documento 12.345.678/0001-95 --hitl
```

### Inicialização web

```bash
cd frontend
npm run build
cd ..
python -m uvicorn certhub.web:app --host 0.0.0.0 --port 8001
```

Na rede local, o painel pode ser acessado pelo endereço configurado na máquina servidora, por exemplo `http://10.206.11.104:8001`.

---

## Slide 13 — Demonstração sugerida

### Cenário

Usar um CNPJ de teste autorizado.

### Roteiro

1. Abrir o painel SIG-Certidões.
2. Mostrar o catálogo com os 10 serviços.
3. Selecionar CNPJ.
4. Informar o CNPJ de demonstração.
5. Marcar CNJ, Receita Federal CNPJ e FGTS.
6. Clicar em **Consultar selecionadas**.
7. Demonstrar a abertura do navegador oficial.
8. Resolver CAPTCHA manualmente, se apresentado.
9. No FGTS, mostrar a sequência do certificado, visualização e PDF.
10. Mostrar o PDF salvo e o histórico local.
11. Abrir um serviço manual, como CNDT, e mostrar que o botão **Consultar** leva ao portal oficial.

### Mensagem principal

O operador trabalha em um único painel, mas o documento continua sendo emitido pela fonte oficial responsável.

---

## Slide 14 — Benefícios esperados

- Menos alternância entre sistemas.
- Menos repetição de preenchimento.
- Padronização do processo de consulta.
- Redução de erros de digitação por validação prévia.
- Organização dos PDFs por consulta e portal.
- Rastreabilidade local por identificador e eventos.
- Separação clara entre automação e interação humana.
- Facilidade para incorporar novos portais ao catálogo.

---

## Slide 15 — Limitações atuais

Para a apresentação, estas limitações devem ser comunicadas de forma objetiva:

- Três portais possuem automação integrada: CNJ, Receita Federal CNPJ e FGTS.
- Os demais sete portais são abertos para consulta manual no endereço oficial.
- CAPTCHAs interativos dependem de uma pessoa.
- A fila de execução está em memória nesta instância.
- Não há autenticação ou autorização por usuário.
- Não há retenção automática ou política de expiração de documentos.
- O PDF é validado estruturalmente; seu conteúdo jurídico ainda deve ser conferido.
- Mudanças de layout dos órgãos podem exigir atualização dos seletores.
- A disponibilidade dos portais externos não é controlada pelo SIG-Certidões.

---

## Slide 16 — Próximas evoluções

### Curto prazo

- Melhorar mensagens de retorno para o operador.
- Criar testes de disponibilidade dos portais.
- Centralizar configuração de URLs e seletores.
- Adicionar exportação de relatório da consulta.

### Médio prazo

- Implementar autenticação e perfis de acesso.
- Substituir a fila em memória por uma fila persistente.
- Adicionar PostgreSQL e Redis para ambiente multiusuário.
- Criar painel administrativo e trilha de auditoria consultável.
- Expandir os fluxos automatizados dos demais portais.

### Governança

- Manter validação jurídica e operacional com a área responsável.
- Registrar alterações dos portais externos.
- Definir política de retenção e descarte de documentos.

---

## Slide 17 — Fechamento executivo

### SIG-Certidões em uma frase

Uma central institucional que organiza dez fontes oficiais, automatiza os fluxos prioritários e mantém os demais serviços acessíveis no portal de origem.

### Resultado entregue

- Painel web responsivo.
- Catálogo oficial de 10 serviços.
- Três automações Playwright.
- Consulta manual integrada por links oficiais.
- Validação de CPF/CNPJ.
- CAPTCHA com participação humana.
- Histórico e eventos locais.
- PDFs organizados e identificados por hash.

### Mensagem para decisão

O SIG-Certidões já funciona como base operacional controlada e pode evoluir para uma plataforma multiusuário com governança, fila persistente e maior cobertura de automação.

---

## Nota para o apresentador

Evitar afirmar que todos os dez portais já emitem documentos automaticamente. A formulação correta é:

> “O catálogo reúne dez serviços oficiais. Três já possuem automação integrada e os outros sete são acessados diretamente no portal oficial a partir do mesmo painel.”
