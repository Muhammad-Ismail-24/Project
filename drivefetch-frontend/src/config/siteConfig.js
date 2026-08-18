/**
 * src/config/siteConfig.js
 *
 * Single source of truth for every absolute URL the site emits — canonicals,
 * OpenGraph, Twitter cards and JSON-LD.
 *
 * DOMAIN SWITCHING
 * ----------------
 * Nothing anywhere else should hardcode the domain. To move to a custom
 * domain, set one variable and rebuild:
 *
 *     VITE_SITE_URL=https://drivefetch.pk
 *
 * That covers the React app. The two static crawl files (robots.txt and
 * sitemap.xml) cannot read import.meta.env because they are served as plain
 * files, so they are regenerated from the same variable by the `prebuild`
 * script — see scripts/generate-seo-assets.mjs. Both paths read VITE_SITE_URL,
 * so the switch stays a one-line change with no split-brain domain.
 */

/**
 * Strips any trailing slash so `${url}${path}` never produces a double slash.
 * A canonical of "https://x.com//about" is a different URL to a crawler.
 */
const normaliseUrl = (raw) => (raw || '').trim().replace(/\/+$/, '');

export const siteConfig = {
  name: 'DriveFetch',
  alternateName: 'Drive Fetch',
  legalName: 'DriveFetch Pakistan',

  url: normaliseUrl(import.meta.env.VITE_SITE_URL) || 'https://drivefetch.vercel.app',

  // NOTE: the asset in /public is og-image.jpg, not .png. Referencing a
  // non-existent .png would silently break every social preview — the crawler
  // 404s the image and falls back to no card at all.
  ogImage: '/og-image.jpg',
  ogImageWidth: 1200,
  ogImageHeight: 630,
  ogImageAlt: 'DriveFetch — AI used car matchmaker and search engine for Pakistan',

  themeColor: '#E5202E',
  locale: 'en_PK',
  author: 'DriveFetch',

  description:
    'AI-driven used car matchmaker and search engine for Pakistan. Aggregating verified listings from PakWheels, OLX, and Gari.pk with instant valuation, tax, and fuel calculators.',

  keywords: [
    'DriveFetch',
    'Drive Fetch',
    'DriveFetch Pakistan',
    'AI Car Matchmaker',
    'Used Cars Pakistan',
    'PakWheels Alternative',
    'Car Token Tax Calculator Pakistan',
    'Car Transfer Fee Calculator 2026',
    'Used Car Search Islamabad Lahore Karachi',
  ],

  socials: {
    twitter: '@DriveFetch',
  },
};

/** Absolute URL for a route path. `absoluteUrl('/about')` -> 'https://…/about' */
export const absoluteUrl = (path = '/') => {
  if (!path || path === '/') return `${siteConfig.url}/`;
  return `${siteConfig.url}${path.startsWith('/') ? path : `/${path}`}`;
};

/** Absolute URL for an asset in /public. */
export const assetUrl = (path) =>
  `${siteConfig.url}${path.startsWith('/') ? path : `/${path}`}`;

/**
 * Organization / Brand node, reused by several page schemas via @id so the
 * knowledge graph resolves to one entity rather than several duplicates.
 */
export const organizationSchema = {
  '@type': 'Organization',
  '@id': `${siteConfig.url}/#organization`,
  name: siteConfig.name,
  alternateName: siteConfig.alternateName,
  legalName: siteConfig.legalName,
  url: `${siteConfig.url}/`,
  logo: {
    '@type': 'ImageObject',
    url: assetUrl('/favicon.svg'),
  },
  image: assetUrl(siteConfig.ogImage),
  description: siteConfig.description,
  areaServed: {
    '@type': 'Country',
    name: 'Pakistan',
  },
};
