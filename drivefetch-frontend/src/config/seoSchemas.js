/**
 * src/config/seoSchemas.js
 *
 * Schema.org JSON-LD nodes, one export per route.
 *
 * All of them build their URLs from siteConfig, so they follow VITE_SITE_URL
 * along with the canonicals. Nodes that describe the same entity share an @id
 * (`#organization`, `#website`) so Google merges them into one knowledge-graph
 * entity instead of treating each page as a separate publisher.
 */
import { siteConfig, absoluteUrl, assetUrl, organizationSchema } from './siteConfig';

const BASE = siteConfig.url;

/** Shared publisher reference — avoids repeating the full Organization node. */
const publisherRef = { '@id': `${BASE}/#organization` };

/* ─────────────────────────────────────────────────────────────
   HOME  /
   WebSite (+ SearchAction) · WebApplication · Organization
   ───────────────────────────────────────────────────────────── */
export const homeSchema = [
  {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': `${BASE}/#website`,
    name: siteConfig.name,
    alternateName: [siteConfig.alternateName, 'DriveFetch Pakistan'],
    url: `${BASE}/`,
    description: siteConfig.description,
    inLanguage: 'en-PK',
    publisher: publisherRef,
    potentialAction: {
      '@type': 'SearchAction',
      target: {
        '@type': 'EntryPoint',
        urlTemplate: `${BASE}/?q={search_term_string}`,
      },
      'query-input': 'required name=search_term_string',
    },
  },
  {
    '@context': 'https://schema.org',
    ...organizationSchema,
  },
  {
    '@context': 'https://schema.org',
    '@type': 'WebApplication',
    '@id': `${BASE}/#webapp`,
    name: siteConfig.name,
    alternateName: siteConfig.alternateName,
    url: `${BASE}/`,
    applicationCategory: 'AutomotiveApplication',
    applicationSubCategory: 'Used Car Search & Valuation',
    operatingSystem: 'Any (web browser)',
    browserRequirements: 'Requires JavaScript',
    description: siteConfig.description,
    image: assetUrl(siteConfig.ogImage),
    inLanguage: 'en-PK',
    publisher: publisherRef,
    featureList: [
      'Multi-platform used car search (PakWheels, OLX, Gari.pk, Drive.pk)',
      'AI car matchmaker based on budget, city and lifestyle',
      'Vehicle token tax calculator for ICT, Punjab, Sindh and KPK',
      'FBR Section 231B transfer fee calculator',
      'Monthly fuel cost estimator',
      'AI listing inspection and red-flag detection',
    ],
    // Free product: an Offer with price 0 is the correct way to state this.
    // Omitting it entirely leaves Google guessing; a fake aggregateRating
    // would be a structured-data violation, so there is none here.
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'PKR',
      availability: 'https://schema.org/InStock',
    },
  },
];

/* ─────────────────────────────────────────────────────────────
   AI MATCHMAKER  /recommend
   ───────────────────────────────────────────────────────────── */
export const recommendSchema = [
  {
    '@context': 'https://schema.org',
    '@type': 'Service',
    '@id': `${absoluteUrl('/recommend')}#service`,
    name: 'DriveFetch AI Car Matchmaker',
    serviceType: 'AI-powered used car recommendation',
    url: absoluteUrl('/recommend'),
    description:
      "Tell us your budget, city, and lifestyle needs. DriveFetch's AI matchmaker analyzes Pakistani market specs, fuel economy, and resale value to fetch your top 3 cars.",
    provider: publisherRef,
    areaServed: { '@type': 'Country', name: 'Pakistan' },
    audience: {
      '@type': 'Audience',
      audienceType: 'Used car buyers in Pakistan',
    },
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'PKR',
    },
  },
  {
    '@context': 'https://schema.org',
    '@type': 'WebApplication',
    '@id': `${absoluteUrl('/recommend')}#webapp`,
    name: 'AI Car Matchmaker',
    url: absoluteUrl('/recommend'),
    applicationCategory: 'AutomotiveApplication',
    operatingSystem: 'Any (web browser)',
    isPartOf: { '@id': `${BASE}/#website` },
    publisher: publisherRef,
  },
];

