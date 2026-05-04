
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 1 — HOME / OVERVIEW
// ─────────────────────────────────────────────────────────────────────────────

function FrameHome({ onNav }) {
  const makeCards = [
    {
      id:'short', label:'YouTube Short', sub:'Vertical · ~45s · AI images + TTS',
      icon:'zap', color: T.amber, bg:'#2A1F0D',
      lastRun:'hace 2h · Supernova 1054',
    },
    {
      id:'long', label:'Long-Form Video', sub:'16:9 · 15–20 min · Series',
      icon:'film', color: T.info, bg:'#0D1A2A',
      lastRun:'hace 2d · Cosmic Mysteries EP.12',
    },
    {
      id:'tweet', label:'Tweet / Affiliate', sub:'Twitter Bot · X auto-post',
      icon:'hash', color: T.success, bg:'#0D2A1A',
      lastRun:'hace 6h · Agujeros negros fact',
    },
  ];

  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }}>
      {/* Main content */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <TopBar title="Studio" onNew={() => onNav('new-short')} renderQueue={2}/>

        <div style={{ flex:1, overflow:'auto', padding:32, display:'flex', flexDirection:'column', gap:40 }}>

          {/* Make cards */}
          <section>
            <h2 style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.08em', textTransform:'uppercase', marginBottom:16 }}>
              What do you want to make?
            </h2>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:16 }}>
              {makeCards.map(card => (
                <button key={card.id} onClick={() => onNav(card.id === 'short' ? 'new-short' : card.id)} style={{
                  background: T.surf2, border:`1px solid ${T.hairline}`,
                  borderRadius:12, padding:24, textAlign:'left', cursor:'pointer',
                  position:'relative', overflow:'hidden', transition:'all 160ms ease',
                  display:'flex', flexDirection:'column', gap:12,
                }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor=card.color+'44'; e.currentTarget.style.background=card.bg; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.background=T.surf2; }}
                >
                  {/* Thumbnail placeholder */}
                  <div style={{
                    height:96, borderRadius:8, overflow:'hidden', position:'relative',
                    background:`linear-gradient(135deg, ${card.bg}, ${T.surf1})`,
                    border:`1px solid ${card.color}22`,
                    display:'flex', alignItems:'center', justifyContent:'center',
                  }}>
                    <div style={{
                      position:'absolute', inset:0, opacity:0.08,
                      backgroundImage:'repeating-linear-gradient(45deg, rgba(255,255,255,0.4) 0, rgba(255,255,255,0.4) 1px, transparent 0, transparent 50%)',
                      backgroundSize:'8px 8px',
                    }}/>
                    <Icon name={card.icon} size={32} color={card.color} style={{ opacity:0.6 }}/>
                  </div>

                  <div>
                    <div style={{ fontSize:15, fontWeight:600, color: T.primary, letterSpacing:'-0.02em', marginBottom:4 }}>
                      {card.label}
                    </div>
                    <div style={{ fontSize:12, color: T.muted }}>{card.sub}</div>
                  </div>

                  <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color: T.muted }}>
                    <span style={{ width:5, height:5, borderRadius:'50%', background: card.color, opacity:0.7 }}/>
                    {card.lastRun}
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Recent renders */}
          <section>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16 }}>
              <h2 style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.08em', textTransform:'uppercase' }}>
                Recent Renders
              </h2>
              <button onClick={() => onNav('library')} style={{
                fontSize:12, color: T.amber, background:'none', border:'none', cursor:'pointer',
                display:'flex', alignItems:'center', gap:4,
              }}>View all <Icon name="chevronR" size={12} color={T.amber}/></button>
            </div>
            <div style={{ display:'flex', gap:16, overflowX:'auto', paddingBottom:8 }}>
              {MOCK_RENDERS.map(r => <VideoTile key={r.id} render={r} size="md"/>)}
            </div>
          </section>
        </div>
      </div>

      {/* Right column */}
      <div style={{
        width:280, borderLeft:`1px solid ${T.hairline}`,
        display:'flex', flexDirection:'column', background: T.surf1, flexShrink:0,
      }}>
        {/* Today's schedule */}
        <div style={{ padding:20, borderBottom:`1px solid ${T.hairline}` }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
            <span style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.06em', textTransform:'uppercase' }}>
              Today's Schedule
            </span>
            <Icon name="calendar" size={14} color={T.muted}/>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {MOCK_SCHEDULE.map((s,i) => (
              <div key={i} style={{
                display:'flex', alignItems:'center', gap:10,
                padding:'8px 10px', borderRadius:8,
                background: T.surf2, border:`1px solid ${T.hairline}`,
              }}>
                <span style={{ fontSize:11, fontFamily:'Geist Mono, monospace', color: T.amber, flexShrink:0, width:38 }}>
                  {s.time}
                </span>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:12, color: T.primary, fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{s.topic}</div>
                  <div style={{ fontSize:10, color: T.muted }}>{s.account} · {s.type}</div>
                </div>
                <StatusPill status="pending" size="xs"/>
              </div>
            ))}
          </div>
        </div>

        {/* Disk usage */}
        <div style={{ padding:20, borderBottom:`1px solid ${T.hairline}` }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12 }}>
            <span style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.06em', textTransform:'uppercase' }}>
              Scratch Storage
            </span>
            <Icon name="db" size={14} color={T.muted}/>
          </div>
          <div style={{ fontSize:11, color: T.secondary, marginBottom:8, fontFamily:'Geist Mono, monospace' }}>
            .mp/ scratch · 2.3 GB
          </div>
          {/* Progress bar */}
          <div style={{ height:4, borderRadius:2, background: T.surf3, marginBottom:8, overflow:'hidden' }}>
            <div style={{ width:'23%', height:'100%', background: T.amber, borderRadius:2 }}/>
          </div>
          <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color: T.muted }}>
            <span>2.3 GB used</span>
            <span>10 GB total</span>
          </div>
          <button style={{
            marginTop:12, width:'100%', padding:'7px 12px',
            background:'transparent', border:`1px solid ${T.hairline}`,
            borderRadius:8, color: T.secondary, fontSize:12, cursor:'pointer',
            display:'flex', alignItems:'center', justifyContent:'center', gap:6,
            transition:'all 120ms',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor=T.danger+'44'; e.currentTarget.style.color=T.danger; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.secondary; }}
          >
            <Icon name="trash" size={12} color="currentColor"/>
            Clean scratch files
          </button>
        </div>

        {/* Quick stats */}
        <div style={{ padding:20 }}>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            {[
              { label:'Total Uploads', val:'74', color: T.primary },
              { label:'This Week', val:'8', color: T.success },
              { label:'Rendering', val:'2', color: T.warning },
              { label:'Failed', val:'1', color: T.danger },
            ].map(s => (
              <div key={s.label} style={{
                padding:'12px', borderRadius:8,
                background: T.surf2, border:`1px solid ${T.hairline}`,
              }}>
                <div style={{ fontSize:20, fontWeight:700, color: s.color, fontVariantNumeric:'tabular-nums', letterSpacing:'-0.02em' }}>{s.val}</div>
                <div style={{ fontSize:10, color: T.muted, marginTop:2 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { FrameHome });
