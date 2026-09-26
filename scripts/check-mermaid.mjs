import { readFileSync } from 'node:fs';

const markdown = readFileSync('README.md', 'utf8');
const diagrams = [...markdown.matchAll(/```mermaid\s*\n([\s\S]*?)\n```/g)].map((match) => match[1]);
if (diagrams.length !== 3) throw new Error(`Expected three Mermaid flowcharts; found ${diagrams.length}.`);
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
console.log(`Mermaid flowchart parse passed: ${diagrams.length} README diagrams.`);
