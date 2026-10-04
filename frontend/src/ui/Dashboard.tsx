import { useEffect, useState } from 'react';

type Site = {
  codigo: string;
  nome: string;
  orgao: string;
  captcha: string;
  url: string;
  execution_mode: 'INTERNO' | 'VISÍVEL' | 'VISÍVEL/CAPTCHA' | 'TOKEN' | 'MANUAL';
  document_types: ('CPF' | 'CNPJ')[];
  integration_configured: boolean;
  manual_only: boolean;
  manual_mode: 'captcha' | 'token' | null;
};

type ConsultationSite = {
  codigo: string;
  status: string;
  resultado: { erro?: string; detalhe?: string; arquivo?: string; pdf_sha256?: string; pdf_path?: string } | null;
};

type Consultation = {
  id: string;
  documento_tipo: string;
  documento_mascarado: string;
  iniciado_em: string;
  status: string;
  pasta_disponivel: boolean;
  pasta_destino: string | null;
  arquivos_pdf: { nome: string; tamanho: number; valido: boolean; sha256: string; modificado_em: string }[];
  sites: ConsultationSite[];
};

type CaptchaPrompt = {
  captcha_id: string;
  site_codigo: string;
  consulta_id: string;
  tipo: 'imagem' | 'recaptcha' | 'hcaptcha' | 'token';
  mensagem?: string;
};

const manualPdfNames: Record<string, string> = {
  cndt: 'cndt.pdf',
  ceis_cgu: 'cgu_certidoes.pdf',
  cartao_cnpj: 'receita_cnpj_comprovante.pdf',
  sicaf: 'compras_gov.pdf',
  simples_nacional: 'simples_nacional.pdf',
};

export function addRecentCnpj(history: string[], cnpj: string): string[] {
  const normalized = cnpj.trim();
  const digits = normalized.replace(/\D/g, '');
  if (!digits) return history;
  return [normalized, ...history.filter(item => item.replace(/\D/g, '') !== digits)].slice(0, 5);
}

export function movePdfInOrder(files: string[], filename: string, targetIndex: number): string[] {
  const sourceIndex = files.indexOf(filename);
  if (sourceIndex < 0 || targetIndex < 0 || targetIndex >= files.length || sourceIndex === targetIndex) return files;
  const reordered = [...files];
  reordered.splice(sourceIndex, 1);
  reordered.splice(targetIndex, 0, filename);
  return reordered;
}

