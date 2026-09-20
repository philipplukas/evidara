/**
 * Shared legal terminology — the words both legal-search surfaces must agree on.
 *
 * ## Why this file exists
 *
 * ADR-0013 draws the ownership line correctly: the BFF owns every display label
 * it sends, the frontend owns the chrome the API never sends. What the ADR did
 * not settle is what happens when the *same domain concept* appears on both
 * sides of that line — and it does, constantly, because the frontend has to
 * write prose about the things the BFF labels.
 *
 * Nothing compared the two, so they drifted, and the drift was visible on one
 * screen: the detail panel's tab strip read **"Zitationen"** (from the BFF,
 * `tabs.citations`, rendered by `DetailTabs.tsx:36`) while the heading directly
 * beneath it read **"Verweise"** (from the frontend, `detail.tabs.references`,
 * rendered by `ReferencesTab.tsx:97`), and the group headings between them fell
 * back to **"Referenzen"** (`labels.references`). Three German words, one
 * concept, one viewport. "Zitation" is not even the right word: in German it is
 * a court summons, or a bibliometrics anglicism.
 *
 * This is AGENTS.md's "the same rule enforced in two clients rather than once
 * behind them" in the terminology layer. The easier path won, and it was the
 * weaker one.
 *
 * ## How it is prevented
 *
 * This table is the single source of truth for those shared words, and
 * `terminology.spec.ts` is the single enforcement point — one test that reads
 * *both* surfaces' message files and fails when they disagree with the table or
 * with each other. It deliberately does not live in each surface: two guards is
 * the defect, not the fix.
 *
 * Every term carries the `evidence` that establishes it. The words are derived
 * from the corpus this product indexes and from the publishers' own statutes,
 * never chosen by taste. Counts cited below were measured on 2026-09-20 against
 * the production read alias `documents-read-20260729111140` (1,784 documents,
 * all `jurisdiction: CH`, sourced from the Zürich Gesetzessammlung).
 *
 * ## Changing a word
 *
 * Change it here first. The spec will then name every key on either surface
 * that still carries the old one.
 */

import type { SupportedLocale } from './locale';

/** A concept whose word must be identical wherever either surface renders it. */
export interface SharedTerm {
  /** Stable identifier, used in failure messages. */
  concept: string;
  /** The canonical word per UI locale. */
  terms: Record<SupportedLocale, string>;
  /** What establishes the word. Required — a term with no source is taste. */
  evidence: string;
  /** Keys in `de.json`/`fr.json` whose value must equal the term exactly. */
  apiKeys: string[];
  /** Dotted paths in the frontend messages whose value must equal the term. */
  frontendKeys: string[];
  /** Dotted frontend paths whose value must *contain* the stem (prose). */
  frontendPhrases: string[];
  /**
   * The substring a prose binding must contain, per locale, when the term
   * itself is the wrong form to search for. Prose inflects: the French
   * heading is "Aucune référence" (singular) while the term is "Références"
   * (plural), and a literal containment check on the term reads that correct
   * string as a violation. Defaults to the term when omitted; matched
   * case-insensitively.
   */
  stems?: Partial<Record<SupportedLocale, string>>;
}

/**
 * A word withdrawn from a locale's UI. It must not reappear on either surface.
 *
 * Listed per locale because the surfaces are not symmetric: "Referenz" is an
 * anglicism in German and the native, correct word in French.
 */
export interface RetiredTerm {
  /** Matched whole-word and case-insensitively. Inflections are listed. */
  words: string[];
  locale: SupportedLocale;
  /** The `concept` of the SharedTerm that replaced it. */
  replacedBy: string;
  reason: string;
}

