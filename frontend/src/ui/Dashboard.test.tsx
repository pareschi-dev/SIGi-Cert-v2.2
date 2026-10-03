// Regression tests for the frontend dependency upgrade baseline.
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { addRecentCnpj, Dashboard } from './Dashboard';

describe('Dashboard rendering', () => {
  it('renders the certificate consultation form and catalog summary', () => {
    const markup = renderToStaticMarkup(<Dashboard />);

    expect(markup).toContain('Central de certidões');
    expect(markup).toContain('Sites no catálogo');
    expect(markup).toContain('value="CNPJ"');
    expect(markup).toContain('CPF/CNPJ não é persistido em claro');
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