export function Dashboard() {
  const [sites, setSites] = useState<Site[]>([]);
  const [consultations, setConsultations] = useState<Consultation[]>([]);
  const [selectedSites, setSelectedSites] = useState<string[]>([]);
  const [documentType, setDocumentType] = useState<'CPF' | 'CNPJ'>('CNPJ');
  const [document, setDocument] = useState('');
  const [recentCnpjs, setRecentCnpjs] = useState<string[]>([]);
  const [showCnpjHistory, setShowCnpjHistory] = useState(false);
  const [birthDate, setBirthDate] = useState('');
  const [notice, setNotice] = useState('');
  const [busySite, setBusySite] = useState('');
  const [activeConsultationIds, setActiveConsultationIds] = useState<string[]>([]);
  const [activeConsultationId, setActiveConsultationId] = useState('');
  const [activeSessionDocumentKey, setActiveSessionDocumentKey] = useState('');
  const [mergeOrder, setMergeOrder] = useState<string[]>([]);
  const [draggedPdf, setDraggedPdf] = useState<string | null>(null);
  const [merging, setMerging] = useState(false);
  const [captchaPrompts, setCaptchaPrompts] = useState<CaptchaPrompt[]>([]);
  const captcha = captchaPrompts[0] ?? null;
  const currentSession = consultations.find(consultation => consultation.id === activeConsultationId)
    ?? consultations[0]
    ?? null;
  const eligibleSites = sites.filter(site => site.document_types.includes(documentType));
  const selectableSites = eligibleSites.filter(site => site.integration_configured);
  const manualCaptchaSites = eligibleSites.filter(site => site.manual_mode === 'captcha');
  const manualTokenSites = eligibleSites.filter(site => site.manual_mode === 'token');
  const automatedSites = eligibleSites.filter(site => !site.manual_only);

  const availableMergeFiles = (currentSession?.arquivos_pdf ?? [])
    .filter(file => file.valido && file.nome.toLowerCase() !== 'certidoes_unificadas.pdf')
    .map(file => file.nome);
  const orderedMergeFiles = [
    ...mergeOrder.filter(filename => availableMergeFiles.includes(filename)),
    ...availableMergeFiles.filter(filename => !mergeOrder.includes(filename)),
  ];

  useEffect(() => {
    setSelectedSites(current => current.filter(siteCode => {
      const site = sites.find(item => item.codigo === siteCode);
      return !site || site.document_types.includes(documentType);
    }));
  }, [documentType, sites]);

  async function loadData() {
    const [catalogResponse, consultationsResponse] = await Promise.all([
      fetch('/api/v1/sites/catalogo'),
      fetch('/api/v1/consultas'),
    ]);
    if (!catalogResponse.ok || !consultationsResponse.ok) {
      throw new Error('Não foi possível carregar os dados locais.');
    }
    const catalog = await catalogResponse.json() as { sites: Site[] };
    const history = await consultationsResponse.json() as { consultas: Consultation[] };
    setSites(catalog.sites);
    setConsultations(history.consultas);
  }

  useEffect(() => {
    loadData().catch(error => setNotice(error.message));
  }, []);

  useEffect(() => {
    const poll = window.setInterval(() => loadData().catch(() => undefined), 2000);
    return () => window.clearInterval(poll);
  }, []);

  useEffect(() => {
    setMergeOrder(current => [
      ...current.filter(filename => availableMergeFiles.includes(filename)),
      ...availableMergeFiles.filter(filename => !current.includes(filename)),
    ]);
  }, [currentSession?.id, availableMergeFiles.join('|')]);

  useEffect(() => {
    if (!activeConsultationIds.length) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const sockets = activeConsultationIds.map(consultationId => {
      const socket = new WebSocket(`${protocol}//${window.location.host}/api/v1/consultas/${consultationId}/stream`);
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.evento === 'captcha_necessario') {
          const prompt = { ...message, consulta_id: consultationId } as CaptchaPrompt;
          setCaptchaPrompts(current => current.some(item => item.captcha_id === prompt.captcha_id)
            ? current
            : [...current, prompt]);
        }
        if (message.evento === 'site_concluido' && message.status === 'sucesso') {
          setNotice(`Certidão ${message.site_codigo} salva na pasta única da consulta.`);
        }
        loadData().catch(error => setNotice(error.message));
      };
      return socket;
    });
    return () => {
      sockets.forEach(socket => socket.close());
    };
  }, [activeConsultationIds]);

  async function startConsultation(siteCodes: string[]) {
    if (!document.trim()) {
      setNotice('Informe o CPF/CNPJ antes de iniciar uma consulta.');
      return;
    }
    if (!siteCodes.length) {
      setNotice('Marque ao menos uma certidão para iniciar.');
      return;
    }
    setBusySite(siteCodes.length === 1 ? siteCodes[0] : 'selected');
    setNotice('');
    try {
      const documentKey = `${documentType}:${document.replace(/\D/g, '')}`;
      const reuseActiveSession = activeConsultationId && activeSessionDocumentKey === documentKey;
      const response = await fetch('/api/v1/consultas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          documento: document,
          tipo: documentType,
          sites: siteCodes,
          ...(documentType === 'CPF' && siteCodes.includes('receita_inss_cpf') ? { data_nascimento: birthDate } : {}),
          ...(reuseActiveSession ? { consulta_id: activeConsultationId } : {}),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail) ? payload.detail.map((item: { msg: string }) => item.msg).join(' ') : payload.detail;
        throw new Error(detail || 'Não foi possível iniciar a consulta.');
      }
      if (documentType === 'CNPJ') setRecentCnpjs(current => addRecentCnpj(current, document));
      setActiveConsultationIds(current => [...new Set([...current, payload.consulta_id])]);
      setActiveConsultationId(payload.consulta_id);
      setActiveSessionDocumentKey(documentKey);
      setNotice(`Consulta iniciada para ${siteCodes.length} certidão(ões). Os portais internos rodam em modo invisível; desafios assistidos aparecem aqui.`);
      await loadData();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao iniciar consulta.');
    } finally {
      setBusySite('');
    }
  }

  async function openManualPortal(site: Site) {
    if (!document.trim()) {
      setNotice('Informe o CPF/CNPJ antes de abrir o portal.');
      return;
    }
    const portalTab = window.open('about:blank', '_blank');
    if (!portalTab) {
      setNotice('O navegador bloqueou a nova aba. Permita pop-ups para este painel e tente novamente.');
      return;
    }
    setBusySite(site.codigo);
    setNotice('Preparando a pasta da consulta e abrindo o portal oficial…');
    try {
      const documentKey = `${documentType}:${document.replace(/\D/g, '')}`;
      const reuseActiveSession = activeConsultationId && activeSessionDocumentKey === documentKey;
      const response = await fetch('/api/v1/consultas/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          documento: document,
          tipo: documentType,
          site: site.codigo,
          ...(reuseActiveSession ? { consulta_id: activeConsultationId } : {}),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Não foi possível abrir a sessão manual.');
      if (documentType === 'CNPJ') setRecentCnpjs(current => addRecentCnpj(current, document));
      portalTab.location.href = payload.url;
      setActiveConsultationId(payload.consulta_id);
      setActiveSessionDocumentKey(documentKey);
      await loadData();
      setNotice(`Portal aberto. Salve ${payload.nome_pdf} na pasta da sessão exibida no card.`);
    } catch (error) {
      portalTab.close();
      setNotice(error instanceof Error ? error.message : 'Erro ao abrir o portal oficial.');
    } finally {
      setBusySite('');
    }
  }

  async function continueSimpleManually(consultationId: string, site: Site) {
    const portalTab = window.open('about:blank', '_blank');
    if (!portalTab) {
      setNotice('O navegador bloqueou a nova aba. Permita pop-ups para este painel e tente novamente.');
      return;
    }
    try {
      const response = await fetch(`/api/v1/consultas/${consultationId}/sites/simples_nacional/manual`, { method: 'POST' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Não foi possível abrir a contingência manual.');
      portalTab.location.href = payload.url || site.url;
      setActiveConsultationId(consultationId);
      await loadData();
      setNotice(`Portal aberto na mesma sessão. Salve ${payload.nome_pdf} na pasta da sessão exibida no card.`);
    } catch (error) {
      portalTab.close();
      setNotice(error instanceof Error ? error.message : 'Erro ao abrir o portal Simples Nacional.');
    }
  }

  async function consultSelectedSites() {
    const selectedAutomatedSites = selectedSites.filter(siteCode =>
      selectableSites.some(site => site.codigo === siteCode),
    );
    if (selectedAutomatedSites.length) await startConsultation(selectedAutomatedSites);
  }

  function toggleSite(siteCode: string) {
    setSelectedSites(current => current.includes(siteCode) ? current.filter(code => code !== siteCode) : [...current, siteCode]);
  }

  function toggleAllEligible() {
    setSelectedSites(selectedSites.length === selectableSites.length ? [] : selectableSites.map(site => site.codigo));
  }

  async function openConsultationFolder(consultationId: string) {
    try {
      const response = await fetch(`/api/v1/consultas/${consultationId}/abrir-pasta`, { method: 'POST' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Não foi possível abrir a pasta.');
      setNotice('Pasta da consulta aberta no Explorer.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao abrir a pasta da consulta.');
    }
  }

  async function copySessionFolder(path: string) {
    try {
      await navigator.clipboard.writeText(path);
      setNotice('Caminho da pasta copiado. Selecione-o na janela “Salvar como” do portal oficial.');
    } catch {
      setNotice(`Pasta da sessão: ${path}`);
    }
  }

  async function resolveCaptcha(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!captcha) return;
    try {
      const response = await fetch(`/api/v1/consultas/${captcha.consulta_id}/captcha/${captcha.captcha_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resposta: 'concluido' }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Não foi possível enviar a resposta.');
      setCaptchaPrompts(current => current.filter(item => item.captcha_id !== captcha.captcha_id));
      setNotice(captcha.site_codigo === 'cndt'
        ? 'Confirmação recebida. Aguardando o PDF emitido no portal do TST.'
        : 'Confirmação recebida. A consulta continuará automaticamente.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao enviar resposta.');
    }
  }

  async function mergeSessionPdfs() {
    if (!currentSession || orderedMergeFiles.length < 2 || merging) return;
    setMerging(true);
    try {
      const response = await fetch(`/api/v1/consultas/${currentSession.id}/pdf/unir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ arquivos: orderedMergeFiles }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || 'Não foi possível unir os PDFs.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = window.document.createElement('a');
      link.href = url;
      link.download = 'certidoes_unificadas.pdf';
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice('PDFs unidos na ordem exibida. O documento também foi salvo na pasta da sessão.');
      await loadData();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao unir PDFs.');
    } finally {
      setMerging(false);
    }
  }

  function dropPdfOn(filename: string) {
    if (!draggedPdf || draggedPdf === filename) return;
    setMergeOrder(movePdfInOrder(orderedMergeFiles, draggedPdf, orderedMergeFiles.indexOf(filename)));
    setDraggedPdf(null);
  }

  return (
    <>
      <header className="topbar">
        <a className="brand" href="/" aria-label="SIGi início">
          <span className="brand-wordmark" aria-hidden="true">SIG<span className="brand-i">i</span></span>
          <span className="brand-copy"><small>Sistema Inteligente de Gestão Integrada</small></span>
        </a>
        <div className="top-actions">
          <span className="environment"><i className="dot" /> Automação local · Playwright</span>
          <span className="avatar" aria-label="Usuário local">LO</span>
        </div>
      </header>
      <main className="layout">
        <section className="main-column">
          <div className="eyebrow">Consultas externas</div>
          <div className="heading">
            <div><h1>Central de certidões</h1><p>Selecione uma certidão para abrir o portal e emitir o documento.</p></div>
            <time className="date">{new Intl.DateTimeFormat('pt-BR', { dateStyle: 'full' }).format(new Date())}</time>
          </div>
          <div className="workspace">
            <section className="panel" aria-labelledby="form-title">
              <div className="panel-head"><h2 id="form-title">Documento</h2><span>CPF/CNPJ não é persistido em claro</span></div>
              <div className="panel-body">
                <div className="field-row">
                  <div className="field"><label htmlFor="tipo">Tipo</label><select id="tipo" value={documentType} onChange={event => { setDocumentType(event.target.value as 'CPF' | 'CNPJ'); setDocument(''); setBirthDate(''); }}><option value="CNPJ">CNPJ</option><option value="CPF">CPF</option></select></div>
                  <div className={`field document-field${showCnpjHistory && documentType === 'CNPJ' && recentCnpjs.length ? ' history-open' : ''}`}>
                    <label htmlFor="documento">Documento</label>
                    <input
                      id="documento"
                      value={document}
                      onChange={event => setDocument(event.target.value)}
                      onFocus={() => setShowCnpjHistory(documentType === 'CNPJ' && recentCnpjs.length > 0)}
                      onBlur={() => setShowCnpjHistory(false)}
                      onKeyDown={event => { if (event.key === 'Escape') setShowCnpjHistory(false); }}
                      autoComplete="off"
                      inputMode="numeric"
                      placeholder={documentType === 'CPF' ? '000.000.000-00' : '00.000.000/0000-00'}
                      role="combobox"
                      aria-autocomplete="list"
                      aria-expanded={showCnpjHistory && documentType === 'CNPJ' && recentCnpjs.length > 0}
                      aria-controls="recent-cnpj-list"
                    />
                    {showCnpjHistory && documentType === 'CNPJ' && recentCnpjs.length > 0 && (
                      <div className="recent-cnpj-dropdown" id="recent-cnpj-list" role="listbox" aria-label="Últimos 5 CNPJs desta sessão">
                        <div className="recent-cnpj-heading">Últimos CNPJs desta sessão</div>
                        {recentCnpjs.map(cnpj => (
                          <button
                            className="recent-cnpj-option"
                            key={cnpj.replace(/\D/g, '')}
                            type="button"
                            role="option"
                            aria-selected={document === cnpj}
                            onMouseDown={event => event.preventDefault()}
                            onClick={() => { setDocument(cnpj); setShowCnpjHistory(false); }}
                          >
                            {cnpj}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <div className="field-hint">Digite o documento; ele será enviado somente aos portais selecionados.</div>
                {documentType === 'CPF' && <div className="field"><label htmlFor="data-nascimento">Data de nascimento (necessária para Receita CPF)</label><input id="data-nascimento" type="date" value={birthDate} onChange={event => setBirthDate(event.target.value)} /></div>}
                {notice && <div className="notice" role="status">{notice}</div>}
              </div>
            </section>
            <section className="panel" aria-labelledby="sites-title">
              <div className="panel-head"><h2 id="sites-title">Certidões disponíveis</h2><button className="text-button" type="button" disabled={!selectableSites.length} onClick={toggleAllEligible}>{selectedSites.length === selectableSites.length ? 'Desmarcar disponíveis' : 'Selecionar disponíveis'}</button></div>
              <div className="portal-list">
                {automatedSites.map(site => {
                  const compatible = site.document_types.includes(documentType);
                  const canRun = site.integration_configured && compatible && !busySite;
                  return (
                    <article className="portal-row" key={site.codigo}>
                      <button className={`portal-select${selectedSites.includes(site.codigo) ? ' is-selected' : ''}`} type="button" role="checkbox" aria-checked={selectedSites.includes(site.codigo)} aria-label={`Selecionar ${site.nome}`} disabled={Boolean(busySite) || !canRun} title={!site.integration_configured ? 'Fluxo ainda em implementação; nenhuma consulta será iniciada.' : undefined} onClick={() => toggleSite(site.codigo)}>{selectedSites.includes(site.codigo) ? '✓' : ''}</button>
                      <div className="portal-details">
                        <strong>{site.nome}</strong>
                        <span className="site-org">{site.orgao}</span>
                        <span className="portal-meta">{site.integration_configured ? site.execution_mode : `Automação em implementação · ${site.execution_mode}`} · {site.captcha}</span>
                      </div>
                      <div className="portal-actions">
                        <button className="primary small-button" type="button" disabled={!canRun} title={!site.integration_configured ? 'Fluxo ainda em implementação.' : undefined} onClick={() => void startConsultation([site.codigo])}>{site.integration_configured ? 'Consultar' : 'Indisponível'}</button>
                      </div>
                    </article>
                  );
                })}
              </div>
              <div className="selected-actions"><span>{selectedSites.length} certidão(ões) selecionada(s)</span><button className="primary" type="button" disabled={!selectedSites.length || Boolean(busySite)} onClick={() => void consultSelectedSites()}>Consultar selecionadas</button></div>
            </section>
            {manualTokenSites.map(site => <section className="panel manual-token-panel" aria-labelledby="manual-token-title" key={site.codigo}>
              <div className="panel-head manual-token-head">
                <div><h2 id="manual-token-title">SICAF — certificado digital/token</h2><p>Consulta 100% manual. O SIGi não automatiza certificado digital, token ou etapas autenticadas.</p></div>
                <span className="manual-badge token-badge">Acesso manual</span>
              </div>
              <div className="portal-row">
                <span className="manual-site-icon token-site-icon" aria-hidden="true">🔐</span>
                <div className="portal-details">
                  <strong>{site.nome}</strong>
                  <span className="site-org">{site.orgao}</span>
                  <span className="portal-meta">Autentique no portal e salve o PDF na pasta da sessão como {manualPdfNames[site.codigo]}.</span>
                </div>
                <div className="portal-actions">
                  <button className="primary small-button" type="button" disabled={Boolean(busySite)} onClick={() => void openManualPortal(site)}>Abrir SICAF</button>
                </div>
              </div>
            </section>)}
            {manualCaptchaSites.length > 0 && <section className="panel manual-captcha-panel" aria-labelledby="manual-captcha-title">
              <div className="panel-head manual-captcha-head">
                <div><h2 id="manual-captcha-title">Portais com CAPTCHA — emissão manual</h2><p>O SIGi não automatiza esses portais. Abra o site, conclua a emissão e salve o PDF na pasta da sessão.</p></div>
                <span className="manual-badge">100% manual</span>
              </div>
              <div className="portal-list">
                {manualCaptchaSites.map(site => <article className="portal-row" key={site.codigo}>
                  <span className="manual-site-icon" aria-hidden="true">↗</span>
                  <div className="portal-details">
                    <strong>{site.nome}</strong>
                    <span className="site-org">{site.orgao}</span>
                    <span className="portal-meta">Portal oficial · {site.captcha}</span>
                  </div>
                  <div className="portal-actions">
                    <button className="primary small-button" type="button" disabled={Boolean(busySite)} onClick={() => void openManualPortal(site)}>Abrir site</button>
                  </div>
                </article>)}
              </div>
            </section>}
            <section className="panel" aria-labelledby="recent-title">
              <div className="panel-head"><h2 id="recent-title">Histórico de consultas</h2><span>Últimas 25</span></div>
              <div className="recent-list">
                {!consultations.length && <div className="recent-empty">Nenhuma consulta iniciada ainda.</div>}
                {consultations.map(consultation => (
                  <article className="recent-item" key={consultation.id}>
                    <div className="recent-top"><div><div className="recent-doc">{consultation.documento_tipo} · {consultation.documento_mascarado}</div><div className="recent-time">{new Date(consultation.iniciado_em).toLocaleString('pt-BR')} · {consultation.status}</div></div>{consultation.pasta_disponivel && <button className="text-button" type="button" onClick={() => void openConsultationFolder(consultation.id)}>Abrir pasta</button>}</div>
                    {consultation.sites.map(site => {
                      const manualSimpleFallback = site.codigo === 'simples_nacional' && site.status === 'erro';
                      const simplePortal = manualSimpleFallback ? sites.find(item => item.codigo === site.codigo) : undefined;
                      return <div className="recent-site" key={site.codigo}>
                        <span>{sites.find(item => item.codigo === site.codigo)?.nome || site.codigo}</span>
                        <span className={`site-state state-${site.status}`}>{site.status}</span>
                        {site.resultado?.detalhe && <span className="recent-time">{site.resultado.detalhe}</span>}
                        {site.resultado?.pdf_sha256 && <span className="recent-time">SHA-256: {site.resultado.pdf_sha256}</span>}
                        {site.resultado?.erro && <span className="site-error">{site.resultado.erro}</span>}
                        {simplePortal && <button className="text-button" type="button" onClick={() => void continueSimpleManually(consultation.id, simplePortal)}>Continuar manualmente nesta sessão</button>}
                      </div>;
                    })}
                  </article>
                ))}
              </div>
            </section>
          </div>
        </section>
        <aside className="sidebar" aria-label="Informações">
          <h2 className="side-label">Antes de emitir</h2>
          <div className="side-callout"><strong>Seleção de certidões</strong><p>Marque uma ou mais certidões e clique em “Consultar selecionadas”. Para executar apenas uma, use “Consultar” na linha correspondente.</p></div>
          <div className="side-callout"><strong>Automático e manual</strong><p>As cinco certidões automatizadas rodam em segundo plano, sem exibir cliques ou janelas do navegador. CNDT, CGU e Comprovante CNPJ são manuais por CAPTCHA; o SICAF fica separado por exigir certificado/token. Abra cada portal e salve o PDF na pasta da sessão.</p></div>
          <div className="side-callout"><strong>Arquivos da consulta</strong><p>Os PDFs válidos ficam juntos na pasta Downloads da consulta. Use “Abrir pasta” no histórico. Uma consulta só aparece como sucesso depois que o PDF é baixado e validado.</p></div>
          <section className="side-callout session-files" aria-live="polite" aria-labelledby="session-files-title">
            <strong id="session-files-title">Pasta da sessão</strong>
            {!currentSession && <p>Inicie uma consulta para criar a pasta e acompanhar os PDFs.</p>}
            {currentSession && <>
              <p>Esta pasta da consulta ativa permanece selecionada enquanto você emite e baixa os documentos. Nos portais manuais, escolha-a na janela “Salvar como” e use o nome abaixo; não é criada outra pasta ao abrir mais um portal da mesma consulta.</p>
              <ul className="session-file-list">{currentSession.sites.filter(site => manualPdfNames[site.codigo]).map(site => <li key={site.codigo}>
                <span className="session-file-valid" aria-hidden="true">↓</span>
                <span className="session-file-name">{site.codigo}: {manualPdfNames[site.codigo]}</span>
              </li>)}</ul>
              {currentSession.pasta_destino && <>
                <code className="session-folder-path">{currentSession.pasta_destino}</code>
                <div className="session-folder-actions">
                  <button className="text-button" type="button" onClick={() => void copySessionFolder(currentSession.pasta_destino!)}>Copiar caminho</button>
                  <button className="text-button" type="button" onClick={() => void openConsultationFolder(currentSession.id)}>Abrir pasta</button>
                </div>
              </>}
              {currentSession.arquivos_pdf.length > 0
                ? <ul className="session-file-list">{currentSession.arquivos_pdf.map(file => <li key={file.nome}>
                  <span className={file.valido ? 'session-file-valid' : 'session-file-invalid'} aria-hidden="true">{file.valido ? '✓' : '!'}</span>
                  <span className="session-file-name">{file.nome}</span>
                  <small>{file.valido ? `${(file.tamanho / 1024).toFixed(1)} KB` : 'PDF inválido'}</small>
                </li>)}</ul>
                : <p className="session-files-empty">Aguardando PDFs nesta sessão…</p>}
              <section className="pdf-merge" aria-labelledby="pdf-merge-title">
                <strong id="pdf-merge-title">Unir PDFs da sessão</strong>
                <p>Arraste os arquivos para definir a sequência do documento final:</p>
                {orderedMergeFiles.length > 0
                  ? <ol className="pdf-merge-list">{orderedMergeFiles.map((filename, index) => <li
                    key={filename}
                    draggable
                    onDragStart={event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', filename); setDraggedPdf(filename); }}
                    onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }}
                    onDrop={event => { event.preventDefault(); dropPdfOn(filename); }}
                    onDragEnd={() => setDraggedPdf(null)}
                    className={draggedPdf === filename ? 'is-dragged' : ''}
                  >
                    <span className="pdf-merge-grip" aria-hidden="true">⠿</span>
                    <span className="pdf-merge-number">{index + 1}.</span>
                    <span className="pdf-merge-filename">{filename}</span>
                    <span className="pdf-merge-move">
                      <button type="button" aria-label={`Mover ${filename} para cima`} disabled={index === 0} onClick={() => setMergeOrder(movePdfInOrder(orderedMergeFiles, filename, index - 1))}>↑</button>
                      <button type="button" aria-label={`Mover ${filename} para baixo`} disabled={index === orderedMergeFiles.length - 1} onClick={() => setMergeOrder(movePdfInOrder(orderedMergeFiles, filename, index + 1))}>↓</button>
                    </span>
                  </li>)}</ol>
                  : <p className="session-files-empty">Salve pelo menos dois PDFs válidos para habilitar a união.</p>}
                <button className="primary small-button pdf-merge-button" type="button" disabled={orderedMergeFiles.length < 2 || merging} onClick={() => void mergeSessionPdfs()}>
                  {merging ? 'Unindo PDFs…' : 'Unir e baixar PDF único'}
                </button>
              </section>
            </>}
          </section>
        </aside>
      </main>
      <footer className="footer">SIGi · execução local · o identificador completo permanece somente em memória durante a consulta.</footer>
      {captcha && <div className="modal-backdrop"><form className="captcha-modal" role="dialog" aria-modal="true" aria-labelledby="captcha-title" onSubmit={event => void resolveCaptcha(event)}><h2 id="captcha-title">{captcha.tipo === 'token' ? 'Autenticação necessária' : 'CAPTCHA necessário'} · {captcha.site_codigo}{captchaPrompts.length > 1 ? ` · ${captchaPrompts.length} pendentes` : ''}</h2><p>{captcha.mensagem || (captcha.tipo === 'token' ? 'Autentique com seu certificado digital/token na aba do SICAF e navegue até a certidão oficial que deseja imprimir. Confirme aqui quando a página da certidão estiver pronta.' : 'Resolva o desafio diretamente na aba oficial do portal aberta no navegador. Depois volte aqui e confirme. Não copie, envie ou automatize respostas/tokens do CAPTCHA.')}</p><div className="modal-actions"><button className="primary" type="submit">{captcha.tipo === 'token' ? 'Certidão pronta' : captcha.site_codigo === 'cndt' ? 'Já emiti no portal' : 'Já resolvi'}</button></div></form></div>}
    </>
  );
}