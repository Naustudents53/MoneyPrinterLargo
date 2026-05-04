
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 5 — SERIES
// ─────────────────────────────────────────────────────────────────────────────

function FrameSeries({ onNav }) {
  const [openSeries, setOpenSeries] = React.useState(null);
  const [editStyle, setEditStyle] = React.useState(false);

  const seriesColors = [
    { bg:'hsl(20,40%,8%)', accent: T.amber },
    { bg:'hsl(210,40%,8%)', accent: T.info },
    { bg:'hsl(270,30%,8%)', accent:'#C084FC' },
    { bg:'hsl(150,30%,8%)', accent: T.success },
  ];

  const episodes = [
    { ep:1, title:'El origen del universo', date:'Mar 12', status:'uploaded', views:'14.2K' },
    { ep:2, title:'Agujeros negros primordiales', date:'Mar 19', status:'uploaded', views:'9.8K' },
    { ep:3, title:'La materia oscura revelada', date:'Mar 26', status:'uploaded', views:'11.1K' },
    { ep:4, title:'Nebulosas: fábricas de estrellas', date:'Apr 2', status:'uploaded', views:'8.4K' },
    { ep:5, title:'El fin del universo observable', date:'Apr 9', status:'uploaded', views:'17.3K' },
    { ep:6, title:'Cuásares y galaxias activas', date:'Apr 16', status:'uploaded', views:'7.9K' },
    { ep:7, title:'Ondas gravitacionales', date:'Apr 23', status:'uploaded', views:'12.6K' },
    { ep:8, title:'La paradoja del tiempo', date:'Apr 30', status:'uploaded', views:'15.0K' },
    { ep:9, title:'Multiverso: teorías y pruebas', date:'May 2', status:'uploaded', views:'6.2K' },
    { ep:10, title:'Singularidades desnudas', date:'—', status:'draft', views:null },
    { ep:11, title:'TBD', date:'May 5', status:'draft', views:null },
    { ep:12, title:'TBD', date:'May 12', status:'draft', views:null },
  ];

  if (openSeries !== null) {
    const s = MOCK_SERIES[openSeries];
    const sc = seriesColors[openSeries];
    return (
      <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
        <TopBar title="Series" onNew={() => {}}/>
        <div style={{ flex:1, overflow:'auto', padding:32 }}>
          {/* Back */}
          <button onClick={() => setOpenSeries(null)} style={{
            display:'flex', alignItems:'center', gap:6,
            background:'none', border:'none', color: T.muted, cursor:'pointer',
            fontSize:12, marginBottom:24, padding:0,
          }}>
            <Icon name="chevronL" size={14} color="currentColor"/>
            All series
          </button>

          {/* Series header */}
          <div style={{
            display:'flex', gap:24, marginBottom:32, alignItems:'flex-start',
          }}>
            <div style={{
              width:120, height:120, borderRadius:12,
              background:`linear-gradient(135deg, ${sc.bg}, ${T.surf1})`,
              border:`1px solid ${sc.accent}22`,
              display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
            }}>
              <Icon name="layers" size={40} color={sc.accent} style={{ opacity:0.5 }}/>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:28, fontWeight:700, color: T.primary, letterSpacing:'-0.03em', marginBottom:6 }}>{s.name}</div>
              <div style={{ display:'flex', gap:8, flexWrap:'wrap', marginBottom:12 }}>
                <Chip color={sc.accent}>{episodes.filter(e=>e.status==='uploaded').length} episodes</Chip>
                <Chip color={T.success}>Last: {s.lastDate}</Chip>
                <Chip>Next: {s.nextDate}</Chip>
              </div>
              {/* Style preset */}
              <div style={{ marginTop:16 }}>
                <div style={{ fontSize:11, fontWeight:600, color: T.muted, textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:8 }}>
                  Style Preset
                </div>
                <div style={{ display:'flex', gap:12 }}>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:10, color: T.muted, marginBottom:4 }}>Image style suffix</div>
                    {editStyle ? (
                      <textarea defaultValue={s.imageStyle} style={{
                        width:'100%', background: T.surf2, border:`1px solid ${T.amberRing}`,
                        borderRadius:8, padding:8, color: T.primary, fontSize:11,
                        fontFamily:'Geist Mono, monospace', outline:'none', resize:'none', rows:2,
                      }} rows={2}/>
                    ) : (
                      <div style={{
                        padding:'6px 10px', borderRadius:8, background: T.surf2,
                        border:`1px solid ${T.hairline}`, fontSize:11,
                        fontFamily:'Geist Mono, monospace', color: T.secondary, lineHeight:1.5,
                      }}>{s.imageStyle}</div>
                    )}
                  </div>
                  <div style={{ width:160 }}>
                    <div style={{ fontSize:10, color: T.muted, marginBottom:4 }}>Default voice</div>
                    <div style={{
                      padding:'6px 10px', borderRadius:8, background: T.surf2,
                      border:`1px solid ${T.hairline}`, fontSize:11,
                      fontFamily:'Geist Mono, monospace', color: T.secondary,
                    }}>{s.voice}</div>
                  </div>
                </div>
                <div style={{ marginTop:8, display:'flex', gap:8 }}>
                  <button onClick={() => setEditStyle(!editStyle)} style={{
                    padding:'6px 12px', borderRadius:8, border:`1px solid ${T.hairline}`,
                    background:'transparent', color: T.secondary, fontSize:12, cursor:'pointer',
                  }}>{editStyle ? 'Save changes' : 'Edit preset'}</button>
                </div>
              </div>
            </div>
          </div>

          {/* Episodes */}
          <div style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.06em', textTransform:'uppercase', marginBottom:12 }}>Episodes</div>
          <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
            {episodes.map(ep => (
              <div key={ep.ep} style={{
                display:'flex', alignItems:'center', gap:16, padding:'10px 14px',
                borderRadius:8, background: T.surf2, border:`1px solid ${T.hairline}`,
                transition:'background 80ms', cursor:'pointer',
              }}
                onMouseEnter={e => e.currentTarget.style.background=T.surf3}
                onMouseLeave={e => e.currentTarget.style.background=T.surf2}
              >
                <span style={{ fontSize:11, fontFamily:'Geist Mono, monospace', color: T.muted, width:24, flexShrink:0 }}>
                  {String(ep.ep).padStart(2,'0')}
                </span>
                <span style={{ flex:1, fontSize:13, color: ep.status==='draft' ? T.muted : T.primary, fontWeight:500 }}>
                  {ep.title}
                </span>
                <span style={{ fontSize:11, color: T.muted, width:50, textAlign:'right' }}>{ep.date}</span>
                <StatusPill status={ep.status} size="xs"/>
                <span style={{ fontSize:11, fontFamily:'Geist Mono, monospace', color: T.success, width:48, textAlign:'right' }}>{ep.views || '—'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <TopBar title="Series" onNew={() => {}}/>
      <div style={{ flex:1, overflow:'auto', padding:32 }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(260px,1fr))', gap:16 }}>
          {MOCK_SERIES.map((s, i) => {
            const sc = seriesColors[i];
            return (
              <button key={s.id} onClick={() => setOpenSeries(i)} style={{
                background: T.surf2, border:`1px solid ${T.hairline}`,
                borderRadius:12, padding:20, textAlign:'left', cursor:'pointer',
                transition:'all 160ms ease', display:'flex', flexDirection:'column', gap:14,
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor=sc.accent+'44'; e.currentTarget.style.background=sc.bg; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.background=T.surf2; }}
              >
                {/* Cover art placeholder */}
                <div style={{
                  height:100, borderRadius:8, overflow:'hidden', position:'relative',
                  background:`linear-gradient(135deg, ${sc.bg}, ${T.surf1})`,
                  border:`1px solid ${sc.accent}22`,
                  display:'flex', alignItems:'center', justifyContent:'center',
                }}>
                  <div style={{
                    position:'absolute', inset:0, opacity:0.07,
                    backgroundImage:'repeating-linear-gradient(45deg, rgba(255,255,255,0.4) 0, rgba(255,255,255,0.4) 1px, transparent 0, transparent 50%)',
                    backgroundSize:'8px 8px',
                  }}/>
                  <Icon name="layers" size={28} color={sc.accent} style={{ opacity:0.5 }}/>
                </div>
                <div>
                  <div style={{ fontSize:15, fontWeight:600, color: T.primary, letterSpacing:'-0.02em', marginBottom:4 }}>{s.name}</div>
                  <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                    <Chip color={sc.accent}>{s.episodes} eps</Chip>
                    <Chip>Next {s.nextDate}</Chip>
                  </div>
                </div>
                <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                  <Chip>{s.voice}</Chip>
                </div>
                <div style={{ fontSize:10, color: T.muted, fontFamily:'Geist Mono, monospace', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  {s.imageStyle}
                </div>
              </button>
            );
          })}

          {/* Add new series */}
          <button style={{
            background:'transparent', border:`2px dashed ${T.hairline}`,
            borderRadius:12, padding:20, cursor:'pointer', minHeight:200,
            display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:8,
            color: T.muted, transition:'all 120ms',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor=T.amber+'44'; e.currentTarget.style.color=T.amber; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.muted; }}
          >
            <Icon name="plus" size={22} color="currentColor"/>
            <span style={{ fontSize:12 }}>New Series</span>
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { FrameSeries });
