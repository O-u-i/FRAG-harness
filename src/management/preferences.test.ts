import {expect,test} from 'vitest';
import {defaultPreferences,normalizePreferences} from './preferences';
test('presentation preferences are bounded and cannot persist authorization or arbitrary fields',()=>{
  expect(normalizePreferences(null)).toEqual(defaultPreferences);
  expect(normalizePreferences({theme:'dracula',density:'comfortable',motion:false,runLimit:200,advanced:true,token:'private'})).toEqual({theme:'dracula',density:'comfortable',motion:false,runLimit:200,advanced:true});
  expect(normalizePreferences({theme:'invalid',runLimit:999,motion:'false',advanced:1,startPage:'admin'})).toEqual(defaultPreferences);
});
