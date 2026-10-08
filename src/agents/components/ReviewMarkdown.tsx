import { Fragment, type ReactNode } from 'react';
import type { RunReport } from '../../../shared/contracts/runtime';

// Deliberately bounded Markdown for model text. React escapes raw HTML; images never fetch remote data.
function inline(text: string): ReactNode[] {
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|!?\[[^\]]*\]\([^\s)]+\))/g;
  return text.split(pattern).filter(Boolean).map((part, index) => {
    if (part.startsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>;
    if (/^(\*\*|__)/.test(part)) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (/^(\*|_)/.test(part)) return <em key={index}>{part.slice(1, -1)}</em>;
    const link = /^(!?)\[([^\]]*)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      if (link[1]) return <span key={index}>{link[2]}</span>;
      try {
        const url = new URL(link[3]);
        if (['https:', 'http:'].includes(url.protocol)) return <a key={index} href={url.href} target="_blank" rel="noopener noreferrer">{link[2]}</a>;
      } catch { /* Untrusted or relative destinations remain text. */ }
      return <span key={index}>{link[2]}</span>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export function ReviewMarkdown({ text, depth = 0 }: { text: string; depth?: number }) {
  if (depth >= 6) return <p>{inline(text)}</p>;
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const blocks: ReactNode[] = [];
  const special = (line: string) => /^(?:#{1,6}\s|```|~~~|>\s?|[-*+]\s|\d+[.)]\s|\s*$|(?:---+|\*\*\*+)\s*$)/.test(line);
  const cells = (line: string) => line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
  for (let i = 0; i < lines.length;) {
    const line = lines[i], key = i;
    if (!line.trim()) { i++; continue; }
    const fence = /^(\x60{3,}|~{3,})\s*(\S*)/.exec(line);
    if (fence) {
      const code: string[] = []; i++;
      while (i < lines.length && !lines[i].startsWith(fence[1])) code.push(lines[i++]);
      if (i < lines.length) i++;
      blocks.push(<pre key={key}><code>{code.join('\n')}</code></pre>); continue;
    }
    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (heading) {
      // Keep model headings below the page title.
      const Tag = `h${Math.min(heading[1].length + 1, 6)}` as 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
      blocks.push(<Tag key={key}>{inline(heading[2])}</Tag>); i++; continue;
    }
    if (/^(?:---+|\*\*\*+)\s*$/.test(line)) { blocks.push(<hr key={key} />); i++; continue; }
    if (line.startsWith('>')) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].startsWith('>')) quote.push(lines[i++].replace(/^>\s?/, ''));
      blocks.push(<blockquote key={key}><ReviewMarkdown text={quote.join('\n')} depth={depth + 1} /></blockquote>); continue;
    }
    const item = /^(?:([-*+])|(\d+)[.)])\s+(.+)/.exec(line);
    if (item) {
      const ordered = !!item[2], items: ReactNode[] = []; const start = Number(item[2]) || 1;
      while (i < lines.length) {
        const row = /^(?:([-*+])|(\d+)[.)])\s+(.+)/.exec(lines[i]);
        if (!row || !!row[2] !== ordered) break;
        items.push(<li key={i}>{inline(row[3])}</li>); i++;
      }
      blocks.push(ordered ? <ol key={key} start={start}>{items}</ol> : <ul key={key}>{items}</ul>); continue;
    }
    if (line.includes('|') && lines[i + 1] && cells(lines[i + 1]).every(cell => /^:?-{3,}:?$/.test(cell))) {
      const columns = cells(line); const rows: string[][] = []; i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push(<div className="review-table-scroll" key={key}><table><thead><tr>{columns.map((cell, c) => <th key={c}>{inline(cell)}</th>)}</tr></thead>
        <tbody>{rows.map((row, r) => <tr key={r}>{columns.map((_, c) => <td key={c}>{inline(row[c] ?? '')}</td>)}</tr>)}</tbody></table></div>); continue;
    }
    const paragraph = [line]; i++;
    while (i < lines.length && !special(lines[i])) paragraph.push(lines[i++]);
    blocks.push(<p key={key}>{inline(paragraph.join('\n'))}</p>);
  }
  return <div className="review-markdown">{blocks}</div>;
}

export function ReviewAnswer({ answer }: { answer: NonNullable<RunReport['modelOutput']> }) {
  return <div className="review-answer">
    <ReviewMarkdown text={answer.answer} />
    <details className="review-annotation"><summary>Citation checks · {answer.claims.length} {answer.claims.length === 1 ? 'claim' : 'claims'}</summary>
      {answer.claims.map((claim, index) => <div key={index}><ReviewMarkdown text={claim.text} />
        <small className="review-citations">{claim.evidenceIds.join(' · ')}</small></div>)}
    </details>
    <details className="review-annotation"><summary>Notes{answer.missingInformation.length ? ` · ${answer.missingInformation.length} ${answer.missingInformation.length === 1 ? 'gap' : 'gaps'}` : ''}</summary>
      <ReviewMarkdown text={answer.disclaimer} />
      {!!answer.missingInformation.length && <ul>{answer.missingInformation.map((item, index) => <li key={index}>{inline(item)}</li>)}</ul>}
    </details>
  </div>;
}
