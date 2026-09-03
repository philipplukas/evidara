import type {
  DetailViewModel,
  FilterViewModel,
  SearchContextViewModel,
  SearchResultViewModel,
} from "./types";

// ─── Search Context ───

export const searchContext: SearchContextViewModel = {
  jurisdictions: [
    { key: "ch", label: "Switzerland", active: true, iconKey: "ch" },
    { key: "at", label: "Austria", active: true, iconKey: "at" },
  ],
  languages: [
    { key: "de", label: "DE", active: true },
    { key: "fr", label: "FR", active: false },
    { key: "it", label: "IT", active: false },
    { key: "en", label: "EN", active: false },
  ],
  sourceTypes: [
    { key: "all", label: "All", active: true },
    { key: "law", label: "Laws", active: false },
    { key: "decision", label: "Court decisions", active: false },
    { key: "rechtssatz", label: "Rechtssätze", active: false },
    { key: "commentary", label: "Commentary", active: false },
  ],
  exactMatches: [
    {
      id: "exact-1",
      type: "law",
      title: "Art. 754 OR",
      subtitle: "Obligationenrecht · Verantwortlichkeit",
      snippet: "",
      badges: [{ label: "Law", colorKey: "blue" }],
      metadataRows: [{ label: "Jurisdiction", value: "Switzerland", iconKey: "ch" }],
      relatedCounts: [],
      actions: [{ label: "Open article", icon: "arrow-right" }],
    },
  ],
};

// ─── Filters ───

export const filters: FilterViewModel[] = [
  {
    key: "jurisdiction",
    label: "Jurisdiction",
    type: "chip",
    options: [
      { value: "ch", label: "Switzerland", count: 14523, iconKey: "ch" },
      { value: "at", label: "Austria", count: 8291, iconKey: "at" },
    ],
    selected: ["ch", "at"],
  },
  {
    key: "language",
    label: "Language",
    type: "chip",
    options: [
      { value: "de", label: "DE", count: 18204 },
      { value: "fr", label: "FR", count: 3891 },
      { value: "it", label: "IT", count: 1203 },
      { value: "en", label: "EN", count: 516 },
    ],
    selected: ["de"],
  },
  {
    key: "court_level",
    label: "Court level",
    type: "checkbox",
    options: [
      { value: "supreme", label: "Supreme Court", count: 4521 },
      { value: "appellate", label: "Appellate Court", count: 3187 },
      { value: "cantonal", label: "Cantonal Court", count: 6892 },
      { value: "district", label: "District Court", count: 2103 },
    ],
    selected: [],
  },
  {
    key: "legal_area",
    label: "Legal area",
    type: "checkbox",
    options: [
      { value: "civil", label: "Civil law", count: 8934 },
      { value: "commercial", label: "Commercial law", count: 5621 },
      { value: "corporate", label: "Corporate law", count: 3412 },
      { value: "administrative", label: "Administrative law", count: 2891 },
      { value: "criminal", label: "Criminal law", count: 1843 },
      { value: "constitutional", label: "Constitutional law", count: 1102 },
    ],
    selected: [],
  },
  {
    key: "date",
    label: "Date",
    type: "dropdown",
    options: [
      { value: "any", label: "Any time" },
      { value: "1y", label: "Last year" },
      { value: "5y", label: "Last 5 years" },
      { value: "10y", label: "Last 10 years" },
    ],
    selected: ["any"],
  },
  {
    key: "has_commentary",
    label: "Has commentary",
    type: "toggle",
    options: [{ value: "true", label: "Yes" }],
    selected: [],
  },
  {
    key: "has_decisions",
    label: "Has related decisions",
    type: "toggle",
    options: [{ value: "true", label: "Yes" }],
    selected: [],
  },
];

// ─── Search Results ───

