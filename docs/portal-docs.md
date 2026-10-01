# Documentação dos portais

## FGTS / CRF

- URL: https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf
- Captcha: nenhum
- Fluxo: valida CNPJ, abre portal e realiza consulta automatizada.

## CNDT

- URL: https://www.tst.jus.br/certidao
- Captcha: texto simples distorcido
- Estratégia: OCR com ddddocr + OpenCV.

## Receita Federal / INSS

- URL: https://servicos.receitafederal.gov.br/servico/certidoes
- Captcha: hCaptcha
- Estratégia: solver local da Fazenda ou API 2Captcha/AntiCaptcha.

## SICAF / ComprasNet

- URL: https://comprasnet.gov.br/seguro/loginPortalUASG.asp
- Captcha: captcha proprietário ComprasNet
- Estratégia: extensão Minha Effecti ou CNN especializada.

## Observações gerais

Todos os portais devem seguir a mesma base de abstração e manter seletores em arquivos de configuração ou classe própria. A mudança de layout deve disparar alerta de revisão manual.
