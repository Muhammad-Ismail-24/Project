/**
 * seo.selftest.mjs
 *
 * Renders every route's <SEO /> through react-helmet-async server-side and
 * asserts the head tags it emits: title, canonical, robots, OpenGraph, Twitter
 * and JSON-LD.
 *
 * SSR rather than a browser check because the pages mount a Three.js
 * DynamicBackground that exhausts the headless sandbox. The head output is
 * identical either way — Helmet builds the same tag set on both sides.
 *
 * Run:  npx vite build --ssr src/config/seo.selftest.mjs --outDir .seotest \
 *         && node .seotest/seo.selftest.js
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { HelmetProvider, HelmetData } from 'react-helmet-async';

import SEO from '../components/SEO.jsx';
import { siteConfig, absoluteUrl } from './siteConfig.js';
import {
  homeSchema,
  recommendSchema,
  calculatorsSchema,
  chatSchema,
  buildAboutSchema,
  privacySchema,
} from './seoSchemas.js';

let passed = 0;
let failed = 0;

const check = (label, cond, detail = '') => {
  if (cond) {
    passed++;
    console.log(`  PASS  ${label}${detail ? ` - ${detail}` : ''}`);
  } else {
    failed++;
    console.log(`  FAIL  ${label}${detail ? ` - ${detail}` : ''}`);
  }
};

/**
 * Renders <SEO {...props}/> and returns the emitted head markup.
 *
 * React 19 hoists <title>/<meta>/<link>/<script> into the document head
 * natively, so the tags land directly in the rendered string rather than in
 * react-helmet-async's SSR context (which stays empty under React 19). We
 * therefore assert against the markup — that is what actually reaches the DOM.
 */
function renderHead(props) {
  const helmetData = new HelmetData({});
  const markup = renderToStaticMarkup(
    React.createElement(
      HelmetProvider,
      { context: helmetData.context },
      React.createElement(SEO, props)
    )
  );
  // Same string for every bucket; the assertions below each look for their
  // own tag type within it.
  return { title: markup, meta: markup, link: markup, script: markup, raw: markup };
}

/**
 * Titles containing "&" are correctly emitted as "&amp;" in HTML, so expected
 * strings must be escaped the same way before comparison.
 */
const esc = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const FAQS = [
  { q: 'How does DriveFetch calculate fair market value?', a: 'Cross-references live listings.' },
  { q: 'Is DriveFetch free to use?', a: 'Yes.' },
];

// The exact props each page passes.
const ROUTES = [
  { name: 'Home', props: { path: '/', schema: homeSchema }, expectTitle: 'DriveFetch — AI Car Matchmaker & Used Car Search Pakistan' },
  { name: 'Recommend', props: { title: 'AI Car Matchmaker | Find Your Ideal Car in Pakistan', path: '/recommend', schema: recommendSchema } },
  { name: 'Calculators', props: { title: 'Car Tax, Transfer Fee & Fuel Cost Calculators Pakistan (FY 2026-27)', path: '/calculators', schema: calculatorsSchema } },
  { name: 'Chat', props: { title: 'Ask DriveFetch AI | 24/7 Pakistani Automotive Expert & Valuation', path: '/chat', schema: chatSchema } },
  { name: 'About', props: { title: 'About DriveFetch | Intelligent Car Discovery in Pakistan', path: '/about', schema: buildAboutSchema(FAQS) } },
  { name: 'Privacy', props: { title: 'Privacy Policy', path: '/privacy', schema: privacySchema } },
  { name: 'Saved', props: { title: 'Saved Vehicles', path: '/saved', noindex: true } },
  { name: '404', props: { title: '404 // Route Not Found', path: '/404', noindex: true } },
];

console.log(`\nSITE_URL in effect: ${siteConfig.url}\n`);

