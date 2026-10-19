export type Preferences = {theme:'system'|'dracula'|'living';density:'comfortable'|'compact';motion:boolean;runLimit:25|50|100|200;advanced:boolean};
export const defaultPreferences:Preferences = {theme:'system',density:'compact',motion:true,runLimit:50,advanced:false};
export function normalizePreferences(raw:unknown):Preferences {
  const value = raw && typeof raw==='object' ? raw as Record<string,unknown> : {};
  return {theme:['system','dracula','living'].includes(value.theme as string)?value.theme as Preferences['theme']:defaultPreferences.theme,
    density:value.density==='comfortable'?'comfortable':'compact',motion:typeof value.motion==='boolean'?value.motion:true,
    runLimit:[25,50,100,200].includes(value.runLimit as number)?value.runLimit as Preferences['runLimit']:50,
    advanced:value.advanced===true};
}
