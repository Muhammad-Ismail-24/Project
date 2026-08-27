with open('src/components/CarResultCard.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix React unused
content = content.replace("import React, { useState, useEffect, useRef } from 'react';", "import { useState, useEffect, useRef } from 'react';")

# Fix SaveCarButton missing types
content = content.replace("import SaveCarButton from './SaveCarButton';", "// @ts-ignore\nimport SaveCarButton from './SaveCarButton';")

# Fix Tag[]
content = content.replace("const tags = [];", "const tags: Tag[] = [];")
content = content.replace("tags.push({ text: 'Danger: Showered', type: 'danger' });", "tags.push({ text: 'Danger: Showered', type: 'danger' as const });")
content = content.replace("tags.push({ text: 'Warning: Touchups', type: 'warning' });", "tags.push({ text: 'Warning: Touchups', type: 'warning' as const });")
content = content.replace("tags.push({ text: 'Warning: Painted', type: 'warning' });", "tags.push({ text: 'Warning: Painted', type: 'warning' as const });")
content = content.replace("tags.push({ text: 'High Liquidity: Genuine', type: 'positive' });", "tags.push({ text: 'High Liquidity: Genuine', type: 'positive' as const });")
content = content.replace("tags.push({ text: 'Positive: Non-Accidental', type: 'positive' });", "tags.push({ text: 'Positive: Non-Accidental', type: 'positive' as const });")

# Fix useRef and useState
content = content.replace("const abortControllerRef = useRef(null);", "const abortControllerRef = useRef<AbortController | null>(null);")
content = content.replace("const [aiData, setAiData] = useState(null);", "const [aiData, setAiData] = useState<any>(null);")
content = content.replace("const [evalError, setEvalError] = useState(null);", "const [evalError, setEvalError] = useState<string | null>(null);")

# Fix unused liquidityBadge
content = content.replace("const liquidityBadge =", "// const liquidityBadge =")

# Fix image e.target
content = content.replace("e.target.onerror = null;", "(e.target as HTMLImageElement).onerror = null;")
content = content.replace("e.target.style.display = 'none';", "(e.target as HTMLImageElement).style.display = 'none';")
content = content.replace("if (e.target.nextElementSibling) e.target.nextElementSibling.style.display = 'flex';", "if ((e.target as HTMLImageElement).nextElementSibling) ((e.target as HTMLImageElement).nextElementSibling as HTMLElement).style.display = 'flex';")

# Fix map params
content = content.replace("redFlags.map((flag, idx) => (", "redFlags.map((flag: string, idx: number) => (")

with open('src/components/CarResultCard.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
