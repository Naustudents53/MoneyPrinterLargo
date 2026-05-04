
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 4 — LIBRARY
// ─────────────────────────────────────────────────────────────────────────────

function FrameLibrary({ onNav }) {
  const [selected, setSelected] = React.useState(null);
  const [filterStatus, setFilterStatus] = React.useState('all');
  const [filterPlatform, setFilterPlatform] = React.useState('all');
  const [search, setSearch] = React.useState('');

  const statuses = ['all','uploaded','rendering','draft','failed'];

  const filtered = MOCK_LIBRARY.filter(r => {
    if (filterStatus !== 'all' && r.status !== filterStatus) return false;
    if (search && !r.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const selectedRender = selected ? MOCK_LIBRARY.find(r => r.id === selected) : null;

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <TopBar title="Library" onNew={() => onNav('new-short')}/>

      {/* Filters bar */}
      <div style={{
        height:48, display:'flex', alignItems:'center', gap:12, padding:'0 24px',
        borderBottom:`1px solid ${T.hairline}`, flexShrink:0,
      }}>
        {/* Search */}
        <div style={{
          display:'flex', alignItems:'center', gap:8,
          background: T.surf2, border:`1px solid ${T.hairline}`,
          borderRadius:8, padding:'0 10px', height:32, flex:'0 0 220px',
          transition:'border-color 120ms',
        }}>
          <Icon name="search" size={13} color={T.muted}/>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            style={{
              background:'none', border:'none', outline:'none',
              fontSize:12, color: T.primary, width:'100%',
            }}
          />
        </div>

        {/* Status filter pills */}
        <div style={{ display:'flex', gap:4 }}>
          {statuses.map(s => (
            <button key={s} onClick={() => setFilterStatus(s)} style={{
              padding:'4px 10px', borderRadius:6, border:'none', cursor:'pointer',
              fontSize:11, fontWeight:500, transition:'all 120ms',
              background: filterStatus === s ? T.amberDim : T.surf2,
              color: filterStatus === s ? T.amber : T.secondary,
              border: `1px solid ${filterStatus === s ? T.amberRing : T.hairline}`,
            }}>
              {s === 'all' ? 'All' : s.charAt(0).toUpperCase()+s.slice(1)}
            </button>
          ))}
        </div>

        <div style={{ flex:1 }}/>

        {/* Account filter */}
        <select style={{
          background: T.surf2, border:`1px solid ${T.hairline}`,
          borderRadius:8, color: T.secondary, fontSize:12, padding:'5px 10px',
          outline:'none', cursor:'pointer',
        }}>
          <option>All accounts</option>
          <option>Savirox</option>
          <option>CosmosES</option>
        </select>

        {/* Date filter */}
        <select style={{
          background: T.surf2, border:`1px solid ${T.hairline}`,
          borderRadius:8, color: T.secondary, fontSize:12, padding:'5px 10px',
          outline:'none', cursor:'pointer',
        }}>
          <option>Last 7 days</option>
          <option>Last 30 days</option>
          <option>All time</option>
        </select>

        <span style={{ fontSize:11, color: T.muted, fontFamily:'Geist Mono, monospace' }}>
          {filtered.length} results
        </span>
      </div>

      <div style={{ flex:1, display:'flex', overflow:'hidden' }}>
        {/* Table */}
        <div style={{ flex:1, overflow:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
            <thead>
              <tr style={{ borderBottom:`1px solid ${T.hairline}` }}>
                {['','Title','Account / Series','Platform','Duration','Created','Status','Views'].map(h => (
                  <th key={h} style={{
                    padding:'8px 16px', textAlign:'left', fontWeight:600,
                    fontSize:11, color: T.muted, letterSpacing:'0.04em',
                    textTransform:'uppercase', whiteSpace:'nowrap',
                    position:'sticky', top:0, background: T.surf1, zIndex:2,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => (
                <tr key={r.id}
                  onClick={() => setSelected(r.id === selected ? null : r.id)}
                  style={{
                    borderBottom:`1px solid ${T.hairlineS}`,
                    background: r.id === selected ? T.amberDim : 'transparent',
                    cursor:'pointer', transition:'background 80ms',
                  }}
                  onMouseEnter={e => { if(r.id !== selected) e.currentTarget.style.background=T.surf2; }}
                  onMouseLeave={e => { if(r.id !== selected) e.currentTarget.style.background='transparent'; }}
                >
                  {/* Thumb */}
                  <td style={{ padding:'10px 16px', width:56 }}>
                    <div style={{
                      width: r.aspect==='9:16' ? 28 : 48, height:r.aspect==='9:16' ? 50 : 27,
                      borderRadius:4, background:`linear-gradient(135deg, ${r.thumb}, ${r.thumb}88)`,
                      border:`1px solid ${T.hairline}`, flexShrink:0,
                      display:'flex', alignItems:'center', justifyContent:'center',
                    }}>
                      <span style={{ fontSize:7, color:'rgba(255,255,255,0.25)', fontFamily:'Geist Mono, monospace' }}>{r.aspect}</span>
                    </div>
                  </td>
                  <td style={{ padding:'10px 16px', maxWidth:280 }}>
                    <div style={{ color: T.primary, fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.title}</div>
                  </td>
                  <td style={{ padding:'10px 16px', color: T.secondary }}>Savirox</td>
                  <td style={{ padding:'10px 16px' }}><PlatformGlyph platform={r.platform}/></td>
                  <td style={{ padding:'10px 16px', fontFamily:'Geist Mono, monospace', color: T.secondary }}>{r.duration}</td>
                  <td style={{ padding:'10px 16px', color: T.muted, whiteSpace:'nowrap' }}>{r.date}</td>
                  <td style={{ padding:'10px 16px' }}><StatusPill status={r.status} size="xs"/></td>
                  <td style={{ padding:'10px 16px', fontFamily:'Geist Mono, monospace', color: r.views ? T.success : T.muted }}>{r.views || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Side drawer */}
        {selectedRender && (
          <div style={{
            width:300, borderLeft:`1px solid ${T.hairline}`,
            background: T.surf1, display:'flex', flexDirection:'column',
            overflow:'auto', flexShrink:0,
          }}>
            <div style={{ padding:'16px 20px', borderBottom:`1px solid ${T.hairline}`, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              <span style={{ fontSize:12, fontWeight:600, color: T.primary }}>Details</span>
              <button onClick={() => setSelected(null)} style={{
                background:'none', border:'none', cursor:'pointer', color: T.muted, padding:4,
              }}><Icon name="x" size={14} color="currentColor"/></button>
            </div>

            {/* Thumb */}
            <div style={{ padding:20 }}>
              <div style={{
                width:'100%', aspectRatio: selectedRender.aspect==='9:16' ? '9/16' : '16/9',
                borderRadius:8, background:`linear-gradient(135deg, ${selectedRender.thumb}, ${selectedRender.thumb}88)`,
                border:`1px solid ${T.hairline}`, marginBottom:16,
                display:'flex', alignItems:'center', justifyContent:'center',
              }}>
                <span style={{ fontFamily:'Geist Mono, monospace', fontSize:11, color:'rgba(255,255,255,0.2)' }}>
                  {selectedRender.aspect}
                </span>
              </div>

              <div style={{ fontSize:13, fontWeight:600, color: T.primary, marginBottom:8, lineHeight:1.4 }}>
                {selectedRender.title}
              </div>
              <StatusPill status={selectedRender.status}/>

              <div style={{ marginTop:16, display:'flex', flexDirection:'column', gap:8 }}>
                {[
                  { label:'Duration', val: selectedRender.duration },
                  { label:'Created', val: selectedRender.date },
                  { label:'Account', val: 'Savirox' },
                  { label:'Views', val: selectedRender.views || '—' },
                ].map(m => (
                  <div key={m.label} style={{ display:'flex', justifyContent:'space-between', fontSize:12 }}>
                    <span style={{ color: T.muted }}>{m.label}</span>
                    <span style={{ color: T.primary, fontFamily:'Geist Mono, monospace' }}>{m.val}</span>
                  </div>
                ))}
              </div>

              <div style={{ marginTop:20, display:'flex', flexDirection:'column', gap:8 }}>
                <button style={{
                  width:'100%', padding:'8px', borderRadius:8,
                  background: T.amber, border:'none', color:'#0B0B0D',
                  fontSize:12, fontWeight:600, cursor:'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center', gap:6,
                }}>
                  <Icon name="refresh" size={12} color="#0B0B0D"/>
                  Regenerate from here
                </button>
                <button style={{
                  width:'100%', padding:'8px', borderRadius:8,
                  background:'transparent', border:`1px solid ${T.hairline}`,
                  color: T.secondary, fontSize:12, cursor:'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center', gap:6,
                }}>
                  <Icon name="external" size={12} color="currentColor"/>
                  Open on YouTube
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { FrameLibrary });
