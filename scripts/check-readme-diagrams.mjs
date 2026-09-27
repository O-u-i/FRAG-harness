import { readFileSync } from 'node:fs';

const markdown = readFileSync('README.md', 'utf8');
const diagrams = [...markdown.matchAll(/```mermaid\s*\n([\s\S]*?)\n```/g)].map((match) => match[1]);
if (diagrams.length !== 1) throw new Error(`Expected one Finance Core Mermaid flowchart; found ${diagrams.length}.`);
for (const [index, diagram] of diagrams.entries()) {
  const lines = diagram.trim().split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!/^flowchart (LR|RL|TD|TB|BT)$/.test(lines.shift())) throw new Error(`Diagram ${index + 1}: invalid flowchart header.`);
  const nodes = new Set();
  for (const line of lines) {
    const edge = line.match(/^([A-Za-z][A-Za-z0-9_]*)(?:\[[^\[\]]+\]|\{[^{}]+\})?\s+(?:-->|--\s+[^<>\n]+?\s+-->|-->\|[^|]+\|)\s*([A-Za-z][A-Za-z0-9_]*)(?:\[[^\[\]]+\]|\{[^{}]+\})?$/);
    const declaration = line.match(/^([A-Za-z][A-Za-z0-9_]*)(?:\[([^\[\]]+)\]|\{([^{}]+)\})$/);
    if (edge) { nodes.add(edge[1]); nodes.add(edge[2]); }
    else if (declaration) nodes.add(declaration[1]);
    else throw new Error(`Diagram ${index + 1}: cannot parse ${line}`);
  }
  if (nodes.size < 3) throw new Error(`Diagram ${index + 1}: too few nodes.`);
}

const expectedSvg = [
  'docs/architecture/harness/dataflow.svg',
  'docs/architecture/harness/lifecycle.svg',
  'docs/architecture/rag-lab/dataflow.svg',
  'docs/architecture/rag-lab/lifecycle.svg',
];
const embeddedSvg = [...markdown.matchAll(/!\[[^\]]+\]\((docs\/architecture\/(?:harness|rag-lab)\/(?:dataflow|lifecycle)\.svg)\)/g)]
  .map((match) => match[1]);
if (embeddedSvg.length !== expectedSvg.length || new Set(embeddedSvg).size !== expectedSvg.length) {
  throw new Error(`Expected four distinct Archify SVG images in README; found ${embeddedSvg.length}.`);
}
for (const svgPath of expectedSvg) {
  if (!embeddedSvg.includes(svgPath)) throw new Error(`README does not embed ${svgPath}.`);
  const svg = readFileSync(svgPath, 'utf8');
  if (!svg.startsWith('<?xml version="1.0" encoding="UTF-8"?>') ||
      !/<svg\b[^>]*\bviewBox="[^"]+"/.test(svg) || !svg.includes('</svg>') ||
      /<script\b|javascript:/i.test(svg)) {
    throw new Error(`Invalid or unsafe Archify SVG: ${svgPath}.`);
  }
}
console.log('README diagram check passed: one Finance Core Mermaid flowchart and four Archify SVG images.');