export const searchResults: SearchResultViewModel[] = [
  {
    id: "law-1",
    type: "law",
    title: "Art. 754 OR",
    subtitle: "Switzerland · Federal law",
    snippet:
      "Die Mitglieder des Verwaltungsrates und alle mit der Geschäftsführung oder mit der Liquidation befassten Personen sind sowohl der Gesellschaft als den einzelnen Aktionären und Gesellschaftsgläubigern für den Schaden verantwortlich, den sie durch absichtliche oder fahrlässige Verletzung ihrer Pflichten verursachen.",
    structuralContext: "Obligationenrecht › Gesellschaftsrecht › Verantwortlichkeit",
    badges: [{ label: "Law", colorKey: "blue", iconKey: "ch" }],
    metadataRows: [
      { label: "Enacted", value: "1911 (rev. 2020)" },
      { label: "In force", value: "01.01.2023" },
    ],
    relatedCounts: [
      { label: "Commentary", count: 8 },
      { label: "Court decisions", count: 142 },
      { label: "Citations", count: 56 },
    ],
    actions: [
      { label: "Open article", icon: "file-text" },
      { label: "Related", icon: "link" },
    ],
  },
  {
    id: "decision-1",
    type: "decision",
    title: "BGer 4A_123/2022",
    subtitle: "Federal Supreme Court · Switzerland",
    snippet:
      "Das Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt. Die Beweislast für sämtliche Haftungsvoraussetzungen liegt beim Kläger.",
    structuralContext: "BGE 148 III 234",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      { label: "Date", value: "15.03.2022" },
      { label: "Court", value: "Federal Supreme Court" },
      { label: "Chamber", value: "I. Civil Law Division" },
    ],
    relatedCounts: [
      { label: "Applies", count: 3 },
      { label: "Cited by", count: 27 },
      { label: "Commentary", count: 4 },
    ],
    actions: [
      { label: "Open decision", icon: "scale" },
      { label: "Related", icon: "link" },
    ],
  },
  {
    id: "commentary-1",
    type: "commentary",
    title: "Basler Kommentar OR II – Art. 754",
    subtitle: "Widmer/Banz · Helbing Lichtenhahn",
    snippet:
      "Die Verantwortlichkeitsklage nach Art. 754 OR ist das zentrale Instrument zur Durchsetzung von Schadenersatzansprüchen gegen die Organe der Aktiengesellschaft. Die Revision 2020 hat wesentliche Klarstellungen gebracht.",
    badges: [{ label: "Commentary", colorKey: "green" }],
    metadataRows: [
      { label: "Edition", value: "7th edition, 2023" },
      { label: "Article", value: "Art. 754 OR" },
    ],
    relatedCounts: [
      { label: "Related article", count: 1 },
      { label: "Decisions cited", count: 89 },
      { label: "External references", count: 34 },
    ],
    actions: [
      { label: "Open commentary", icon: "book-open" },
      { label: "View article", icon: "file-text" },
    ],
  },
  {
    id: "rs-1",
    type: "rechtssatz",
    title: "RS0023456",
    subtitle: "OGH · Austria",
    snippet:
      "Die Haftung der Vorstandsmitglieder einer Aktiengesellschaft setzt neben einer Pflichtverletzung auch ein Verschulden voraus. Der Sorgfaltsmassstab richtet sich nach einem ordentlichen Geschäftsleiter.",
    badges: [{ label: "Rechtssatz", colorKey: "indigo", iconKey: "at" }],
    metadataRows: [
      { label: "Court", value: "Oberster Gerichtshof" },
      { label: "Linked norms", value: "§ 84 AktG" },
    ],
    relatedCounts: [
      { label: "Linked decisions", count: 18 },
      { label: "Linked norms", count: 2 },
    ],
    actions: [
      { label: "Open", icon: "bookmark" },
      { label: "Related decision", icon: "scale" },
    ],
  },
  {
    id: "law-2",
    type: "law",
    title: "§ 84 AktG",
    subtitle: "Austria · Federal law",
    snippet:
      "Die Vorstandsmitglieder haben bei ihrer Geschäftsführung die Sorgfalt eines ordentlichen und gewissenhaften Geschäftsleiters anzuwenden. Vorstandsmitglieder, die ihre Obliegenheiten verletzen, sind der Gesellschaft zum Ersatz des daraus entstehenden Schadens als Gesamtschuldner verpflichtet.",
    structuralContext: "Aktiengesetz › Vorstand › Sorgfaltspflicht und Verantwortlichkeit",
    badges: [{ label: "Law", colorKey: "blue", iconKey: "at" }],
    metadataRows: [{ label: "Enacted", value: "1965 (rev. 2021)" }],
    relatedCounts: [
      { label: "Commentary", count: 5 },
      { label: "Rechtssätze", count: 23 },
      { label: "Court decisions", count: 87 },
    ],
    actions: [
      { label: "Open article", icon: "file-text" },
      { label: "Related", icon: "link" },
    ],
    contentLanguage: {
      display: "de",
      original: "de",
      isTranslation: false,
    },
  },
  {
    id: "decision-2",
    type: "decision",
    title: "OGH 6 Ob 35/21a",
    subtitle: "Oberster Gerichtshof · Austria",
    snippet:
      "Der OGH bestätigt die ständige Rechtsprechung zur Business Judgment Rule im österreichischen Aktienrecht. Ein Vorstandsmitglied handelt nicht pflichtwidrig, wenn es bei einer unternehmerischen Entscheidung vernünftigerweise annehmen durfte, auf der Grundlage angemessener Information zum Wohle der Gesellschaft zu handeln.",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "at" }],
    metadataRows: [
      { label: "Date", value: "22.09.2021" },
      { label: "Court", value: "Oberster Gerichtshof" },
    ],
    relatedCounts: [
      { label: "Applies", count: 2 },
      { label: "Cited by", count: 14 },
      { label: "Rechtssätze", count: 3 },
    ],
    actions: [
      { label: "Open decision", icon: "scale" },
      { label: "Related", icon: "link" },
    ],
  },
  {
    id: "law-3",
    type: "law",
    title: "Art. 752 OR",
    subtitle: "Switzerland · Federal law",
    snippet:
      "Gründer, welche bei der Gründung der Gesellschaft durch absichtliche oder fahrlässige Verletzung ihrer Pflichten die Gesellschaft, die Aktionäre oder die Gesellschaftsgläubiger geschädigt haben, sind diesen zum Ersatz des Schadens verpflichtet.",
    structuralContext: "Obligationenrecht › Gesellschaftsrecht › Verantwortlichkeit",
    badges: [{ label: "Law", colorKey: "blue", iconKey: "ch" }],
    metadataRows: [{ label: "Enacted", value: "1911 (rev. 2020)" }],
    relatedCounts: [
      { label: "Commentary", count: 3 },
      { label: "Court decisions", count: 31 },
    ],
    actions: [
      { label: "Open article", icon: "file-text" },
      { label: "Related", icon: "link" },
    ],
  },
  {
    id: "commentary-2",
    type: "commentary",
    title: "Zürcher Kommentar – Verantwortlichkeit",
    subtitle: "Forstmoser/Meier-Hayoz/Nobel",
    snippet:
      "Die gesellschaftsrechtliche Verantwortlichkeit bildet das Rückgrat des Minderheitenschutzes im schweizerischen Aktienrecht. Die vorliegende Kommentierung verbindet dogmatische Analyse mit der umfangreichen Bundesgerichtspraxis.",
    badges: [{ label: "Commentary", colorKey: "green" }],
    metadataRows: [
      { label: "Edition", value: "5th edition, 2022" },
      { label: "Article", value: "Art. 752–761 OR" },
    ],
    relatedCounts: [
      { label: "Related articles", count: 10 },
      { label: "Decisions cited", count: 213 },
    ],
    actions: [
      { label: "Open commentary", icon: "book-open" },
      { label: "View article", icon: "file-text" },
    ],
    contentLanguage: {
      display: "de",
      original: "de",
      isTranslation: false,
    },
  },
];

