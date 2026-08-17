/**
 * src/components/SEO.jsx
 *
 * One place that emits every head tag a page needs: title, description,
 * keywords, robots, canonical, OpenGraph, Twitter card and JSON-LD.
 *
 * Every absolute URL is derived from siteConfig, so switching domains is a
 * single VITE_SITE_URL change rather than a grep across eight page files —
 * which is how the previous hardcoded canonicals would have gone stale.
 *
 * Usage:
 *   <SEO
 *     title="AI Car Matchmaker"          // becomes "… | DriveFetch"
 *     description="…"
 *     path="/recommend"
 *     schema={someJsonLdObject}          // object or array of objects
 *   />
 */
import React from 'react';
import { Helmet } from 'react-helmet-async';

import { siteConfig, absoluteUrl, assetUrl } from '../config/siteConfig';

const DEFAULT_TITLE =
  'DriveFetch — AI Car Matchmaker & Used Car Search Pakistan';

export default function SEO({
  title,
  description = siteConfig.description,
  path = '/',
  keywords,
  image,
  ogType = 'website',
  noindex = false,
  schema,
}) {
  const fullTitle = title ? `${title} | ${siteConfig.name}` : DEFAULT_TITLE;
  const canonical = absoluteUrl(path);
  const imageUrl = assetUrl(image || siteConfig.ogImage);

  const keywordList = keywords?.length
    ? [...new Set([...keywords, ...siteConfig.keywords])]
    : siteConfig.keywords;

  // Helmet cannot take an array child for the JSON-LD block, so normalise to a
  // list and emit one <script> per node.
  const schemaNodes = schema ? (Array.isArray(schema) ? schema : [schema]) : [];

  return (
    <Helmet prioritizeSeoTags>
      {/* ── Primary ── */}
      <html lang="en" />
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <meta name="keywords" content={keywordList.join(', ')} />
      <meta name="author" content={siteConfig.author} />
      <meta
        name="robots"
        content={noindex ? 'noindex, follow' : 'index, follow'}
      />
      <meta name="theme-color" content={siteConfig.themeColor} />

      {/* ── Canonical ── */}
      <link rel="canonical" href={canonical} />

      {/* ── OpenGraph (Facebook / LinkedIn / WhatsApp) ── */}
      <meta property="og:site_name" content={siteConfig.name} />
      <meta property="og:type" content={ogType} />
      <meta property="og:locale" content={siteConfig.locale} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={imageUrl} />
      <meta property="og:image:width" content={String(siteConfig.ogImageWidth)} />
      <meta property="og:image:height" content={String(siteConfig.ogImageHeight)} />
      <meta property="og:image:alt" content={siteConfig.ogImageAlt} />

      {/* ── Twitter ── */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:site" content={siteConfig.socials.twitter} />
      <meta name="twitter:creator" content={siteConfig.socials.twitter} />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:url" content={canonical} />
      <meta name="twitter:image" content={imageUrl} />
      <meta name="twitter:image:alt" content={siteConfig.ogImageAlt} />

      {/* ── Structured data ── */}
      {schemaNodes.map((node, i) => (
        <script type="application/ld+json" key={i}>
          {JSON.stringify(node)}
        </script>
      ))}
    </Helmet>
  );
}