/* ─────────────────────────────────────────────────────────────
   CALCULATORS  /calculators
   ───────────────────────────────────────────────────────────── */
export const calculatorsSchema = [
  {
    '@context': 'https://schema.org',
    '@type': 'WebApplication',
    '@id': `${absoluteUrl('/calculators')}#webapp`,
    name: 'Pakistan Car Tax, Transfer Fee & Fuel Cost Calculators',
    url: absoluteUrl('/calculators'),
    applicationCategory: 'FinanceApplication',
    applicationSubCategory: 'Vehicle tax and running-cost calculators',
    operatingSystem: 'Any (web browser)',
    inLanguage: 'en-PK',
    isPartOf: { '@id': `${BASE}/#website` },
    publisher: publisherRef,
    description:
      'Calculate exact annual token tax (ICT, Punjab, Sindh, KPK), FBR 231B vehicle transfer fees, and monthly fuel costs with latest 2026-2027 statutory rates.',
    featureList: [
      'Annual token tax calculator (Islamabad, Punjab, Sindh, Khyber Pakhtunkhwa)',
      'FBR Section 234 withholding tax with 10-year age exemption',
      'FBR Section 231B transfer advance tax with 10% annual depreciation',
      'Provincial MRA transfer fee, smart card and biometric charges',
      'Monthly fuel cost estimator by engine capacity and daily commute',
    ],
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'PKR',
    },
  },
];

/* ─────────────────────────────────────────────────────────────
   AI CHAT  /chat
   ───────────────────────────────────────────────────────────── */
export const chatSchema = [
  {
    '@context': 'https://schema.org',
    '@type': 'WebApplication',
    '@id': `${absoluteUrl('/chat')}#webapp`,
    name: 'DriveFetch AI — Pakistani Automotive Expert',
    url: absoluteUrl('/chat'),
    applicationCategory: 'AutomotiveApplication',
    operatingSystem: 'Any (web browser)',
    inLanguage: 'en-PK',
    isPartOf: { '@id': `${BASE}/#website` },
    publisher: publisherRef,
    description:
      'Chat with DriveFetch Expert for ustaad mechanic advice, real-world fuel averages, JDM auction sheet checks, and Pakistan Excise transfer policies.',
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'PKR',
    },
  },
];

/* ─────────────────────────────────────────────────────────────
   ABOUT  /about   — AboutPage + FAQPage
   FAQ entries are passed in from the page so the rendered accordion and the
   rich snippet can never drift apart. Google penalises FAQ markup that does
   not appear verbatim on the page.
   ───────────────────────────────────────────────────────────── */
export const buildAboutSchema = (faqs = []) => {
  const nodes = [
    {
      '@context': 'https://schema.org',
      '@type': 'AboutPage',
      '@id': `${absoluteUrl('/about')}#aboutpage`,
      name: 'About DriveFetch',
      url: absoluteUrl('/about'),
      description:
        'Learn how DriveFetch unifies the Pakistani used car market with multi-agent AI and real-time multi-platform scraping.',
      isPartOf: { '@id': `${BASE}/#website` },
      about: publisherRef,
    },
  ];

  if (faqs.length) {
    nodes.push({
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      '@id': `${absoluteUrl('/about')}#faq`,
      mainEntity: faqs.map(({ q, a }) => ({
        '@type': 'Question',
        name: q,
        acceptedAnswer: { '@type': 'Answer', text: a },
      })),
    });
  }

  return nodes;
};

/* ─────────────────────────────────────────────────────────────
   PRIVACY  /privacy
   ───────────────────────────────────────────────────────────── */
export const privacySchema = [
  {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    '@id': `${absoluteUrl('/privacy')}#webpage`,
    name: 'Privacy Policy',
    url: absoluteUrl('/privacy'),
    description:
      'How DriveFetch collects, uses and protects your data, including Google OAuth authentication and saved vehicle preferences.',
    isPartOf: { '@id': `${BASE}/#website` },
    publisher: publisherRef,
  },
];
