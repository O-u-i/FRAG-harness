const test=require('node:test'),assert=require('node:assert/strict');
const {hostEnvironment}=require('../host-launcher.cjs');
test('backend environment receives no native/model credentials or inherited provider settings',()=>{
 const env=hostEnvironment('synthetic-installation','synthetic-ephemeral-token',{PATH:'synthetic-path',OPENAI_API_KEY:'synthetic-private-model-key',FINANCE_CORE_PLUGIN_READ_TOKEN:'synthetic-private-fc-token',NODE_OPTIONS:'synthetic-unsafe-injection'});
 assert.equal(env.FRAG_EXTENSION_TOKEN,'synthetic-ephemeral-token');
 for(const name of ['OPENAI_API_KEY','FINANCE_CORE_PLUGIN_READ_TOKEN','NODE_OPTIONS']) assert.equal(env[name],undefined);
 assert.equal(env.PYTHONDONTWRITEBYTECODE,'1');
});