// ─── Detail: Article (Art. 754 OR) ───

export const articleDetail: DetailViewModel = {
  id: "law-1",
  type: "law",
  title: "Art. 754 OR",
  subtitle: "Verantwortlichkeit — Haftung der Verwaltung und der Geschäftsführung",
  breadcrumbs: [
    "Obligationenrecht",
    "Achtundzwanzigster Titel: Die Aktiengesellschaft",
    "Achter Abschnitt: Verantwortlichkeit",
    "Art. 754",
  ],
  metadata: [
    { label: "Jurisdiction", value: "Switzerland", iconKey: "ch", visibility: "always" },
    { label: "Law", value: "Obligationenrecht (OR)", visibility: "default" },
    { label: "Systematic number", value: "SR 220", visibility: "default" },
    { label: "In force since", value: "01.01.2023", visibility: "always" },
    { label: "Last revision", value: "Aktienrechtsrevision 2020", visibility: "expanded" },
  ],
  // Plain text, as the API really sends it: paragraphs split by blank lines,
  // no markup. This mock used to hold hand-written HTML with styling classes —
  // a shape no API response has ever produced — which is precisely why the
  // missing body went unnoticed for so long (#609).
  contentText: `Die Mitglieder des Verwaltungsrates und alle mit der Geschäftsführung oder mit der Liquidation befassten Personen sind sowohl der Gesellschaft als den einzelnen Aktionären und Gesellschaftsgläubigern für den Schaden verantwortlich, den sie durch absichtliche oder fahrlässige Verletzung ihrer Pflichten verursachen.

Wer die Erfüllung einer Aufgabe befugterweise einem anderen Organ überträgt, haftet für den von diesem verursachten Schaden, sofern er nicht nachweist, dass er bei der Auswahl, Unterrichtung und Überwachung die nach den Umständen gebotene Sorgfalt angewendet hat.`,
  tabs: [
    { key: "content", label: "Inhalt" },
    { key: "details", label: "Details" },
    { key: "related", label: "Related", count: 154 },
    { key: "references", label: "References", count: 56 },
    { key: "annotation", label: "Annotation" },
    { key: "structure", label: "Structure" },
  ],
  relatedGroups: [
    {
      groupLabel: "Court decisions",
      items: [
        {
          id: "d1",
          title: "BGer 4A_123/2022",
          subtitle: "Federal Supreme Court · 15.03.2022",
          badge: { label: "Decision", colorKey: "pink" },
        },
        {
          id: "d2",
          title: "BGer 4A_456/2021",
          subtitle: "Federal Supreme Court · 08.11.2021",
          badge: { label: "Decision", colorKey: "pink" },
        },
        {
          id: "d3",
          title: "BGer 4A_789/2020",
          subtitle: "Federal Supreme Court · 22.06.2020",
          badge: { label: "Decision", colorKey: "pink" },
        },
        {
          id: "d4",
          title: "HG Zürich HG190245",
          subtitle: "Handelsgericht Zürich · 03.09.2019",
          badge: { label: "Decision", colorKey: "pink" },
        },
      ],
    },
    {
      groupLabel: "Commentary",
      items: [
        {
          id: "c1",
          title: "Basler Kommentar OR II – Art. 754",
          subtitle: "Widmer/Banz · 7th ed. 2023",
          badge: { label: "Commentary", colorKey: "green" },
        },
        {
          id: "c2",
          title: "Zürcher Kommentar – Verantwortlichkeit",
          subtitle: "Forstmoser/Meier-Hayoz/Nobel · 5th ed. 2022",
          badge: { label: "Commentary", colorKey: "green" },
        },
      ],
    },
  ],
  references: [
    {
      direction: "Cited by",
      items: [
        {
          id: "r1",
          title: "Art. 756 OR",
          subtitle: "Klagerecht der Gesellschaft und der Aktionäre",
        },
        { id: "r2", title: "Art. 757 OR", subtitle: "Klagerecht der Gläubiger" },
        { id: "r3", title: "Art. 725a OR", subtitle: "Drohende Zahlungsunfähigkeit" },
      ],
    },
    {
      direction: "Cites",
      items: [
        { id: "r4", title: "Art. 717 OR", subtitle: "Sorgfalts- und Treuepflicht" },
        { id: "r5", title: "Art. 41 OR", subtitle: "Allgemeine Haftungsvoraussetzungen" },
      ],
    },
  ],
  annotations: [
    {
      title: "Article annotation",
      content:
        "Art. 754 OR regelt die zentrale Haftungsnorm für Gesellschaftsorgane im schweizerischen Aktienrecht. Die Bestimmung setzt vier kumulative Voraussetzungen voraus: (1) Pflichtverletzung, (2) Schaden, (3) adäquater Kausalzusammenhang und (4) Verschulden. Mit der Aktienrechtsrevision 2020 wurde Abs. 2 zur Delegationshaftung neu gefasst und die Exkulpationsmöglichkeit klargestellt.",
      provenance: "Synthesized from 142 court decisions and 8 commentary sources",
      sourceCount: 150,
      confidence: "High",
    },
  ],
  localStructure: {
    items: [
      { id: "art-752", label: "Art. 752 – Gründungshaftung", active: false },
      { id: "art-753", label: "Art. 753 – Emissionshaftung", active: false },
      { id: "art-754", label: "Art. 754 – Haftung der Verwaltung", active: true },
      { id: "art-755", label: "Art. 755 – Revisionshaftung", active: false },
      { id: "art-756", label: "Art. 756 – Klage der Gesellschaft", active: false },
    ],
  },
};

