// DEMO CONTENT (issue #30). Producers, organizations, numbers and datasets are SYNTHETIC.
// Standard clauses are REAL APS/FPS IDs from data/src/fx_data/clauses.json (#9); a test fails
// if any cited clause doesn't exist. Clause choices are the team's mapping, for FTUSA to confirm.
// When the chat API (#25) lands, answers come from the agent instead of this file.

export interface Bilingual { en: string; es?: string }
export interface Insight { text: Bilingual; source: string; period: string; strength: 'exact' | 'nearest' | 'limited'; clause: string }
export interface Peer {
  text: Bilingual; org: string; place: string; coords: { lat: number; lon: number }
  tradeoff?: Bilingual; match: { crop: boolean; entity: boolean; country: boolean }; clause: string
}
export interface ChartBar { label: Bilingual; value: number; ref?: boolean }
export interface Scenario {
  id: string; name: string; entityType: string; crop: string; region: string; language: 'en' | 'es'
  scenario: string; summary: Bilingual; coords: { lat: number; lon: number }
  chart: { title: Bilingual; unit: string; source: string; bars: ChartBar[] }
  tags: [ChallengeTag, ...ChallengeTag[]]
  premiumProjects: { year: number; project: string; amount: string }[]
  survey: { year: number; item: string; value: string }
  certification: { standard: string; status: string; since: number }
  chips: Record<'open' | 'timing' | 'severity' | 'tried', Bilingual[]>
  insights: Insight[]; peers: Peer[]
}

export const CHALLENGE_TAGS = [
  'climate and weather', 'water', 'soil and land', 'market and price',
  'labor and migration', 'financial and access to capital', 'education',
  'health', 'infrastructure', 'biodiversity and conservation', 'social and community',
] as const
export type ChallengeTag = (typeof CHALLENGE_TAGS)[number]

