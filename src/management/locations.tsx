import {useEffect,useState} from 'react';
import {request} from './client';
import {Icon} from './icons';
type Locations={stateRoot:string;hostRoot:string;acceptanceRoot:string;sourceRoot:string;planPath:string};
export function LocationsPanel({refreshKey=0}:{refreshKey?:number}){
  const [locations,setLocations]=useState<Locations>();const [error,setError]=useState('');
  const [open,setOpen]=useState(false);
  useEffect(()=>{if(!open)return;let current=true;void request('locations-info').then(value=>{if(current){setLocations(value);setError('');}}).catch(e=>{if(current)setError(e instanceof Error?e.message:'LOCATION_UNAVAILABLE');});return()=>{current=false;};},[open,refreshKey]);
  async function act(name:string){try{await request(name);setError('');}catch(e){setError(e instanceof Error?e.message:'LOCATION_UNAVAILABLE');}}
  return <details className="panel locations-panel" onToggle={e=>setOpen(e.currentTarget.open)}><summary>Folders & storage <span className="muted">Private state stays separate from sources</span></summary>
    {error&&<p role="alert" className="error">{error}</p>}
    {locations&&<dl className="path-list"><dt>Private state</dt><dd><code>{locations.stateRoot}</code></dd><dt>Host</dt><dd><code>{locations.hostRoot}</code></dd><dt>Acceptance</dt><dd><code>{locations.acceptanceRoot}</code></dd><dt>Test source</dt><dd><code>{locations.sourceRoot}</code></dd></dl>}
    <div className="toolbar"><button onClick={()=>void act('state-open')}><Icon name="folder"/>Open private state</button><button onClick={()=>void act('settings-open')}>Configure locations…</button></div>
    <p className="muted">Native Settings: frag.privateStateRoot, frag.hostInstallation and frag.acceptanceRoot. Stop/reload after changing state or Host. No automatic migration, merge or deletion; source authorization stays in Sources.</p>
  </details>;
}