console.log('[1] Per-route head tags');
for (const { name, props, expectTitle } of ROUTES) {
  const head = renderHead(props);
  const canonical = absoluteUrl(props.path);
  const ok =
    head.title.includes('<title') &&
    head.link.includes(`rel="canonical" href="${canonical}"`) &&
    head.meta.includes(`property="og:url" content="${canonical}"`) &&
    head.meta.includes('property="og:title"') &&
    head.meta.includes('name="twitter:card" content="summary_large_image"') &&
    head.meta.includes('name="description"');
  check(`${name.padEnd(12)} emits title + canonical + OG + Twitter`, ok, canonical);

  if (expectTitle) {
    check(`${name.padEnd(12)} default title is the brand string`,
      head.title.includes(esc(expectTitle)), expectTitle.slice(0, 46) + '…');
  }
  if (props.title) {
    check(`${name.padEnd(12)} title suffixed with "| DriveFetch"`,
      head.title.includes(esc(`${props.title} | DriveFetch`)));
  }

  const wantRobots = props.noindex ? 'noindex, follow' : 'index, follow';
  check(`${name.padEnd(12)} robots = ${wantRobots}`,
    head.meta.includes(`name="robots" content="${wantRobots}"`));

  if (props.schema) {
    const count = (head.script.match(/application\/ld\+json/g) || []).length;
    const expected = Array.isArray(props.schema) ? props.schema.length : 1;
    check(`${name.padEnd(12)} emits ${expected} JSON-LD block(s)`, count === expected, `got ${count}`);
  }
}

console.log('\n[2] JSON-LD validity');
const allSchemas = {
  home: homeSchema,
  recommend: recommendSchema,
  calculators: calculatorsSchema,
  chat: chatSchema,
  about: buildAboutSchema(FAQS),
  privacy: privacySchema,
};
for (const [name, nodes] of Object.entries(allSchemas)) {
  const list = Array.isArray(nodes) ? nodes : [nodes];
  const allValid = list.every((n) => n['@context'] === 'https://schema.org' && n['@type']);
  check(`${name.padEnd(12)} every node has @context + @type`, allValid,
    list.map((n) => n['@type']).join(', '));
  // Must survive JSON.stringify — a circular ref or undefined would break the tag.
  let serialises = true;
  try { JSON.stringify(list); } catch { serialises = false; }
  check(`${name.padEnd(12)} serialises cleanly`, serialises);
  // No absolute URL may point anywhere but the configured domain.
  const blob = JSON.stringify(list);
  const foreign = (blob.match(/https?:\/\/[^"]+/g) || [])
    .filter((u) => !u.startsWith(siteConfig.url) && !u.startsWith('https://schema.org'));
  check(`${name.padEnd(12)} no foreign absolute URLs`, foreign.length === 0, foreign.join(' ') || 'clean');
}

console.log('\n[3] Home schema completeness (branded search)');
const website = homeSchema.find((n) => n['@type'] === 'WebSite');
const org = homeSchema.find((n) => n['@type'] === 'Organization');
const app = homeSchema.find((n) => n['@type'] === 'WebApplication');
check('WebSite node present', !!website);
check('WebSite has SearchAction', website?.potentialAction?.['@type'] === 'SearchAction');
check('Organization name is DriveFetch', org?.name === 'DriveFetch');
check('Organization alternateName is "Drive Fetch"', org?.alternateName === 'Drive Fetch');
check('WebApplication categorised as automotive',
  app?.applicationCategory === 'AutomotiveApplication');
check('Organization @id is shared and stable',
  org?.['@id'] === `${siteConfig.url}/#organization`);

console.log('\n[4] FAQ schema mirrors the rendered accordion');
const faqNode = buildAboutSchema(FAQS).find((n) => n['@type'] === 'FAQPage');
check('FAQPage node built', !!faqNode);
check('one Question per rendered FAQ', faqNode?.mainEntity?.length === FAQS.length,
  `${faqNode?.mainEntity?.length} of ${FAQS.length}`);
check('question text matches verbatim',
  faqNode?.mainEntity?.[0]?.name === FAQS[0].q);
check('answer text matches verbatim',
  faqNode?.mainEntity?.[0]?.acceptedAnswer?.text === FAQS[0].a);

console.log('\n[5] Domain-agnostic wiring');
check('siteConfig.url has no trailing slash', !siteConfig.url.endsWith('/'), siteConfig.url);
check('absoluteUrl("/") ends in a single slash', absoluteUrl('/') === `${siteConfig.url}/`);
check('absoluteUrl("/about") has no double slash', absoluteUrl('/about') === `${siteConfig.url}/about`);
check('ogImage points at a file that exists (.jpg not .png)',
  siteConfig.ogImage === '/og-image.jpg', siteConfig.ogImage);

const homeHead = renderHead({ path: '/', schema: homeSchema });
const urlCount = (homeHead.meta.match(new RegExp(siteConfig.url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
check('every absolute URL in head uses siteConfig.url', urlCount >= 4, `${urlCount} occurrences`);

console.log(`\n${'='.repeat(64)}`);
console.log(`  ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(64)}\n`);
process.exit(failed ? 1 : 0);
