import { useRef, useState } from 'react';
import type { ResearchPreview } from '../../../shared/contracts/research';
import type { RunReport } from '../../../shared/contracts/runtime';
import { parseResearchSelection, type ResearchKind } from '../../api/researchClient';
import { PreparedCallPreview } from '../../components/common/PreparedCallPreview';
import type { MemorySelection } from '../../../shared/contracts/memory';
import { MemoryPicker } from '../memory/MemoryPicker';

export type ResearchContinuation = { runId: string; kind: ResearchKind; preview: ResearchPreview; sourceRequest: unknown };
type Props = {
  report?: RunReport; busy: boolean; continuation?: ResearchContinuation; onInvalidate: () => void;
  onPrepare: (kind: ResearchKind, input: unknown, runId?: string) => Promise<ResearchPreview>;
  onDispatch: (preview: ResearchPreview, input: unknown) => Promise<void>;
};
export function matchingResearchContinuation(report: RunReport | undefined, continuation: ResearchContinuation | undefined) {
  return report?.research && continuation?.runId === report.run.id && continuation.preview.runId === report.run.id
    && continuation.preview.sessionId === report.run.sessionId && continuation.kind === report.run.kind ? continuation : undefined;
}
function memoryInput(kind: ResearchKind, text: string) {
  try { return parseResearchSelection(kind, JSON.parse(text) as unknown); }
  catch { return undefined; }
}
function sourceKey(input: ReturnType<typeof memoryInput>) {
  return input ? JSON.stringify('goal' in input ? {
    fileSelections: input.fileSelections.map(({ relativePath, locatorIds }) => ({ relativePath, locatorIds })),
    pluginSelection: input.pluginSelection ?? null,
  }
    : { datasetId: input.datasetId, query: input.query, topK: input.topK }) : undefined;
}

