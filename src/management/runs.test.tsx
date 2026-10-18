import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RunSummary, RunDetails, formatLocalTime, recentEvidenceRuns, type Run } from './runs';

const search:Run = {id:'new-search',tool:'frag_search',status:'completed',createdAt:'2026-10-09T12:00:00Z',sourceId:'management',input:{query:'planning < organizing'}};
test('Run summary identifies the exact search and uses local time without losing its UTC timestamp',()=>{
  const html = renderToStaticMarkup(<RunSummary run={search} runs={[search]}/>);
  expect(html).toContain('Source: <code>management</code>');
  expect(html).toContain('Query: planning &lt; organizing');
  expect(html).toContain('Run: <code>new-search</code>');
  expect(html).toContain('dateTime="2026-10-09T12:00:00Z"');
  expect(html).toContain(formatLocalTime(search.createdAt));
  expect(formatLocalTime(search.createdAt)).not.toBe(search.createdAt);
});

test('Run details show readable sections and keep full audit JSON separately collapsed',()=>{
  const run:Run = {...search,sourceRevision:2,outputTokens:120,sourceBindings:[{}],pack:{
    query:'planning',evidence:[{evidenceId:'e1',locatorId:'section-1',locatorLabel:'Planning',relativePath:'notes.md',text:'evidence <script> text',windowed:true}],
    memoryBackground:[{memoryId:'m1',version:4,contentVersion:2,text:'Reviewed background',general:false}],warnings:['Untrusted source content'],budget:{maxBytes:16384,omittedEvidenceIds:['e2']},
  }};
  const html = renderToStaticMarkup(<RunDetails run={run}/>);
  for(const label of ['Summary','Evidence','Memory','Warnings','1 evidence snippet from 1 file','Tool result tokens: 120','Omitted snippets: 1','v2 · Revision 4','Windowed excerpt']) expect(html).toContain(label);
  expect(html).toContain('evidence &lt;script&gt; text');
  expect(html).toContain('<details class="advanced"><summary>Advanced · complete audit JSON</summary>');
  expect(html).not.toContain('<details open');
  expect(html).toContain('&quot;sourceBindings&quot;');
  expect(html).toContain('does not confirm native model consumption');
  const failed = renderToStaticMarkup(<RunDetails run={{...search,status:'failed',errorCode:'INDEX_STALE',pack:null}}/>);
  expect(failed).toContain('INDEX_STALE'); expect(failed).toContain('No evidence text'); expect(failed).toContain('No Memory included');
});

test('recent Memory Run choices contain only the latest four completed evidence Runs',()=>{
  const valid = Array.from({length:7},(_,index):Run=>({...search,id:`valid-${index}`,sourceBindings:[{}],pack:{evidence:[{evidenceId:`e${index}`,locatorId:'s',text:'Evidence'}]}}));
  const runs = [{...valid[0],id:'failed',status:'failed'}, {...valid[0],id:'prepared',status:'prepared'}, {...valid[0],id:'discovery',pack:{discovery:{}}}, {...valid[0],id:'empty-bindings',sourceBindings:[]}, ...valid];
  expect(recentEvidenceRuns(runs).map(run=>run.id)).toEqual(['valid-0','valid-1','valid-2','valid-3']);
});
test('Read uses its parent search query, never an unrelated latest search',()=>{
  const read:Run = {...search,id:'new-read',tool:'frag_read',input:{searchRunId:search.id}};
  const other:Run = {...search,id:'different-search',input:{query:'unrelated'}};
  expect(renderToStaticMarkup(<RunSummary run={read} runs={[other,read,search]}/>)).toContain('Query: planning &lt; organizing');
  const withoutParent = renderToStaticMarkup(<RunSummary run={read} runs={[other,read]}/>);
  expect(withoutParent).toContain('Search Run: new-search');
  expect(withoutParent).not.toContain('unrelated');
  expect(formatLocalTime('not-a-timestamp')).toBe('not-a-timestamp');
});
test('the finalized redacted query remains visible when the parent is outside the latest-200 list',()=>{
  const read:Run = {...search,id:'packed-read',tool:'frag_read',input:{searchRunId:'older-search'},pack:{query:'approved redacted query'}};
  expect(renderToStaticMarkup(<RunSummary run={read} runs={[read]}/>)).toContain('Query: approved redacted query');
  const html = renderToStaticMarkup(<RunSummary run={{...search,pack:{query:'redacted'}}} runs={[search]}/>);
  expect(html).toContain('Query: redacted');
  expect(html).not.toContain('planning');
});

test('plan confirmation is a human action on a completed local Search document, never inferred from an excerpt',()=>{
  const run:Run = {...search,pack:{evidence:[{evidenceId:'plan',locatorId:'s',relativePath:'plan.md',text:'A search excerpt'}]}};
  const html = renderToStaticMarkup(<RunDetails run={run} onConfirmPlan={()=>{}}/>);
  expect(html).toContain('Confirm entire document as a plan');
  expect(html).toContain('reviewing the complete file');
  for (const value of [{...run,status:'prepared'}, {...run,tool:'frag_read'}, {...run,pack:{evidence:[{evidenceId:'not-plan',locatorId:'s',text:'FC report'}]}}]) {
    expect(renderToStaticMarkup(<RunDetails run={value} onConfirmPlan={()=>{}}/>)).not.toContain('Confirm entire document as a plan');
  }
  expect(renderToStaticMarkup(<RunDetails run={run}/>)).not.toContain('Confirm entire document as a plan');
});