// ─── Detail: Court Decision (BGer 4A_123/2022) ───

export const decisionDetail: DetailViewModel = {
  id: "decision-1",
  type: "decision",
  title: "BGer 4A_123/2022",
  subtitle: "Verantwortlichkeit des Verwaltungsrats – Beweislastverteilung",
  breadcrumbs: ["Federal Supreme Court", "I. Civil Law Division", "4A_123/2022"],
  metadata: [
    { label: "Court", value: "Federal Supreme Court", iconKey: "ch", visibility: "always" },
    { label: "Date", value: "15.03.2022", visibility: "always" },
    { label: "Docket", value: "4A_123/2022", visibility: "default" },
    { label: "Publication", value: "BGE 148 III 234", visibility: "default" },
    { label: "Chamber", value: "I. Civil Law Division", visibility: "default" },
    { label: "Outcome", value: "Appeal dismissed", visibility: "always" },
  ],
  // The headnote, as its own field — the shape the API returns since #760. It
  // is also the opening of `contentText` below, because the seeded body text
  // of a Swiss decision starts with the printed Regeste.
  regeste: `Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder; Beweislastverteilung.

Das Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt. Die Beweislast für sämtliche Haftungsvoraussetzungen liegt beim Kläger (E. 3.2).`,
  contentText: `Regeste

Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder; Beweislastverteilung.

Das Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt. Die Beweislast für sämtliche Haftungsvoraussetzungen liegt beim Kläger (E. 3.2).

Die Sorgfaltspflicht der Verwaltungsratsmitglieder bemisst sich nach einem objektiven Massstab unter Berücksichtigung der konkreten Umstände des Einzelfalls (E. 4.1).`,
  tabs: [
    { key: "content", label: "Inhalt" },
    { key: "details", label: "Details" },
    { key: "related", label: "Related", count: 34 },
    { key: "references", label: "References", count: 12 },
  ],
  relatedGroups: [
    {
      groupLabel: "Applied norms",
      items: [
        {
          id: "n1",
          title: "Art. 754 OR",
          subtitle: "Haftung der Verwaltung",
          badge: { label: "Law", colorKey: "blue" },
        },
        {
          id: "n2",
          title: "Art. 717 OR",
          subtitle: "Sorgfalts- und Treuepflicht",
          badge: { label: "Law", colorKey: "blue" },
        },
        {
          id: "n3",
          title: "Art. 8 ZGB",
          subtitle: "Beweislast",
          badge: { label: "Law", colorKey: "blue" },
        },
      ],
    },
    {
      groupLabel: "Commentary",
      items: [
        {
          id: "c1",
          title: "Basler Kommentar OR II – Art. 754",
          subtitle: "Widmer/Banz",
          badge: { label: "Commentary", colorKey: "green" },
        },
      ],
    },
  ],
  references: [
    {
      direction: "Cited by",
      items: [
        { id: "cb1", title: "BGer 4A_567/2023", subtitle: "Federal Supreme Court · 12.01.2024" },
        { id: "cb2", title: "BGer 4A_890/2022", subtitle: "Federal Supreme Court · 05.09.2023" },
      ],
    },
    {
      direction: "Cites",
      items: [
        { id: "ct1", title: "BGE 132 III 564", subtitle: "Federal Supreme Court · 2006" },
        { id: "ct2", title: "BGE 139 III 24", subtitle: "Federal Supreme Court · 2013" },
        { id: "ct3", title: "BGE 144 III 93", subtitle: "Federal Supreme Court · 2018" },
      ],
    },
  ],
  annotations: [],
  localStructure: undefined,
};

