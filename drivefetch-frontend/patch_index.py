import os

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# We will replace the block from <title> to the end of <head> with the new static tags,
# while preserving the json-ld and other necessary tags, but wait, it's easier to just
# manually replace the specific lines.
# Actually, replacing the exact strings is safer.

replacements = {
    '<title>DriveFetch — AI Car Matchmaker & Used Car Search Pakistan</title>': '<title>DriveFetch — AI-Powered Used Car Search in Pakistan</title>',
    '<meta name="description" content="AI-driven used car matchmaker and search engine for Pakistan. Aggregating verified listings from PakWheels, OLX, and Gari.pk with instant valuation, tax, and fuel calculators." />': '<meta name="description" content="Find your perfect used car in Pakistan with AI-powered matching. Search thousands of listings by budget, family size, and fuel preference.">',
    '<meta property="og:title" content="DriveFetch — AI Car Matchmaker & Used Car Search Pakistan" />': '<meta property="og:title" content="DriveFetch — AI Car Matchmaker Pakistan">',
    '<meta property="og:description" content="AI-driven used car matchmaker and search engine for Pakistan. Aggregating verified listings from PakWheels, OLX, and Gari.pk with instant valuation, tax, and fuel calculators." />': '<meta property="og:description" content="AI-powered used car search for Pakistan.">',
    'https://drivefetch.vercel.app/og-image.jpg': 'https://drivefetch.vercel.app/og-preview.jpg'
}

for old, new in replacements.items():
    content = content.replace(old, new)
    content = content.replace(old.replace('—', '?"'), new) # Handle encoding issues just in case

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