export const scenarios: Scenario[] = [
  {
    id: 'P-001',
    name: 'Cooperativa Café Alto Cauca',
    entityType: 'cooperative',
    crop: 'coffee',
    region: 'Cauca, Colombia',
    language: 'es',
    scenario: 'Drought',
    summary: {
      en: 'Rainfall near the centre of Cauca averaged 11.5% below the 10-year average over 2024 and 2025: 2024 was about 20% below, and 2025 was about 3% below. Water stress in the area is rated low to medium and is projected to stay in that band. Two cooperatives in similar conditions used Premium funds for rainwater collection and shade trees.',
      es: 'La lluvia cerca del centro de Cauca estuvo en promedio un 11,5% por debajo del promedio de 10 años en 2024 y 2025: 2024 estuvo cerca de un 20% por debajo y 2025 cerca de un 3% por debajo. El estrés hídrico de la zona se califica de bajo a medio y se proyecta que siga en ese nivel. Dos cooperativas en condiciones similares usaron fondos del Premium para captar agua lluvia y sembrar árboles de sombra.',
    },
    coords: { lat: 2.45, lon: -76.6 },
    chart: {
      title: { en: 'Annual rainfall in Cauca vs. 2014–2023 average', es: 'Lluvia anual en Cauca vs. promedio 2014–2023' },
      unit: 'mm', source: 'CHIRPS v2.0 rainfall anomaly, Cauca, Colombia, 2024-2025 [RF-F8C4E1]',
      bars: [
        { label: { en: '2014–23 avg', es: 'Prom. 2014–23' }, value: 2103, ref: true },
        { label: { en: '2024', es: '2024' }, value: 1675 },
        { label: { en: '2025', es: '2025' }, value: 2048 },
      ],
    },
    tags: ['climate and weather', 'water'],
    premiumProjects: [
      { year: 2023, project: 'Community water storage tanks', amount: 'US$18,000' },
      { year: 2024, project: 'Coffee rust training for members', amount: 'US$6,500' },
    ],
    survey: { year: 2025, item: 'Top concern reported', value: 'Unreliable rainfall' },
    certification: { standard: 'APS', status: 'Certified', since: 2016 },
    chips: {
      open: [{ es: 'La lluvia ha sido muy irregular en las últimas dos temporadas y la última cosecha bajó.', en: 'Rainfall has been very irregular for the last two seasons and the last harvest dropped.' }],
      timing: [{ es: 'Empezó hace unos dos años, en 2024.', en: 'It started about two years ago, in 2024.' }],
      severity: [{ es: 'La cosecha bajó como un 30% y varios socios tienen deudas.', en: 'The harvest dropped about 30% and several members are in debt.' }],
      tried: [{ es: 'Algunos socios sembraron más sombra, pero no alcanza.', en: 'Some members planted more shade trees, but it is not enough.' }],
    },
    insights: [
      {
        text: { es: 'La lluvia cerca del centro de Cauca promedió 1.861 mm al año en 2024–2025, un 11,5% por debajo del promedio de 2014–2023 (2.103 mm). 2024 estuvo cerca de un 20% por debajo y 2025 cerca de un 3% por debajo.', en: 'Rainfall near the centre of Cauca averaged 1,861 mm a year in 2024–2025, 11.5% below the 2014–2023 average of 2,103 mm. 2024 was about 20% below and 2025 about 3% below.' },
        source: 'CHIRPS v2.0 rainfall anomaly, Cauca, Colombia, 2024-2025 [RF-F8C4E1]', period: '2014–2025', strength: 'nearest',
        clause: 'APS 4.1.1',
      },
      {
        text: { es: 'WRI Aqueduct califica el estrés hídrico de la cuenca cerca del centro de Cauca como bajo a medio (10-20%) y proyecta que seguirá en ese nivel en 2030 y 2050, con un aumento leve del índice.', en: 'WRI Aqueduct rates water stress in the river basin near the centre of Cauca as low to medium (10-20%) and projects it stays in that band in 2030 and 2050, with the score rising slightly.' },
        source: 'WRI Aqueduct 4.0 projected water stress, Cauca, Colombia, 2030-2050 [RF-E680B5]', period: '2030–2050 projection', strength: 'nearest',
        clause: 'APS 4.1.1',
      },
      {
        text: { es: 'Su propio registro muestra que en 2023 su comité ya invirtió Premium en tanques de agua comunitarios.', en: 'Your own record shows your committee already invested Premium in community water tanks in 2023.' },
        source: 'Your organization’s Premium record (synthetic)', period: '2023', strength: 'exact',
        clause: 'APS 1.2.2',
      },
    ],
    peers: [
      {
        text: { es: 'Una cooperativa cafetera en Huila financió sistemas de captación de agua lluvia con su Premium.', en: 'A coffee cooperative in Huila used its Premium to fund rainwater catchment systems.' },
        org: 'Cooperativa Ejemplo Huila (fictional)', place: 'Huila, Colombia', coords: { lat: 2.53, lon: -75.53 },
        tradeoff: { en: 'Took about a year to build. The cost was shared across members.', es: 'Tomó cerca de un año construirlo. El costo se compartió entre los socios.' }, match: { crop: true, entity: true, country: true },
        clause: 'APS 4.1.1',
      },
      {
        text: { es: 'Una cooperativa en Honduras financió viveros de árboles de sombra para reducir el estrés por calor.', en: 'A cooperative in Honduras funded shade-tree nurseries to reduce heat stress.' },
        org: 'Cooperativa Ejemplo Copán (fictional)', place: 'Copán, Honduras', coords: { lat: 14.84, lon: -89.15 },
        tradeoff: { en: 'Trees take 2–3 years to give useful shade.', es: 'Los árboles tardan 2–3 años en dar sombra útil.' }, match: { crop: true, entity: true, country: false },
        clause: 'APS 4.2.1',
      },
    ],
  },
  {
    id: 'P-002',
    name: 'Unión de Productores Sierra Norte',
    entityType: 'cooperative',
    crop: 'coffee',
    region: 'Oaxaca, Mexico',
    language: 'en',
    scenario: 'Price drop',
    summary: {
      en: 'The international arabica benchmark price was 16.9% lower in October 2026 than a year earlier, though still about 18% above its 5-year average. This is a world market price, not what a cooperative is paid. Other cooperatives have used Premium funds to add value, such as roasting their own coffee or improving quality to reach specialty buyers.',
    },
    coords: { lat: 17.06, lon: -96.72 },
    chart: {
      title: { en: 'International arabica benchmark price, past year', es: 'Precio internacional de referencia del arábica, último año' },
      unit: 'US$/kg', source: 'World Bank Pink Sheet (Coffee, Arabica) coffee price, global, October 2026 [RF-74608A]',
      bars: [
        { label: { en: 'Oct ’25', es: 'Oct ’25' }, value: 8.90, ref: true },
        { label: { en: 'Jan', es: 'Ene' }, value: 8.02 },
        { label: { en: 'Apr', es: 'Abr' }, value: 7.30 },
        { label: { en: 'Jul', es: 'Jul' }, value: 7.91 },
        { label: { en: 'Oct ’26', es: 'Oct ’26' }, value: 7.40 },
      ],
    },
    tags: ['market and price', 'financial and access to capital'],
    premiumProjects: [
      { year: 2022, project: 'Shared drying patio', amount: 'US$22,000' },
      { year: 2024, project: 'Member emergency loan fund', amount: 'US$15,000' },
    ],
    survey: { year: 2025, item: 'Top concern reported', value: 'Income instability' },
    certification: { standard: 'APS', status: 'Certified', since: 2014 },
    chips: {
      open: [{ en: 'The price we get for our coffee has dropped a lot and members are struggling to cover costs.' }],
      timing: [{ en: 'Since the start of this harvest season, about six months ago.' }],
      severity: [{ en: 'Some members are thinking about leaving coffee altogether.' }],
      tried: [{ en: 'We tried selling some coffee locally, but volumes are small.' }],
    },
    insights: [
      {
        text: { en: 'World Bank data puts the international arabica benchmark at US$7.40 per kg in October 2026, 16.9% lower than a year earlier and 18% above its 5-year average. This is a world market price, not a farm-gate price.' },
        source: 'World Bank Pink Sheet (Coffee, Arabica) coffee price, global, October 2026 [RF-74608A]', period: 'Oct 2025 – Oct 2026', strength: 'limited',
        clause: 'APS 5.2.3',
      },
      {
        text: { en: 'Your own record shows a member emergency loan fund created with Premium in 2024.' },
        source: 'Your organization’s Premium record (synthetic)', period: '2024', strength: 'exact',
        clause: 'APS 1.2.2',
      },
    ],
    peers: [
      {
        text: { en: 'A cooperative in Chiapas used Premium to build a small roasting operation and sell roasted coffee regionally.' },
        org: 'Ejemplo Chiapas Cooperative (fictional)', place: 'Chiapas, Mexico', coords: { lat: 16.75, lon: -92.63 },
        tradeoff: { en: 'Needed training and a roaster. Sales started small.' }, match: { crop: true, entity: true, country: true },
        clause: 'APS 1.2.2',
      },
      {
        text: { en: 'A Peruvian cooperative funded quality-cupping training to reach higher-value specialty buyers.' },
        org: 'Ejemplo Cajamarca Cooperative (fictional)', place: 'Cajamarca, Peru', coords: { lat: -7.16, lon: -78.5 },
        tradeoff: { en: 'Quality improves gradually. Buyers look for consistency over several harvests.' }, match: { crop: true, entity: true, country: false },
        clause: 'APS 1.2.2',
      },
    ],
  },
  {
    id: 'P-003',
    name: 'Soubré Smallholder Group',
    entityType: 'smallholder',
    crop: 'cocoa',
    region: 'Nawa (Soubré), Côte d’Ivoire',
    language: 'en',
    scenario: 'Labor shortage',
    summary: {
      en: 'The evidence here is limited, but regional data suggests more young people are leaving rural areas, and your own survey lists harvest labor as your top concern. A cocoa group in Ghana bought shared tools that reduce the work needed at harvest.',
    },
    coords: { lat: 5.78, lon: -6.6 },
    chart: {
      title: { en: 'Rural youth leaving the area each year (limited evidence)', es: 'Jóvenes rurales que dejan la zona cada año (evidencia limitada)' },
      unit: '%', source: 'Regional migration fact table (hand-curated stand-in)',
      bars: [
        { label: { en: '2020', es: '2020' }, value: 8, ref: true },
        { label: { en: '2021', es: '2021' }, value: 9 },
        { label: { en: '2022', es: '2022' }, value: 11 },
        { label: { en: '2023', es: '2023' }, value: 12 },
        { label: { en: '2024', es: '2024' }, value: 13 },
        { label: { en: '2025', es: '2025' }, value: 14 },
      ],
    },
    tags: ['labor and migration', 'social and community'],
    premiumProjects: [
      { year: 2023, project: 'Village primary school roof', amount: 'US$9,000' },
    ],
    survey: { year: 2025, item: 'Top concern reported', value: 'Not enough workers at harvest' },
    certification: { standard: 'APS', status: 'Certified', since: 2019 },
    chips: {
      open: [{ en: 'We cannot find enough people to help with the cocoa harvest anymore.' }],
      timing: [{ en: 'It got worse over the last two harvests.' }],
      severity: [{ en: 'Some pods were left on the trees and rotted.' }],
      tried: [{ en: 'We share labor between families, but young people are moving to the city.' }],
    },
    insights: [
      {
        text: { en: 'Regional data suggests rural youth migration from your area has risen over the last five years.' },
        source: 'Regional migration fact table (hand-curated stand-in)', period: '2020–2025', strength: 'limited',
        clause: 'APS 3.3.1',
      },
      {
        text: { en: 'Your own survey from 2025 lists “not enough workers at harvest” as your top concern.' },
        source: 'Your organization’s survey record (synthetic)', period: '2025', strength: 'exact',
        clause: 'APS 3.3.1',
      },
    ],
    peers: [
      {
        text: { en: 'A cocoa group in Ghana used Premium to buy shared pod-breaking tools, reducing labor needed at harvest.' },
        org: 'Ejemplo Ashanti Cocoa Group (fictional)', place: 'Ashanti, Ghana', coords: { lat: 6.69, lon: -1.62 },
        tradeoff: { en: 'Tools need to be shared fairly and looked after by the group.' }, match: { crop: true, entity: true, country: false },
        clause: 'APS 3.2.4',
      },
    ],
  },
]
