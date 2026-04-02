/**
 * Core i18n module tests.
 *
 * Tests locale resolution from Accept-Language headers and
 * translation key lookup via t().
 */
import { describe, expect, it } from 'vitest';
import { resolveLocale, t } from '../../core/i18n';

// ─── resolveLocale ───

describe('resolveLocale', () => {
  it('should default to "de" when no header', () => {
    expect(resolveLocale()).toBe('de');
    expect(resolveLocale(undefined)).toBe('de');
    expect(resolveLocale('')).toBe('de');
  });

  it('should resolve simple language codes', () => {
    expect(resolveLocale('de')).toBe('de');
    expect(resolveLocale('fr')).toBe('fr');
  });

  it('should resolve region-tagged codes', () => {
    expect(resolveLocale('fr-CH')).toBe('fr');
    expect(resolveLocale('de-AT')).toBe('de');
  });

  it('should resolve weighted Accept-Language headers', () => {
    expect(resolveLocale('fr-CH, de;q=0.9')).toBe('fr');
    expect(resolveLocale('de, fr;q=0.9')).toBe('de');
    expect(resolveLocale('en, fr;q=0.8, de;q=0.5')).toBe('fr');
  });

  it('should fall back to "de" for unsupported languages', () => {
    expect(resolveLocale('en')).toBe('de');
    expect(resolveLocale('it')).toBe('de');
    expect(resolveLocale('ja')).toBe('de');
  });

  it('should handle wildcard', () => {
    expect(resolveLocale('*')).toBe('de');
  });
});

// ─── t() ───

describe('t', () => {
  it('should resolve German keys by default', () => {
    expect(t('tabs.content')).toBe('Inhalt');
    expect(t('labels.all')).toBe('Alle');
  });

  it('should resolve French keys with locale "fr"', () => {
    expect(t('tabs.content', 'fr')).toBe('Contenu');
    expect(t('labels.all', 'fr')).toBe('Tous');
  });

  it('should fall back to the key for unknown keys', () => {
    expect(t('nonexistent.key')).toBe('nonexistent.key');
    expect(t('nonexistent.key', 'fr')).toBe('nonexistent.key');
  });
});

// ─── Key Parity ───

describe('translation key parity', () => {
  it('should have identical keys in de.json and fr.json', async () => {
    const de = await import('./de.json');
    const fr = await import('./fr.json');
    const deKeys = Object.keys(de).filter((k) => k !== 'default').sort();
    const frKeys = Object.keys(fr).filter((k) => k !== 'default').sort();
    expect(frKeys).toEqual(deKeys);
  });
});
