import {expect,test,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
vi.mock('./client',()=>({request:vi.fn()}));
import {AcceptancePanel,acceptancePrompt} from './acceptance';
test('acceptance guide never claims approval or exposes a production advice launch',()=>{
  const html=renderToStaticMarkup(<AcceptancePanel open onToggle={()=>{}} onUseSource={()=>{}}/>);
  for(const text of ['Synthetic only','No automatic pass','Prepare virtual files','Choose location','human confirmation','official FC economic report'])expect(html).toContain(text);
  expect(acceptancePrompt).toContain('requireCompletePlan=true');expect(acceptancePrompt).toContain('Do not read FC');
  expect(html).not.toContain('Run recommendations');
  expect(html).not.toMatch(/<summary>Native Chat prompt[\s\S]*?<button[\s\S]*?<\/summary>/);
  expect(html).toContain('Copy acceptance prompt');
});
