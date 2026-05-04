
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 7 — SETTINGS (LLM Providers tab)
// ─────────────────────────────────────────────────────────────────────────────

function FrameSettings({ onNav }) {
  const [activeTab, setActiveTab] = React.useState('llm');
  const [activeProvider, setActiveProvider] = React.useState('ollama');
  const [testState, setTestState] = React.useState({}); // { provId: 'idle'|'loading'|'done' }
  const [testOutput, setTestOutput] = React.useState({});

  const tabs = [
    { id:'general', label:'General' },
    { id:'llm', label:'LLM Providers' },
    { id:'image', label:'Image Gen' },
    { id:'voices', label:'Voices' },
    { id:'subtitles', label:'Subtitles' },
    { id:'music', label:'Music' },
    { id:'storage', label:'Storage' },
    { id:'advanced', label:'Advanced' },
  ];

  const providers = [
    {
      id:'ollama',
      name:'Ollama',
      desc:'Local inference — no API key required',
      icon:'cpu',
      models:['deepseek-v4-pro:cloud','llama3.2:3b','mistral:7b','phi3:mini'],
      defaultModel:'deepseek-v4-pro:cloud',
      fields:[
        { key:'base_url', label:'Base URL', placeholder:'http://127.0.0.1:11434', mono:true },
      ],
    },
    {
      id:'gemini',
      name:'Gemini',
      desc:'Google cloud cascade — fast and accurate',
      icon:'zap',
      models:['gemini-2.5-flash','gemini-2.5-pro','gemini-2.0-flash'],
      defaultModel:'gemini-2.5-flash',
      fields:[
        { key:'api_key', label:'API Key', placeholder:'AIzaSy...', mono:true, secret:true },
      ],
    },
    {
      id:'pollinations',
      name:'Pollinations',
      desc:'Free tier — no API key needed',
      icon:'globe',
      models:['openai','mistral','llama'],
      defaultModel:'openai',
      fields:[],
    },
  ];

  const runTest = (provId) => {
    setTestState(s => ({...s, [provId]:'loading'}));
    setTestOutput(o => ({...o, [provId]:''}));
    // Simulate streaming
    const words = ['Hola!', ' El', ' universo', ' tiene', ' aproximadamente', ' 13.8', ' mil', ' millones', ' de', ' años.'];
    let i = 0;
    const interval = setInterval(() => {
      if (i >= words.length) {
        clearInterval(interval);
        setTestState(s => ({...s, [provId]:'done'}));
        return;
      }
      setTestOutput(o => ({...o, [provId]: (o[provId]||'') + words[i]}));
      i++;
    }, 180);
  };

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <TopBar title="Settings" onNew={() => {}}/>

      {/* Tab bar */}
      <div style={{
        display:'flex', gap:0, padding:'0 24px',
        borderBottom:`1px solid ${T.hairline}`, flexShrink:0, overflowX:'auto',
      }}>
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
            padding:'10px 16px', background:'none', border:'none', cursor:'pointer',
            fontSize:13, fontWeight: activeTab===tab.id ? 600 : 400,
            color: activeTab===tab.id ? T.primary : T.muted,
            borderBottom: `2px solid ${activeTab===tab.id ? T.amber : 'transparent'}`,
            transition:'all 120ms', whiteSpace:'nowrap',
            marginBottom:-1,
          }}>
            {tab.label}
          </button>
        ))}
      </div>

      <div style={{ flex:1, overflow:'auto', padding:32 }}>
        {activeTab === 'llm' && (
          <div style={{ maxWidth:780 }}>
            <div style={{ marginBottom:28 }}>
              <div style={{ fontSize:18, fontWeight:700, color: T.primary, letterSpacing:'-0.02em', marginBottom:4 }}>
                LLM Providers
              </div>
              <div style={{ fontSize:13, color: T.secondary }}>
                Choose your inference backend. The active provider is used for all script generation, metadata, and tweet copy.
              </div>
            </div>

            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              {providers.map(prov => {
                const isActive = activeProvider === prov.id;
                const ts = testState[prov.id] || 'idle';
                return (
                  <div key={prov.id} style={{
                    borderRadius:12, border:`1px solid ${isActive ? T.amber+'44' : T.hairline}`,
                    background: isActive ? T.amberDim : T.surf2,
                    overflow:'hidden', transition:'all 160ms',
                  }}>
                    {/* Provider header */}
                    <div style={{ padding:'16px 20px', display:'flex', alignItems:'center', gap:14 }}>
                      <div style={{
                        width:36, height:36, borderRadius:8, flexShrink:0,
                        background: isActive ? T.amber+'22' : T.surf3,
                        border:`1px solid ${isActive ? T.amber+'44' : T.hairline}`,
                        display:'flex', alignItems:'center', justifyContent:'center',
                      }}>
                        <Icon name={prov.icon} size={16} color={isActive ? T.amber : T.secondary}/>
                      </div>
                      <div style={{ flex:1 }}>
                        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                          <span style={{ fontSize:14, fontWeight:600, color: T.primary }}>{prov.name}</span>
                          {isActive && (
                            <span style={{
                              fontSize:10, fontWeight:600, padding:'2px 7px', borderRadius:4,
                              background: T.amber+'22', color: T.amber,
                              border:`1px solid ${T.amber}44`, letterSpacing:'0.04em',
                            }}>ACTIVE</span>
                          )}
                        </div>
                        <div style={{ fontSize:12, color: T.muted }}>{prov.desc}</div>
                      </div>
                      <button onClick={() => setActiveProvider(prov.id)} style={{
                        padding:'6px 14px', borderRadius:8, cursor:'pointer', fontSize:12,
                        border: `1px solid ${isActive ? T.amber : T.hairline}`,
                        background: isActive ? T.amber : 'transparent',
                        color: isActive ? '#0B0B0D' : T.secondary,
                        fontWeight: isActive ? 600 : 400,
                        transition:'all 120ms',
                      }}>
                        {isActive ? 'Active' : 'Set active'}
                      </button>
                    </div>

                    {/* Provider body */}
                    <div style={{ padding:'0 20px 20px', display:'flex', flexDirection:'column', gap:12, borderTop:`1px solid ${T.hairline}` }}>
                      <div style={{ paddingTop:16 }}/>

                      {/* Model picker */}
                      <div>
                        <label style={{ fontSize:11, fontWeight:600, color: T.muted, textTransform:'uppercase', letterSpacing:'0.06em', display:'block', marginBottom:6 }}>
                          Model
                        </label>
                        <select defaultValue={prov.defaultModel} style={{
                          background: T.surf3, border:`1px solid ${T.hairline}`,
                          borderRadius:8, color: T.primary, fontSize:12, padding:'7px 12px',
                          outline:'none', cursor:'pointer', width:300,
                          fontFamily:'Geist Mono, monospace',
                        }}>
                          {prov.models.map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                      </div>

                      {/* Fields */}
                      {prov.fields.map(field => (
                        <div key={field.key}>
                          <label style={{ fontSize:11, fontWeight:600, color: T.muted, textTransform:'uppercase', letterSpacing:'0.06em', display:'block', marginBottom:6 }}>
                            {field.label}
                          </label>
                          <input
                            type={field.secret ? 'password' : 'text'}
                            placeholder={field.placeholder}
                            defaultValue={field.key==='base_url' ? 'http://127.0.0.1:11434' : ''}
                            style={{
                              background: T.surf3, border:`1px solid ${T.hairline}`,
                              borderRadius:8, color: T.primary, fontSize:12, padding:'7px 12px',
                              outline:'none', width:320, fontFamily: field.mono ? 'Geist Mono, monospace' : 'inherit',
                            }}
                          />
                        </div>
                      ))}

                      {/* Test connection */}
                      <div>
                        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                          <button onClick={() => runTest(prov.id)} disabled={ts==='loading'} style={{
                            padding:'6px 14px', borderRadius:8, cursor: ts==='loading' ? 'wait' : 'pointer',
                            border:`1px solid ${T.hairline}`,
                            background: T.surf3, color: T.secondary, fontSize:12,
                            display:'flex', alignItems:'center', gap:6, transition:'all 120ms',
                          }}
                            onMouseEnter={e => { if(ts!=='loading') { e.currentTarget.style.borderColor=T.amberRing; e.currentTarget.style.color=T.primary; }}}
                            onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.secondary; }}
                          >
                            {ts==='loading'
                              ? <><span style={{ width:10, height:10, borderRadius:'50%', border:`2px solid ${T.muted}`, borderTopColor:T.amber, animation:'spin 0.8s linear infinite', display:'inline-block' }}/> Testing…</>
                              : ts==='done'
                              ? <><Icon name="check" size={12} color={T.success}/> Test again</>
                              : <><Icon name="zap" size={12} color="currentColor"/> Test connection</>
                            }
                          </button>
                          {ts==='done' && (
                            <span style={{ fontSize:11, color: T.success, display:'flex', alignItems:'center', gap:4 }}>
                              <Icon name="check" size={11} color={T.success}/>
                              Connected
                            </span>
                          )}
                        </div>
                        {testOutput[prov.id] && (
                          <div style={{
                            marginTop:8, padding:'8px 12px', borderRadius:8,
                            background: T.surf3, border:`1px solid ${T.hairline}`,
                            fontSize:11, fontFamily:'Geist Mono, monospace',
                            color: T.secondary, lineHeight:1.7,
                          }}>
                            {testOutput[prov.id]}
                            {ts==='loading' && <span style={{ animation:'blink 1s step-end infinite' }}>▌</span>}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {activeTab !== 'llm' && (
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', height:'100%', gap:12, color: T.muted }}>
            <Icon name="settings" size={32} color={T.muted} style={{ opacity:0.4 }}/>
            <span style={{ fontSize:13 }}>
              {tabs.find(t=>t.id===activeTab)?.label} settings
            </span>
            <span style={{ fontSize:11, color: T.muted }}>Switch to the LLM Providers tab to see the full design.</span>
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

Object.assign(window, { FrameSettings });
