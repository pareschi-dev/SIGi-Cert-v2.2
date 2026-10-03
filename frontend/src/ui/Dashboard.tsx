import { useEffect, useState } from 'react';

type Site = {
  codigo: string;
  nome: string;
  orgao: string;
  captcha: string;
  url: string;
  execution_mode: 'INTERNO' | 'VISÍVEL' | 'VISÍVEL/CAPTCHA' | 'TOKEN';
  document_types: ('CPF' | 'CNPJ')[];
  integration_configured: boolean;
};

type ConsultationSite = {
  codigo: string;
  status: string;
  resultado: { erro?: string; arquivo?: string; pdf_sha256?: string; pdf_path?: string } | null;
};

type Consultation = {
  id: string;
  documento_tipo: string;
  documento_mascarado: string;
  iniciado_em: string;
  status: string;
  pasta_disponivel: boolean;
  pasta_destino: string | null;
  sites: ConsultationSite[];
};

type CaptchaPrompt = {
  captcha_id: string;
  site_codigo: string;
  consulta_id: string;
  tipo: 'imagem' | 'recaptcha' | 'hcaptcha' | 'token';
  mensagem?: string;
};

export function addRecentCnpj(history: string[], cnpj: string): string[] {
  const normalized = cnpj.trim();
  const digits = normalized.replace(/\D/g, '');
  if (!digits) return history;
  return [normalized, ...history.filter(item => item.replace(/\D/g, '') !== digits)].slice(0, 5);
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
  const [captchaPrompts, setCaptchaPrompts] = useState<CaptchaPrompt[]>([]);
  const captcha = captchaPrompts[0] ?? null;
  const eligibleSites = sites.filter(site => site.document_types.includes(documentType));
  const selectableSites = eligibleSites.filter(site => site.integration_configured);
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
        body: JSON.stringify({ documento: document, tipo: documentType, sites: siteCodes, ...(documentType === 'CPF' && siteCodes.includes('receita_inss_cpf') ? { data_nascimento: birthDate } : {}) }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail) ? payload.detail.map((item: { msg: string }) => item.msg).join(' ') : payload.detail;
        throw new Error(detail || 'Não foi possível iniciar a consulta.');
      }
      if (documentType === 'CNPJ') setRecentCnpjs(current => addRecentCnpj(current, document));
      setActiveConsultationIds(current => [...new Set([...current, payload.consulta_id])]);
      setNotice(`Consulta iniciada para ${siteCodes.length} certidão(ões). Os portais internos rodam em modo invisível; desafios assistidos aparecem aqui.`);
      await loadData();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Erro ao iniciar consulta.');
    } finally {
      setBusySite('');
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
                {eligibleSites.map(site => {
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
            <section className="panel" aria-labelledby="recent-title">
              <div className="panel-head"><h2 id="recent-title">Histórico de consultas</h2><span>Últimas 25</span></div>
              <div className="recent-list">
                {!consultations.length && <div className="recent-empty">Nenhuma consulta iniciada ainda.</div>}
                {consultations.map(consultation => (
                  <article className="recent-item" key={consultation.id}>
                    <div className="recent-top"><div><div className="recent-doc">{consultation.documento_tipo} · {consultation.documento_mascarado}</div><div className="recent-time">{new Date(consultation.iniciado_em).toLocaleString('pt-BR')} · {consultation.status}</div></div>{consultation.pasta_disponivel && <button className="text-button" type="button" onClick={() => void openConsultationFolder(consultation.id)}>Abrir pasta</button>}</div>
                    {consultation.sites.map(site => <div className="recent-site" key={site.codigo}><span>{sites.find(item => item.codigo === site.codigo)?.nome || site.codigo}</span><span className={`site-state state-${site.status}`}>{site.status}</span>{site.resultado?.pdf_sha256 && <span className="recent-time">SHA-256: {site.resultado.pdf_sha256}</span>}{site.resultado?.erro && <span className="site-error">{site.resultado.erro}</span>}</div>)}
                  </article>
                ))}
              </div>
            </section>
          </div>
        </section>
        <aside className="sidebar" aria-label="Informações">
          <h2 className="side-label">Antes de emitir</h2>
          <div className="side-callout"><strong>Seleção de certidões</strong><p>Marque uma ou mais fontes e use “Consultar selecionadas”, ou use o botão da própria linha para consultar somente aquela certidão.</p></div>
          <div className="side-callout"><strong>CAPTCHA humano</strong><p>Para CNPJ, CNDT, CGU e Comprovante CNPJ abrem em abas próprias com o documento preenchido. Resolva cada desafio no portal oficial e confirme cada aviso aqui; não injetamos nem automatizamos respostas de CAPTCHA.</p></div>
          <div className="side-callout"><strong>Arquivos da consulta</strong><p>Os PDFs emitidos são salvos juntos na pasta Downloads da consulta. Use “Abrir pasta” no histórico; falhas não são apresentadas como certidões emitidas.</p></div>
        </aside>
      </main>
      <footer className="footer">SIG-Certidões · execução local · o identificador completo permanece somente em memória durante a consulta.</footer>
      {captcha && <div className="modal-backdrop"><form className="captcha-modal" role="dialog" aria-modal="true" aria-labelledby="captcha-title" onSubmit={event => void resolveCaptcha(event)}><h2 id="captcha-title">{captcha.tipo === 'token' ? 'Autenticação necessária' : 'CAPTCHA necessário'} · {captcha.site_codigo}{captchaPrompts.length > 1 ? ` · ${captchaPrompts.length} pendentes` : ''}</h2><p>{captcha.mensagem || (captcha.tipo === 'token' ? 'Autentique com seu certificado digital/token na aba do SICAF e navegue até a certidão oficial que deseja imprimir. Confirme aqui quando a página da certidão estiver pronta.' : 'Resolva o desafio diretamente na aba oficial do portal aberta no navegador. Depois volte aqui e confirme. Não copie, envie ou automatize respostas/tokens do CAPTCHA.')}</p><div className="modal-actions"><button className="primary" type="submit">{captcha.tipo === 'token' ? 'Certidão pronta' : captcha.site_codigo === 'cndt' ? 'Já emiti no portal' : 'Já resolvi'}</button></div></form></div>}
    </>
  );
}