import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReviewMarkdown, ReviewAnswer } from './ReviewMarkdown';

describe('review model text', () => {
  it('renders headings, emphasis, lists, quotes, code and tables', () => {
    const html = renderToStaticMarkup(<ReviewMarkdown text={'# Finding\n\n**Supported** by `evidence`.\n\n- First\n- Second\n\n> Note\n\n```text\n<example>\n```\n\n| Item | Value |\n| --- | --- |\n| A | B |'} />);
    for (const part of ['<h2>Finding</h2>', '<strong>Supported</strong>', '<code>evidence</code>', '<li>First</li>', '<blockquote>', '&lt;example&gt;', '<th>Value</th>', '<td>B</td>']) expect(html).toContain(part);
  });
  it('escapes model HTML, rejects active links and never fetches images', () => {
    const html = renderToStaticMarkup(<ReviewMarkdown text={'<script>alert(1)</script>\n\n[Bad](javascript:alert) ![Remote image](https://example.invalid/a.png) [Source](https://example.invalid)'} />);
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('javascript:');
    expect(html).not.toContain('<img');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(renderToStaticMarkup(<ReviewMarkdown text={'>' .repeat(1000) + ' bounded'} />)).toContain('bounded');
  });
  it('keeps the answer visible and review details collapsed without removing gaps', () => {
    const html = renderToStaticMarkup(<ReviewAnswer answer={{ answer: '# Finding\nOne answer.', claims: [{ text: 'One answer.', evidenceIds: ['e-1'] }], disclaimer: 'Synthetic example.', missingInformation: ['Missing date'] }} />);
    expect(html).toContain('<h2>Finding</h2>');
    expect(html).toContain('<summary>Citation checks');
    expect(html).toContain('Notes · 1 gap');
    expect(html).toContain('Missing date');
    expect(html).not.toContain(' open=');
  });
});
