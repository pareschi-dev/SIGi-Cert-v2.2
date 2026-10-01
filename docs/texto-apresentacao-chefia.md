# SIG-Certidões

## Sistema Inteligente de Gestão

## 1. O que o sistema faz

O SIG-Certidões é uma central para facilitar a consulta de certidões públicas. Ele reúne, em uma única tela, os principais serviços utilizados para verificar a situação de empresas e pessoas.

Em vez de o usuário precisar procurar cada órgão separadamente, o sistema apresenta uma lista organizada de certidões. O usuário informa um CPF ou CNPJ, escolhe o serviço desejado e clica em **Consultar**.

O sistema reúne 10 serviços oficiais:

- Compras.gov.br.
- Certidão de Pessoa Jurídica da Receita Federal.
- Certidão de Pessoa Física da Receita Federal.
- Certificado de Regularidade do FGTS.
- Certidão Negativa de Débitos Trabalhistas.
- Consulta de Improbidade Administrativa e Inelegibilidade do CNJ.
- Sistema de Certidões da Controladoria-Geral da União.
- Comprovante de Inscrição e de Situação Cadastral do CNPJ.
- Certidão de Licitantes Inidôneos do TCU.
- Consulta de Optantes pelo Simples Nacional.

### Como funciona

1. O usuário escolhe se vai consultar um CPF ou CNPJ.
2. Informa o número do documento.
3. Marca uma ou mais certidões.
4. Clica em **Consultar** ou em **Consultar selecionadas**.
5. O sistema encaminha cada consulta para o serviço correspondente.
6. Quando o portal permite, o sistema realiza o procedimento e salva o PDF.
7. Quando o portal exige uma ação manual, o sistema abre o site oficial para que o usuário continue a consulta.
8. Os documentos gerados ficam organizados no sistema para facilitar a conferência.

### O que é automatizado

O sistema já possui fluxo automatizado para:

- Consulta de Improbidade Administrativa e Inelegibilidade do CNJ.
- Certidão de Pessoa Jurídica da Receita Federal.
- Certificado de Regularidade do FGTS.

Nos demais serviços, o botão **Consultar** abre diretamente o portal oficial do órgão responsável.

### Participação do usuário

Alguns portais utilizam CAPTCHA ou outra confirmação de segurança. Nesses casos, o usuário resolve a confirmação diretamente na janela oficial do portal. O sistema não tenta burlar essa etapa.

### Segurança e organização

- O sistema verifica se o CPF ou CNPJ foi digitado corretamente.
- O histórico mostra o tipo de documento e mantém o número protegido.
- Os arquivos são organizados por consulta e por serviço.
- Os PDFs gerados recebem uma identificação para ajudar na conferência.
- A certidão continua sendo emitida pelo órgão oficial responsável.

### Benefícios

- Centraliza vários serviços em um único local.
- Diminui a necessidade de repetir o mesmo preenchimento em diferentes sites.
- Facilita o trabalho diário da equipe.
- Reduz erros de digitação.
- Organiza os documentos obtidos.
- Ajuda a acompanhar as consultas realizadas.
- Mantém o usuário conectado às fontes oficiais.

### Limites atuais

O sistema depende da disponibilidade dos sites dos órgãos públicos. Quando um portal está fora do ar, muda de formato ou exige uma etapa manual, o usuário precisa continuar o procedimento diretamente no site oficial.

A conferência final do conteúdo e da validade da certidão deve sempre ser feita na fonte emissora.

---

## 2. Texto pronto para sua chefe apresentar

Bom dia.

Hoje vamos apresentar o SIG-Certidões, o Sistema Inteligente de Gestão criado para facilitar e organizar a consulta de certidões públicas.

Atualmente, para consultar certidões, muitas vezes é necessário acessar vários sites diferentes, preencher os mesmos dados repetidamente e acompanhar cada procedimento separadamente. O SIG-Certidões foi criado para reunir essa rotina em um único lugar.

Na tela principal, o usuário escolhe se deseja consultar um CPF ou CNPJ, informa o documento e seleciona as certidões necessárias. Depois, basta clicar em consultar. O sistema organiza o encaminhamento para o portal correspondente.

A central reúne dez serviços oficiais, incluindo Receita Federal, FGTS, CNJ, Tribunal de Contas da União, Tribunal Superior do Trabalho, Controladoria-Geral da União, Compras.gov.br e Simples Nacional.

Nos serviços que já possuem integração, o sistema conduz o procedimento, acompanha as etapas necessárias e pode salvar o PDF da certidão. Hoje, os fluxos integrados incluem o CNJ, a Receita Federal para CNPJ e o FGTS.

Nos demais serviços, o botão consultar abre diretamente o portal oficial do órgão responsável. Assim, mesmo quando a consulta ainda precisa ser feita manualmente, o usuário não precisa procurar o endereço correto: ele parte do SIG-Certidões e chega ao serviço oficial com um único clique.

O sistema também foi preparado para lidar com confirmações de segurança, como CAPTCHA. Quando essa etapa aparece, o próprio usuário faz a confirmação na janela oficial do portal. Isso mantém o processo seguro e respeita as regras de cada órgão.

Outro benefício é a organização dos documentos. Os PDFs obtidos ficam associados à consulta e ao serviço correspondente, facilitando a localização, a conferência e o acompanhamento do trabalho.

O SIG-Certidões não substitui os órgãos emissores. Ele funciona como uma central de apoio, organização e encaminhamento. A certidão continua sendo emitida pela fonte oficial, e a conferência final deve ser feita no próprio portal responsável.

Em resumo, o SIG-Certidões torna uma atividade repetitiva mais simples, organizada e rápida. Ele concentra os principais acessos, reduz a repetição de tarefas e cria uma base para ampliar gradualmente as consultas automatizadas.

Obrigado.

---

## 3. Frase curta para encerrar

> O SIG-Certidões reúne os principais serviços oficiais em uma única central, simplifica a rotina de consulta e mantém cada documento vinculado à sua fonte emissora.

---

## 4. Como o sistema foi feito

Foi criado um painel único que reúne os portais oficiais, recebe o CPF ou CNPJ, organiza as certidões escolhidas e encaminha cada consulta para o serviço correto.

## 5. O que foi usado para fazer

- **Python:** regras do sistema e comunicação com os portais.
- **TypeScript e React:** tela do sistema.
- **FastAPI e Uvicorn:** atendimento das solicitações.
- **Playwright:** automação dos fluxos integrados.
- **SQLite:** histórico e registros locais.
- **Pydantic:** validação das informações recebidas.
- **Vite:** compilação e publicação da interface.
- **HTML e CSS:** estrutura e aparência da página.

## 6. Principais funcionalidades

- Consulta de CPF e CNPJ.
- Catálogo com 10 serviços oficiais.
- Seleção individual ou em grupo.
- Botões **Consultar** e **Consultar selecionadas**.
- Automação do CNJ, Receita Federal CNPJ e FGTS.
- Abertura dos demais portais oficiais.
- Tratamento de CAPTCHA com participação do usuário.
- Geração e organização de PDFs.
- Histórico local das consultas.
- Proteção do CPF/CNPJ exibido no histórico.

## 7. Finalidade do sistema

Facilitar, agilizar e organizar a consulta de certidões, reduzindo o acesso repetitivo a vários sites e diminuindo erros de preenchimento.

O SIG-Certidões centraliza o atendimento, mas mantém cada certidão vinculada ao órgão oficial que a emite. A validade e o conteúdo do documento continuam sendo responsabilidade da fonte emissora.
