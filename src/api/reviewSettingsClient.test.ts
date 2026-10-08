import { afterEach, describe, expect, it, vi } from 'vitest';
import { applicationSettingsSchema, conversationSettingsSchema, evidenceSettingsSchema } from '../../shared/contracts/reviewSettings';
import { settingsFixture } from '../agents/testSettingsFixture';
import { fetchReviewSettings, prepareFromSettings, saveApplicationSettings, saveConversationSettings, saveProjectSettings } from './reviewSettingsClient';
import type { AgentView } from '../../shared/contracts/agents';
afterEach(() => vi.unstubAllGlobals());
const view: AgentView = {session:{sessionId:'a'.repeat(32),resource:'frag:/synthetic',version:3,
  turns:[{id:'synthetic-turn',text:'Synthetic task',state:'running',createdAt:'now',runId:null}]},report:null,preview:null};
describe('Review settings controls', () => {
  it('separates application, project and conversation writes from preparation and execution', async () => {
    const fetchMock=vi.fn().mockImplementation(async () => Response.json(settingsFixture)); vi.stubGlobal('fetch',fetchMock);
    expect(await fetchReviewSettings(view.session.sessionId)).toEqual(settingsFixture);
    await saveApplicationSettings(0,settingsFixture.application.settings);
    await saveProjectSettings(0,settingsFixture.project.settings);
    await saveConversationSettings(view,0,null);
    expect(fetchMock.mock.calls.map(([url])=>url)).toEqual([
      `/api/agents/sessions/${view.session.sessionId}/settings`, '/api/agents/settings/application','/api/agents/settings/project',
      `/api/agents/sessions/${view.session.sessionId}/settings`]);
    expect(fetchMock.mock.calls.slice(1).every(([,options])=>options.method==='PUT')).toBe(true);
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({version:3,turnId:'synthetic-turn',revision:0,settings:null});
  });
  it('binds all displayed revisions and does not carry an approval or chat history', async () => {
    const fetchMock=vi.fn().mockResolvedValue(Response.json(view));vi.stubGlobal('fetch',fetchMock);
    await prepareFromSettings(view,settingsFixture,null,{templateId:'evidence-review-v1',checklist:[]},[]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({version:3,turnId:'synthetic-turn',applicationRevision:0,
      projectRevision:0,conversationRevision:0,override:null,task:{templateId:'evidence-review-v1',checklist:[]},selectedMemory:[]});
    expect(fetchMock.mock.calls[0][0]).toContain('/prepare-settings');
  });
  it('rejects ambiguous sources, unsafe paths, coercion and duplicate template ids', () => {
    const evidence=settingsFixture.project.settings;
    for(const relativePath of ['../private.md','C:\\private.md','\\private.md','/private.md']) expect(evidenceSettingsSchema.safeParse({...evidence,
      file:{relativePath,locatorIds:['section'],relevanceReason:'Selected scope'}}).success).toBe(false);
    expect(evidenceSettingsSchema.safeParse({...evidence,synthetic:true}).success).toBe(false);
    expect(applicationSettingsSchema.safeParse({...settingsFixture.application.settings,topK:'3'}).success).toBe(false);
    const item={id:'same',text:'Review scope',blocking:true};
    expect(applicationSettingsSchema.safeParse({...settingsFixture.application.settings,checklist:[item,item]}).success).toBe(false);
    expect(conversationSettingsSchema.safeParse({evidence:{mode:'plugin',file:null,synthetic:false,plugin:null},topK:3,research:true,checklist:[]}).success).toBe(false);
  });
});
