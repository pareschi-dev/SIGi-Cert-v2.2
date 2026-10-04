// Regression tests for the frontend dependency upgrade baseline.
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { addRecentCnpj, Dashboard, movePdfInOrder } from './Dashboard';

describe('Dashboard rendering', () => {
  it('renders the certificate consultation form without summary metrics', () => {
    const markup = renderToStaticMarkup(<Dashboard />);

    expect(markup).toContain('Central de certidões');
    expect(markup).toContain('aria-label="SIGi início"');
    expect(markup).toContain('Sistema Inteligente de Gestão Integrada');
    expect(markup).not.toContain('Sites no catálogo');
    expect(markup).not.toContain('Fluxos automatizados');
    expect(markup).not.toContain('Solicitações recentes');
    expect(markup).toContain('value="CNPJ"');
    expect(markup).toContain('CPF/CNPJ não é persistido em claro');
    expect(markup).toContain('Pasta da sessão');
    expect(markup).toContain('Inicie uma consulta para criar a pasta');
  });

  it('shows an empty consultation history before data is loaded', () => {
    const markup = renderToStaticMarkup(<Dashboard />);

    expect(markup).toContain('Histórico de consultas');
    expect(markup).toContain('Nenhuma consulta iniciada ainda.');
  });

  it('renders the document input as an accessible recent-entry combobox', () => {
    const markup = renderToStaticMarkup(<Dashboard />);

    expect(markup).toContain('role="combobox"');
    expect(markup).toContain('aria-autocomplete="list"');
  });
});

describe('CNPJ session history', () => {
  it('keeps only the five most recent unique CNPJs, comparing digits only', () => {
    const history = [
      '11.111.111/1111-11',
      '22.222.222/2222-22',
      '33.333.333/3333-33',
      '44.444.444/4444-44',
      '55.555.555/5555-55',
    ];

    expect(addRecentCnpj(history, '11.111.111/1111-11')).toEqual([
      '11.111.111/1111-11',
      '22.222.222/2222-22',
      '33.333.333/3333-33',
      '44.444.444/4444-44',
      '55.555.555/5555-55',
    ]);
    expect(addRecentCnpj(history, '66.666.666/6666-66')).toEqual([
      '66.666.666/6666-66',
      ...history.slice(0, 4),
    ]);
  });

  it('does not add blank values', () => {
    const history = ['11.111.111/1111-11'];

    expect(addRecentCnpj(history, '   ')).toBe(history);
  });
});

describe('PDF merge ordering', () => {
  it('moves a PDF to the requested position without losing other files', () => {
    expect(movePdfInOrder(['a.pdf', 'b.pdf', 'c.pdf'], 'c.pdf', 0)).toEqual([
      'c.pdf', 'a.pdf', 'b.pdf',
    ]);
  });

  it('leaves order unchanged for an unknown file or invalid position', () => {
    const files = ['a.pdf', 'b.pdf'];
    expect(movePdfInOrder(files, 'missing.pdf', 0)).toBe(files);
    expect(movePdfInOrder(files, 'a.pdf', 4)).toBe(files);
  });
});