export function ResearchPanel({ report, busy, continuation, onInvalidate, onPrepare, onDispatch }: Props) {
  const carried = matchingResearchContinuation(report, continuation);
  const [kind, setKind] = useState<ResearchKind>(report?.run.kind ?? 'harness');
  const [sourceText, setSourceText] = useState(carried ? JSON.stringify(carried.sourceRequest, null, 2)
    : report ? JSON.stringify(report.selection.input, null, 2) : '');
  const [prepared, setPrepared] = useState<ResearchPreview | undefined>(carried?.preview);
  const [sourceRequest, setSourceRequest] = useState<unknown>(carried?.sourceRequest);
  const [inputError, setInputError] = useState('');
  const inputEpoch = useRef(0);
  const existing = Boolean(report?.research);
  const parsedInput = memoryInput(kind, sourceText);
  const selectedMemory = parsedInput?.selectedMemory ?? [];
  const savedInput = report ? memoryInput(report.run.kind, JSON.stringify(report.selection.input)) : undefined;
  const memoryChanged = existing && JSON.stringify(selectedMemory) !== JSON.stringify(savedInput?.selectedMemory ?? []);
  const recommendRunId = report && sourceKey(parsedInput) === sourceKey(savedInput) ? report.run.id : undefined;
  const cannotContinue = existing && (['accepted', 'rejected', 'error', 'outcome_unknown'].includes(report!.run.status)
    || ['error', 'exhausted', 'outcome_unknown'].includes(report!.research!.status) || Boolean(report!.modelOutput));
  const invalidate = () => { inputEpoch.current += 1; setPrepared(undefined); setSourceRequest(undefined); setInputError(''); onInvalidate(); };
  const confirmMemory = (items: MemorySelection[]) => {
    if (parsedInput) setSourceText(JSON.stringify({ ...parsedInput, selectedMemory: items }, null, 2));
    invalidate();
  };
  const editSource = (text: string) => {
    const next = memoryInput(kind, text);
    if (next && JSON.stringify({ ...next, selectedMemory: undefined }) !== JSON.stringify({ ...parsedInput, selectedMemory: undefined })) {
      setSourceText(JSON.stringify({ ...next, selectedMemory: [] }, null, 2));
    } else setSourceText(text);
    invalidate();
  };
  const prepare = async (linked = false) => {
    invalidate();
    const epoch = inputEpoch.current;
    let input: unknown;
    try { input = parseResearchSelection(kind, JSON.parse(sourceText) as unknown); }
    catch { setInputError('Enter valid, explicitly selected KB request JSON for the chosen source kind.'); return; }
    if (report && (linked || !existing)) input = { ...(input as object), sessionId: report.run.sessionId, parentRunId: report.run.id };
    try {
      const value = await onPrepare(kind, input, existing && !linked ? report?.run.id : undefined);
      if (inputEpoch.current === epoch) { setSourceRequest(input); setPrepared(value); }
    } catch { /* The parent displays the sanitized error and refreshes history. */ }
  };
  const dispatch = async () => {
    if (!prepared?.canApprove || !prepared.approvalToken || busy) return;
    if (!window.confirm(`Approve only this ${prepared.stage} request to ${prepared.preparedCall.endpoint}?\nFingerprint: ${prepared.fingerprint}`)) return;
    const call = prepared;
    setPrepared(undefined); onInvalidate();
    try { await onDispatch(call, sourceRequest); }
    catch { /* Unknown and failed outcomes are never automatically resent. */ }
  };
  return <section className="card research-panel"><div className="section-heading"><span className="eyebrow">Optional KB evidence loop</span>
    <h2>{existing ? 'Continue Research' : 'Start Research'}</h2>
    <p>Research gathers evidence before Context and Inference. Each model request requires its own preview and approval.</p></div>
    <p className="muted">At most 3 model turns and 6 serial tools. The first request contains a source manifest; tools read only your selected scope.</p>
    {!existing && <label className="field">Research source kind<select value={kind} disabled={busy}
      onChange={(event) => { setKind(event.target.value as ResearchKind); setSourceText(''); invalidate(); }}>
      <option value="harness">Selected local files</option><option value="rag">Selected synthetic RAG query</option>
    </select></label>}
    <label className="field">Research source selection JSON<textarea className="runtime-selection" value={sourceText} disabled={busy} spellCheck={false}
      placeholder="Paste the explicit Harness or RAG Lab source selection request."
      onChange={(event) => editSource(event.target.value)} /></label>
    <p className="muted">Keep the original selection for a saved Research run. Changed inputs require a new run. Finance Core stays on the fixed workflow.</p>
    {cannotContinue && <p className="alert">This Research checkpoint cannot continue. Review the saved outcome; no external call will be resent.</p>}
    {inputError && <p className="alert" role="alert">{inputError}</p>}
    <MemoryPicker runId={recommendRunId} query={parsedInput ? ('goal' in parsedInput ? parsedInput.goal : parsedInput.query) : ''}
      selected={selectedMemory} disabled={busy || !parsedInput} onChange={confirmMemory} />
    {memoryChanged && <p className="notice">Memory selection changed. Prepare a linked Research run to preserve the original request and trajectory.</p>}
    <div className="rag-actions"><button className="button" type="button" disabled={busy || cannotContinue || memoryChanged || !sourceText.trim()} onClick={() => void prepare()}>
      {existing ? 'Preview next Research stage' : 'Preview initial Research request'}</button>
      {existing && <button className="button" type="button" disabled={busy || !sourceText.trim()} onClick={() => void prepare(true)}>Preview linked Research run</button>}
    </div>
    {existing && <p className="muted">A linked run preserves this original run and uses a new preview. Reconcile unknown external outcomes before starting it.</p>}
    {prepared && <div className="runtime-recovered"><h3>{prepared.stage === 'research' ? `Research turn ${prepared.turn} / ${prepared.maxTurns}`
      : `${prepared.stage === 'context' ? 'Context' : 'Inference'} preview`}</h3>
      <p className="muted">Run: {prepared.runId} · Fresh approval · <code>{prepared.fingerprint}</code></p>
      {prepared.warnings.map((warning, index) => <p className="notice" key={index}>{warning}</p>)}
      <PreparedCallPreview call={prepared.preparedCall} />
      {!prepared.canApprove && <p className="alert">This request cannot be approved. Resolve the displayed limits or blocking review items.</p>}
      <button className="button primary" type="button" disabled={busy || !prepared.canApprove || !prepared.approvalToken}
        onClick={() => void dispatch()}>Approve displayed {prepared.stage === 'research' ? 'Research' : prepared.stage === 'context' ? 'Context' : 'Inference'} request</button>
    </div>}
  </section>;
}