export const SHARED_TERMS: SharedTerm[] = [
  {
    concept: 'crossReference',
    terms: { de: 'Verweise', fr: 'Références' },
    evidence:
      'Zürich PublG 170.5 § 8 is titled "Verweisung auf Normen Dritter" and PublV 170.51 § 18 ' +
      'reads "die Verweisung auf die Fundstelle" — the canton\'s own publication statutes use ' +
      'the verweisen stem for a norm pointing at another norm, and pair it with Fundstelle ' +
      'exactly as this product does. "Zitation" and "Referenz" each occur in 0 of 1,784 ' +
      'indexed documents. Note that bare "Verweis" is polysemous in this corpus — 14 documents ' +
      'use "schriftlicher Verweis" for a disciplinary reprimand — but the sense cannot arise ' +
      'for a list attached to a norm. French is not adjudicated by the corpus, which is ' +
      'German-only; "Références" is the word the frontend already used and is native French.',
    stems: { de: 'Verweis', fr: 'référence' },
    apiKeys: ['counts.citations', 'tabs.citations', 'labels.references'],
    frontendKeys: ['detail.tabs.references'],
    frontendPhrases: [
      'detail.descriptions.references',
      'detail.empty.noReferencesTitle',
      'detail.empty.noReferencesDescription',
    ],
  },
  {
    concept: 'citationLocator',
    terms: { de: 'Fundstelle', fr: 'Citation officielle' },
    evidence:
      'Already correct on the API side and kept as the anchor the frontend must match. ' +
      'Zürich PublV 170.51 § 18 requires that "die Verweisung auf die Fundstelle aktuell" be ' +
      'kept; 15 indexed documents use the word. The frontend called the same thing "Zitat".',
    stems: { de: 'Fundstelle', fr: 'citation officielle' },
    apiKeys: ['metadata.citation'],
    frontendKeys: [],
    frontendPhrases: ['detail.copyCitation'],
  },
  {
    concept: 'legalOrder',
    terms: { de: 'Rechtsordnung', fr: 'Ordre juridique' },
    evidence:
      "The facet's values are polities (Schweiz, Kanton Zürich), i.e. a legal order. " +
      '"Zuständigkeit" occurs in 531 indexed documents and every sampled use is an authority\'s ' +
      'competence — "Zuständigkeit der Gemeinden", "Zuständigkeit des Kantonsrates" — which is ' +
      'a different thing. Of the candidates only "Rechtsordnung" (42 documents, used as "die ' +
      'Rechtsordnung des Landes") names the legal order itself; "Geltungsbereich" (476) is a ' +
      'norm\'s own scope of application, and "Rechtsraum" and "Jurisdiktion" occur 0 times. ' +
      'French "Juridiction" carries the same court/competence sense the German term did.',
    stems: { de: 'Rechtsordnung', fr: 'ordre juridique' },
    apiKeys: ['metadata.jurisdiction', 'facets.jurisdiction'],
    frontendKeys: [],
    frontendPhrases: ['filter.sheetDescription'],
  },
  {
    concept: 'courtDecisionPlural',
    terms: { de: 'Gerichtsentscheide', fr: 'Décisions judiciaires' },
    evidence:
      'contracts/vocabularies/document-type.json pins `decision` to de "Gerichtsentscheid" / ' +
      'fr "Décision judiciaire". The frontend said "Urteile"/"Arrêts", which is narrower — a ' +
      'Urteil is one kind of Entscheid, and the corpus also holds Beschlüsse and Verfügungen.',
    apiKeys: ['plurals.decision', 'counts.courtDecisions'],
    frontendKeys: ['results.sourceTypes.decision'],
    frontendPhrases: ['results.empty.startHint'],
  },
  {
    concept: 'rechtssatzPlural',
    terms: { de: 'Rechtssätze', fr: 'Principes juridiques' },
    evidence:
      'contracts/vocabularies/document-type.json pins `rechtssatz` to fr "Principe juridique". ' +
      'The frontend\'s fr.json carried the untranslated German "Rechtssätze".',
    apiKeys: ['plurals.rechtssatz'],
    frontendKeys: ['results.sourceTypes.rechtssatz'],
    frontendPhrases: [],
  },
  {
    concept: 'lawPlural',
    terms: { de: 'Gesetze', fr: 'Lois' },
    evidence:
      'contracts/vocabularies/document-type.json pins `law` to de "Gesetz" / fr "Loi". Listed ' +
      'although both surfaces already agree: a guard that covers only what broke does not stop ' +
      'the next one.',
    apiKeys: ['plurals.law'],
    frontendKeys: ['results.sourceTypes.law'],
    frontendPhrases: [],
  },
  {
    concept: 'commentaryPlural',
    terms: { de: 'Kommentare', fr: 'Commentaires' },
    evidence:
      'contracts/vocabularies/document-type.json pins `commentary` to de "Kommentar" / ' +
      'fr "Commentaire". Both surfaces already agree; pinned for the same reason as lawPlural.',
    apiKeys: ['plurals.commentary', 'counts.commentary'],
    frontendKeys: ['results.sourceTypes.commentary'],
    frontendPhrases: [],
  },
];

export const RETIRED_TERMS: RetiredTerm[] = [
  {
    words: ['Zitation', 'Zitationen'],
    locale: 'de',
    replacedBy: 'crossReference',
    reason:
      'In German a Zitation is a court summons (Ladung), or a bibliometrics anglicism. It ' +
      'occurs in 0 of 1,784 indexed Swiss legal documents.',
  },
  {
    words: ['Referenz', 'Referenzen'],
    locale: 'de',
    replacedBy: 'crossReference',
    reason:
      'A second anglicism for the concept crossReference already names. 0 occurrences in the ' +
      'corpus. (The French "Référence" is native and is the chosen term there.)',
  },
  {
    words: ['Zuständigkeit', 'Zuständigkeiten'],
    locale: 'de',
    replacedBy: 'legalOrder',
    reason:
      "An authority's or court's competence, not a legal order. Used 531 times in the corpus, " +
      'always in the competence sense.',
  },
  {
    words: ['Gerichtsbarkeit'],
    locale: 'de',
    replacedBy: 'legalOrder',
    reason:
      'The judicial power or the court system — a third word the frontend used for the facet ' +
      'the API labelled "Zuständigkeit".',
  },
  {
    words: ['Rechtssätze', 'Rechtssatz'],
    locale: 'fr',
    replacedBy: 'rechtssatzPlural',
    reason: 'Untranslated German inside the French message file.',
  },
  {
    words: ['Juridiction', 'juridictions'],
    locale: 'fr',
    replacedBy: 'legalOrder',
    reason: 'Carries the same court/competence sense that made "Zuständigkeit" wrong in German.',
  },
];
