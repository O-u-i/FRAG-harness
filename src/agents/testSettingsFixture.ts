import type { SettingsView } from '../../shared/contracts/reviewSettings';
export const settingsFixture: SettingsView = {
  application: { revision:0, settings:{mode:'files',topK:3,researchInCustom:false,checklist:[]} },
  project: { revision:0, settings:{mode:'files',file:null,plugin:null,synthetic:false} },
  conversation: { revision:0,settings:null },
};
