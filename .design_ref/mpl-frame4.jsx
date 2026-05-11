// ─────────────────────────────────────────────────────────────────────────────
// FRAME 4 — CANALES YOUTUBE (rack de canales) + DETALLE
// ─────────────────────────────────────────────────────────────────────────────

function ChannelCard({ ch, onOpen }) {
  const T = useT();
  const last = MOCK_VIDEOS.filter(v => v.channel === ch.id).slice(0, 3);
  return (
    <Surface hover style={{ padding:0, overflow:'hidden', cursor:'pointer' }}>
      <div onClick={() => onOpen(ch.id)} style={{ display:'flex', flexDirection:'column' }}>
        {/* Header rule */}
        <div style={{ height:3, background: ch.accent }}/>

        <div style={{ padding:'18px 18px 14px', display:'flex', alignItems:'flex-start', gap:14 }}>
          <div style={{
            width:54, height:54, borderRadius:10,
            background:`linear-gradient(135deg, color-mix(in oklch, ${ch.accent} 35%, ${T.bg}), ${T.bg})`,
            border:`1px solid color-mix(in oklch, ${ch.accent} 30%, ${T.hairline})`,
            display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
            position:'relative', overflow:'hidden',
          }}>
            <span style={{ fontFamily:"'Sora', sans-serif", fontSize:24, fontWeight:700, color:ch.accent, letterSpacing:'-0.04em' }}>
              {ch.nickname[0]}
            </span>
            <div style={{ position:'absolute', inset:0, opacity:0.10,
              backgroundImage:'repeating-linear-gradient(45deg, currentColor 0, currentColor 1px, transparent 0, transparent 6px)' }}/>
          </div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:3 }}>
              <span style={{ fontFamily:"'Sora', sans-serif", fontSize:16, fontWeight:600, color:T.fg, letterSpacing:'-0.02em', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{ch.nickname}</span>
              <span style={{ fontSize:11, color:T.muted, fontFamily:"'JetBrains Mono', monospace" }}>{ch.flag}</span>
            </div>
            <div style={{ fontSize:12, color:T.fgDim, marginBottom:8 }}>{ch.niche}</div>
            <div style={{ display:'flex', gap:8, fontSize:11, fontFamily:"'JetBrains Mono', monospace" }}>
              <span style={{ color:T.fg }}>{ch.subs} <span style={{ color:T.muted }}>subs</span></span>
              <span style={{ color:T.muted }}>·</span>
              <span style={{ color:T.fg }}>{ch.uploads} <span style={{ color:T.muted }}>vids</span></span>
            </div>
          </div>
        </div>

        {/* Last 3 videos strip */}
        <div style={{ padding:'0 18px 14px', display:'flex', gap:6 }}>
          {last.map(v => (
            <div key={v.id} style={{
              flex:1, aspectRatio:'9/16', borderRadius:6,
              background:`linear-gradient(135deg, ${v.thumb}, ${v.thumb}88)`,
              border:`1px solid ${T.hairline}`, position:'relative', overflow:'hidden', minHeight:90, maxHeight:130,
            }}>
              <div style={{ position:'absolute', inset:0, opacity:0.12,
                backgroundImage:'repeating-linear-gradient(45deg, rgba(255,255,255,0.3) 0, rgba(255,255,255,0.3) 1px, transparent 0, transparent 50%)',
                backgroundSize:'6px 6px' }}/>
              <span style={{ position:'absolute', bottom:4, right:4, fontFamily:"'JetBrains Mono', monospace", fontSize:9, color:'rgba(255,255,255,0.6)', background:'rgba(0,0,0,0.4)', padding:'1px 4px', borderRadius:3 }}>{v.duration}</span>
              {v.status === 'rendering' && (
                <span style={{ position:'absolute', top:4, left:4, width:6, height:6, borderRadius:'50%', background:T.warning, animation:'mpl-pulse 1.4s infinite' }}/>
              )}
            </div>
          ))}
          {last.length < 3 && Array.from({ length: 3 - last.length }).map((_,i) => (
            <div key={`empty-${i}`} style={{ flex:1, aspectRatio:'9/16', borderRadius:6, border:`1px dashed ${T.hairline}`, minHeight:90, maxHeight:130 }}/>
          ))}
        </div>

        {/* Meta strip */}
        <div style={{ display:'flex', alignItems:'center', gap:8, padding:'10px 18px', borderTop:`1px solid ${T.hairlineS}`, background:T.bg }}>
          <Chip mono style={{ fontSize:10 }}>{ch.shortVoice.replace('Neural','').replace('es-ES-','').replace('es-MX-','')}</Chip>
          <span style={{ fontSize:11, color:T.muted, flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {ch.last} · <span style={{ color:T.fgDim }}>{ch.lastDate}</span>
          </span>
          <Icon name="chevronR" size={13} color={T.muted}/>
        </div>
      </div>
    </Surface>
  );
}

function FrameChannels({ onNav }) {
  const T = useT();
  const totalSubs = MOCK_CHANNELS.reduce((acc, c) => acc + parseFloat(c.subs), 0).toFixed(0);
  const totalVids = MOCK_CHANNELS.reduce((acc, c) => acc + c.uploads, 0);

  return (
    <MeshBg>
      <div style={{ flex:1, overflow:'auto', padding:'28px 28px 40px' }}>
        <div style={{ maxWidth:1440, margin:'0 auto', display:'flex', flexDirection:'column', gap:20 }}>
          {/* Header bar */}
          <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:18, flexWrap:'wrap' }}>
            <div>
              <Eyebrow style={{ marginBottom:6, display:'block' }}>· canales · youtube</Eyebrow>
              <Display size={36} weight={600} style={{ color:T.fg }}>Tu rack de canales</Display>
              <p style={{ fontSize:13, color:T.fgDim, marginTop:6, margin:'6px 0 0' }}>
                {MOCK_CHANNELS.length} activos · {totalSubs}K subs combinados · {totalVids} vídeos publicados
              </p>
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <div style={{
                display:'flex', alignItems:'center', gap:8, height:36, padding:'0 12px',
                background:T.surface, border:`1px solid ${T.hairline}`, borderRadius:8, color:T.fgDim,
              }}>
                <Icon name="search" size={14}/>
                <input placeholder="Filtrar por canal o nicho…" style={{
                  background:'transparent', border:'none', outline:'none', color:T.fg,
                  fontFamily:'inherit', fontSize:13, width:240,
                }}/>
              </div>
              <Btn variant="brand" leading={<Icon name="plus" size={14} color="#0B0F14"/>}>Nuevo canal</Btn>
            </div>
          </div>

          {/* Grid */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(320px, 1fr))', gap:14 }}>
            {MOCK_CHANNELS.map(ch => (
              <ChannelCard key={ch.id} ch={ch} onOpen={() => onNav('channels')}/>
            ))}
            {/* Add card */}
            <button style={{
              minHeight:280, border:`1px dashed ${T.hairline}`, background:'transparent',
              borderRadius:12, cursor:'pointer', color:T.muted, display:'flex',
              alignItems:'center', justifyContent:'center', flexDirection:'column', gap:10,
              fontFamily:'inherit', transition:'all 160ms ease',
            }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = T.primaryR; e.currentTarget.style.color = T.primary; e.currentTarget.style.background = T.primaryS; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = T.hairline; e.currentTarget.style.color = T.muted; e.currentTarget.style.background = 'transparent'; }}
            >
              <span style={{
                width:46, height:46, borderRadius:'50%', border:`1.5px dashed currentColor`,
                display:'flex', alignItems:'center', justifyContent:'center',
              }}>
                <Icon name="plus" size={20}/>
              </span>
              <span style={{ fontSize:13, fontWeight:500, letterSpacing:'-0.01em' }}>Nuevo canal</span>
            </button>
          </div>
        </div>
      </div>
    </MeshBg>
  );
}

Object.assign(window, { FrameChannels, ChannelCard });
