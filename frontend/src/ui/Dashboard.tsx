import { useEffect, useRef, useState } from 'react';

type Site = {
  codigo: string;
  nome: string;
  orgao: string;
  captcha: string;
  url: string;
  document_types: ('CPF' | 'CNPJ')[];
  integration_configured: boolean;
};

type ConsultationSite = {
  codigo: string;
  status: string;
  resultado: { erro?: string; arquivo?: string; pdf_sha256?: string } | null;
};

type Consultation = {
  id: string;
  documento_tipo: string;
  documento_mascarado: string;
  iniciado_em: string;
  status: string;
  sites: ConsultationSite[];
};

type CaptchaPrompt = {
  captcha_id: string;
  site_codigo: string;
  consulta_id: string;
  tipo: 'imagem' | 'recaptcha' | 'hcaptcha';
  imagem_base64?: string;
};

export function Dashboard() {
  const [sites, setSites] = useState<Site[]>([]);
  const [consultations, setConsultations] = useState<Consultation[]>([]);
  const [selectedSites, setSelectedSites] = useState<string[]>([]);
  const [documentType, setDocumentType] = useState<'CPF' | 'CNPJ'>('CNPJ');
  const [document, setDocument] = useState('');
  const [notice, setNotice] = useState('');
  const [busySite, setBusySite] = useState('');
  const [activeConsultationIds, setActiveConsultationIds] = useState<string[]>([]);
  const [captcha, setCaptcha] = useState<CaptchaPrompt | null>(null);
  const [captchaAnswer, setCaptchaAnswer] = useState('');
  const [manualSiteCodes, setManualSiteCodes] = useState<string[]>([]);
  const downloadedCertificates = useRef(new Set<string>());
  const eligibleSites = sites.filter(site => site.document_types.includes(documentType));
  const automatedSiteCount = sites.filter(site => site.integration_configured).length;

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
    if (!activeConsultationIds.length) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const sockets = activeConsultationIds.map(consultationId => {
      const socket = new WebSocket(`${protocol}//${window.location.host}/api/v1/consultas/${consultationId}/stream`);
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.evento === 'captcha_necessario') {
          setCaptcha({ ...message, consulta_id: consultationId } as CaptchaPrompt);
          setCaptchaAnswer('');
        }
        if (message.evento === 'site_concluido' && message.status === 'sucesso') {
          const downloadKey = `${consultationId}:${message.site_codigo}`;
          if (!downloadedCertificates.current.has(downloadKey)) {
            downloadedCertificates.current.add(downloadKey);
            const link = globalThis.document.createElement('a');
            link.href = `/api/v1/consultas/${consultationId}/sites/${message.site_codigo}/pdf`;
            link.download = `${message.site_codigo}.pdf`;
            link.hidden = true;
            globalThis.document.body.append(link);
            link.click();
            link.remove();
            setNotice(`Certidão ${message.site_codigo} emitida; o download foi iniciado automaticamente.`);
          }
        }
        loadData().catch(error => setNotice(error.message));
      };
      return socket;
    });
    const poll = window.setInterval(() => loadData().catch(() => undefined), 2000);
    return () => {
      sockets.forEach(socket => socket.close());
      window.clearInterval(poll);
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
      const response = await fetch('/api/v1/consultas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documento: document, tipo: documentType, sites: siteCodes }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail) ? payload.detail.map((item: { msg: string }) => item.msg).join(' ') : payload.detail;
        throw new Error(detail || 'Não foi possível iniciar a consulta.');
      }
      setActiveConsultationIds(current => [...new Set([...current, payload.consulta_id])]);
      setNotice(`Consulta iniciada para ${siteCodes.length} certidão(ões) selecionada(s). Acompanhe as janelas dos portais.`);
      await loadData();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao iniciar consulta.');
    } finally {
      setBusySite('');
    }
  }

  async function consultSelectedSites() {
    const compatibleSelectedSites = selectedSites.filter(siteCode => {
      const site = sites.find(item => item.codigo === siteCode);
      return site && site.document_types.includes(documentType);
    });

    const selectedManualSites = compatibleSelectedSites.filter(siteCode => !sites.find(site => site.codigo === siteCode)?.integration_configured);
    const firstManualSite = sites.find(site => site.codigo === selectedManualSites[0]);
    if (firstManualSite) window.open(firstManualSite.url, '_blank', 'noopener,noreferrer');
    setManualSiteCodes(selectedManualSites);
    if (selectedManualSites.length) {
      setNotice('Um portal manual foi aberto. Abra os próximos individualmente pelos links oficiais abaixo.');
    }
    const selectedAutomatedSites = compatibleSelectedSites.filter(siteCode => sites.find(site => site.codigo === siteCode)?.integration_configured);
    if (selectedAutomatedSites.length) await startConsultation(selectedAutomatedSites);
  }

  function toggleSite(siteCode: string) {
    setSelectedSites(current => current.includes(siteCode) ? current.filter(code => code !== siteCode) : [...current, siteCode]);
  }

  function toggleAllEligible() {
    setSelectedSites(selectedSites.length === eligibleSites.length ? [] : eligibleSites.map(site => site.codigo));
  }

  async function resolveCaptcha(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!captcha) return;
    try {
      const response = await fetch(`/api/v1/consultas/${captcha.consulta_id}/captcha/${captcha.captcha_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resposta: captcha.tipo === 'imagem' ? captchaAnswer : 'concluido' }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Não foi possível enviar a resposta.');
      setCaptcha(null);
      setCaptchaAnswer('');
      setNotice('Resposta encaminhada ao portal. A consulta continuará automaticamente.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao enviar resposta.');
    }
  }

  return (
    <>
      <header className="topbar">
        <a className="brand" href="/" aria-label="SIG-Certidões início">
          <span className="brand-wordmark" aria-hidden="true">SIG-Certidões<span className="brand-accent" /></span>
          <span className="brand-copy"><small>Sistema Inteligente de Gestão</small></span>
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
          <section className="metrics" aria-label="Resumo">
            <div className="metric"><div className="metric-label">Sites no catálogo</div><div className="metric-value">{sites.length || 10}</div><div className="metric-note">Links oficiais</div></div>
            <div className="metric"><div className="metric-label">Fluxos automatizados</div><div className="metric-value green">{automatedSiteCount}</div><div className="metric-note">Com automação integrada</div></div>
            <div className="metric"><div className="metric-label">Solicitações recentes</div><div className="metric-value">{consultations.length}</div><div className="metric-note">Neste ambiente local</div></div>
          </section>
          <div className="workspace">
            <section className="panel" aria-labelledby="form-title">
              <div className="panel-head"><h2 id="form-title">Documento</h2><span>CPF/CNPJ não é persistido em claro</span></div>
              <div className="panel-body">
                <div className="field-row">
                  <div className="field"><label htmlFor="tipo">Tipo</label><select id="tipo" value={documentType} onChange={event => { setDocumentType(event.target.value as 'CPF' | 'CNPJ'); setDocument(''); }}><option value="CNPJ">CNPJ</option><option value="CPF">CPF</option></select></div>
                  <div className="field"><label htmlFor="documento">Documento</label><input id="documento" value={document} onChange={event => setDocument(event.target.value)} autoComplete="off" inputMode="numeric" placeholder={documentType === 'CPF' ? '000.000.000-00' : '00.000.000/0000-00'} /></div>
                </div>
                <div className="field-hint">Digite o documento; ele será enviado somente aos portais selecionados.</div>
                {notice && <div className="notice" role="status">{notice}</div>}
              </div>
            </section>
            <section className="panel" aria-labelledby="sites-title">
              <div className="panel-head"><h2 id="sites-title">Certidões disponíveis</h2><button className="text-button" type="button" onClick={toggleAllEligible}>{selectedSites.length === eligibleSites.length ? 'Desmarcar disponíveis' : 'Selecionar disponíveis'}</button></div>
              <div className="portal-list">
                {eligibleSites.map(site => {
                  const compatible = site.document_types.includes(documentType);
                  const canRun = site.integration_configured && compatible && !busySite;
                  return (
                    <article className="portal-row" key={site.codigo}>
                      <button className={`portal-select${selectedSites.includes(site.codigo) ? ' is-selected' : ''}`} type="button" role="checkbox" aria-checked={selectedSites.includes(site.codigo)} aria-label={`Selecionar ${site.nome}`} disabled={Boolean(busySite)} onClick={() => toggleSite(site.codigo)}>{selectedSites.includes(site.codigo) ? '✓' : ''}</button>
                      <div className="portal-details">
                        <strong>{site.nome}</strong>
                        <span className="site-org">{site.orgao}</span>
                        <span className="portal-meta">{site.integration_configured ? '[AUTOMAÇÃO] ' : '[MANUAL] '}{site.captcha}</span>
                      </div>
                      <div className="portal-actions">
                        {site.integration_configured ? <button className="primary small-button" type="button" disabled={!canRun} onClick={() => void startConsultation([site.codigo])}>Consultar</button> : <a className="primary small-button portal-button" href={site.url} target="_blank" rel="noreferrer" aria-label={`Consultar ${site.nome}`} title={`Consultar ${site.nome}`}>Consultar</a>}
                      </div>
                    </article>
                  );
                })}
              </div>
              <div className="selected-actions"><span>{selectedSites.length} certidão(ões) selecionada(s)</span><button className="primary" type="button" disabled={!selectedSites.length || Boolean(busySite)} onClick={() => void consultSelectedSites()}>Consultar selecionadas</button></div>
              {manualSiteCodes.length > 0 && <div className="manual-links" role="region" aria-label="Portais manuais bloqueados"><strong>Abra os portais oficiais manualmente:</strong>{manualSiteCodes.map(siteCode => { const site = sites.find(item => item.codigo === siteCode); return site ? <a key={site.codigo} href={site.url} target="_blank" rel="noreferrer">{site.nome}</a> : null; })}</div>}
            </section>
            <section className="panel" aria-labelledby="recent-title">
              <div className="panel-head"><h2 id="recent-title">Histórico de consultas</h2><span>Últimas 25</span></div>
              <div className="recent-list">
                {!consultations.length && <div className="recent-empty">Nenhuma consulta iniciada ainda.</div>}
                {consultations.map(consultation => (
                  <article className="recent-item" key={consultation.id}>
                    <div className="recent-top"><div><div className="recent-doc">{consultation.documento_tipo} · {consultation.documento_mascarado}</div><div className="recent-time">{new Date(consultation.iniciado_em).toLocaleString('pt-BR')}</div></div></div>
                    {consultation.sites.map(site => <div className="recent-site" key={site.codigo}><span>{sites.find(item => item.codigo === site.codigo)?.nome || site.codigo}</span></div>)}
                  </article>
                ))}
              </div>
            </section>
          </div>
        </section>
        <aside className="sidebar" aria-label="Informações">
          <h2 className="side-label">Antes de emitir</h2>
          <div className="side-callout"><strong>Seleção de certidões</strong><p>Marque uma ou mais fontes e use “Consultar selecionadas”, ou use o botão da própria linha para consultar somente aquela certidão.</p></div>
          <div className="side-callout"><strong>CAPTCHA humano</strong><p>Desafios de imagem aparecem aqui. reCAPTCHA e hCaptcha devem ser resolvidos na janela real do portal; tokens não são injetados.</p></div>
          <div className="side-callout"><strong>Download automático</strong><p>Após a emissão, o PDF é baixado automaticamente quando o portal entrega um arquivo válido. Confirme a certidão diretamente na fonte emissora.</p></div>
        </aside>
      </main>
      <footer className="footer">SIG-Certidões · execução local · o identificador completo permanece somente em memória durante a consulta.</footer>
      {captcha && <div className="modal-backdrop"><form className="captcha-modal" role="dialog" aria-modal="true" aria-labelledby="captcha-title" onSubmit={event => void resolveCaptcha(event)}><h2 id="captcha-title">Captcha necessário · {captcha.site_codigo}</h2>{captcha.tipo === 'imagem' ? <><img className="captcha-image" src={`data:image/png;base64,${captcha.imagem_base64}`} alt="Captcha do portal" /><label className="field"><span>Resposta do captcha</span><input autoFocus value={captchaAnswer} onChange={event => setCaptchaAnswer(event.target.value)} required /></label></> : <p>Resolva o desafio na janela aberta do portal e confirme aqui. Não copie nem automatize o token.</p>}<div className="modal-actions"><button className="primary" type="submit" disabled={captcha.tipo === 'imagem' && !captchaAnswer.trim()}>Já resolvi</button></div></form></div>}
    </>
  );
}