// ─── Pivot Mock Data ───

export const pivotDecisionsForArt754: SearchResultViewModel[] = [
  {
    id: "decision-1",
    type: "decision",
    title: "BGer 4A_123/2022",
    subtitle: "Federal Supreme Court · Switzerland",
    snippet:
      "Das Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt.",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      { label: "Date", value: "15.03.2022" },
      { label: "Court", value: "Federal Supreme Court" },
    ],
    relatedCounts: [
      { label: "Applies", count: 3 },
      { label: "Cited by", count: 27 },
    ],
    actions: [{ label: "Open decision", icon: "scale" }],
  },
  {
    id: "pivot-d2",
    type: "decision",
    title: "BGer 4A_456/2021",
    subtitle: "Federal Supreme Court · Switzerland",
    snippet:
      "Zur Frage der Beweislastverteilung bei der aktienrechtlichen Verantwortlichkeit: Der Kläger trägt die Beweislast für Pflichtverletzung, Schaden und Kausalzusammenhang.",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      { label: "Date", value: "08.11.2021" },
      { label: "Court", value: "Federal Supreme Court" },
    ],
    relatedCounts: [
      { label: "Applies", count: 2 },
      { label: "Cited by", count: 14 },
    ],
    actions: [{ label: "Open decision", icon: "scale" }],
  },
  {
    id: "pivot-d3",
    type: "decision",
    title: "BGer 4A_789/2020",
    subtitle: "Federal Supreme Court · Switzerland",
    snippet:
      "Die Business Judgment Rule findet auch im schweizerischen Recht Anwendung. Verwaltungsratsmitglieder haften nicht für unternehmerische Fehlentscheidungen, sofern sie auf angemessener Informationsgrundlage getroffen wurden.",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      { label: "Date", value: "22.06.2020" },
      { label: "Court", value: "Federal Supreme Court" },
    ],
    relatedCounts: [
      { label: "Applies", count: 4 },
      { label: "Cited by", count: 31 },
    ],
    actions: [{ label: "Open decision", icon: "scale" }],
  },
  {
    id: "pivot-d4",
    type: "decision",
    title: "HG Zürich HG190245",
    subtitle: "Handelsgericht Zürich · Switzerland",
    snippet:
      "Das Handelsgericht Zürich bestätigt die Haftung eines Verwaltungsratsmitglieds wegen Verletzung der Sorgfaltspflicht bei der Genehmigung einer riskanten Investition ohne hinreichende Due Diligence.",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      { label: "Date", value: "03.09.2019" },
      { label: "Court", value: "Handelsgericht Zürich" },
    ],
    relatedCounts: [
      { label: "Applies", count: 1 },
      { label: "Cited by", count: 5 },
    ],
    actions: [{ label: "Open decision", icon: "scale" }],
  },
  {
    id: "pivot-d5",
    type: "decision",
    title: "BGE 139 III 24",
    subtitle: "Federal Supreme Court · Switzerland",
    snippet:
      "Grundsatzentscheid zur Solidarhaftung mehrerer Verwaltungsratsmitglieder nach Art. 754 OR. Die interne Regressordnung richtet sich nach dem Verschuldensanteil.",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      { label: "Date", value: "14.01.2013" },
      { label: "Court", value: "Federal Supreme Court" },
      { label: "Publication", value: "BGE 139 III 24" },
    ],
    relatedCounts: [
      { label: "Applies", count: 5 },
      { label: "Cited by", count: 89 },
    ],
    actions: [{ label: "Open decision", icon: "scale" }],
  },
];

// ─── Search Function (mock) ───

/** All available mock results for search filtering */
const allResults: SearchResultViewModel[] = [
  ...searchResults,
  ...pivotDecisionsForArt754.filter((r) => !searchResults.some((sr) => sr.id === r.id)),
];

/**
 * Simulates a search API call — filters mock data by query term.
 * Matches against title, subtitle, snippet, badges, and metadata.
 *
 * Swap this for a real API call when the backend is ready.
 */
export function searchMockResults(query: string): SearchResultViewModel[] {
  if (!query.trim()) return searchResults;

  const terms = query.toLowerCase().split(/\s+/);
  return allResults.filter((result) => {
    const searchable = [
      result.title,
      result.subtitle,
      result.snippet,
      result.structuralContext ?? "",
      ...result.badges.map((b) => b.label),
      ...result.metadataRows.map((r) => `${r.label} ${r.value}`),
    ]
      .join(" ")
      .toLowerCase();

    return terms.every((term) => searchable.includes(term));
  });
}
