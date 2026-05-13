// ─────────────────────────────────────────────────────────────────────────────
// FRAME 6 — LIBRARY + SERIES + EMPTY STATES (combinado)
// ─────────────────────────────────────────────────────────────────────────────

function StatusDot({ kind }) {
  const T = useT();
  const m = {
    uploaded:  { c: T.success,  l:'subido' },
    rendering: { c: T.warning,  l:'rendering', pulse:true },
    draft:     { c: T.muted,    l:'borrador' },
    failed:    { c: T.danger,   l:'falló' },
    queued:    { c: T.info,     l:'en cola', pulse:true },
  }[kind] || { c: T.muted, l:'—' };
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:6, fontSize:11, color:T.fgDim, fontFamily:"'JetBrains Mono', monospace" }}>
      <span style={{ width:6, height:6, borderRadius:'50%', background:m.c, animation: m.pulse ? 'mpl-pulse 1.4s infinite' : 'none' }}/>
      {m.l}
    </span>
  );
}

function VideoCard({ v }) {
  const T = useT();
  const ch = MOCK_CHANNELS.find(c => c.id === v.channel);
  return (
    <Surface hover style={{ padding:0, overflow:'hidden', cursor:'pointer' }}>
      <div style={{
        aspectRatio: v.kind === 'short' ? '9/16' : '16/9',
        background:`linear-gradient(135deg, ${v.thumb}, ${v.thumb}66)`,
        position:'relative', borderBottom:`1px solid ${T.hairlineS}`,
      }}>
        <div style={{ position:'absolute', inset:0, opacity:0.10,
          backgroundImage:'repeating-linear-gradient(45deg, rgba(255,255,255,0.4) 0, rgba(255,255,255,0.4) 1px, transparent 0, transparent 50%)',
          backgroundSize:'7px 7px' }}/>
        <span style={{ position:'absolute', top:8, left:8, fontFamily:"'JetBrains Mono', monospace", fontSize:9, color:'rgba(255,255,255,0.7)', background:'rgba(0,0,0,0.45)', padding:'2px 6px', borderRadius:4, textTransform:'uppercase', letterSpacing:'0.05em' }}>
          {v.kind}
        </span>
        <span style={{ position:'absolute', bottom:8, right:8, fontFamily:"'JetBrains Mono', monospace", fontSize:10, color:'rgba(255,255,255,0.85)', background:'rgba(0,0,0,0.55)', padding:'2px 6px', borderRadius:4 }}>
          {v.duration}
        </span>
        {v.status === 'rendering' && (
          <div style={{ position:'absolute', left:0, right:0, bottom:0, height:2, background:'rgba(0,0,0,0.4)' }}>
            <div style={{ width:'42%', height:'100%', background:T.warning }}/>
          </div>
        )}
      </div>
      <div style={{ padding:'12px 14px 14px' }}>
        <div style={{ fontSize:13, color:T.fg, fontWeight:500, lineHeight:1.4, marginBottom:8, height:36, overflow:'hidden', display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical' }}>
          {v.title}
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:11 }}>
          <span style={{ width:8, height:8, borderRadius:2, background:ch.accent, flexShrink:0 }}/>
          <span style={{ color:T.fgDim, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1 }}>{ch.nickname}</span>
          <StatusDot kind={v.status}/>
        </div>
        <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${T.hairlineS}`, display:'flex', justifyContent:'space-between', alignItems:'center', fontSize:10.5, color:T.muted, fontFamily:"'JetBrains Mono', monospace" }}>
          <span>{v.date}</span>
          {v.views && <span style={{ color:T.fgDim }}><Icon name="eye" size={10} stroke={1.7}/> {v.views}</span>}
        </div>
      </div>
    </Surface>
  );
}

function FrameLibrary({ onNav }) {
  const T = useT();
  const [filter, setFilter] = React.useState('all');
  const [kind, setKind] = React.useState('all');

  const filters = [
    { id:'all', label:'Todos', count: MOCK_VIDEOS.length },
    { id:'uploaded', label:'Subidos', count: MOCK_VIDEOS.filter(v=>v.status==='uploaded').length },
    { id:'rendering', label:'Rendering', count: MOCK_VIDEOS.filter(v=>v.status==='rendering').length },
    { id:'draft', label:'Borradores', count: MOCK_VIDEOS.filter(v=>v.status==='draft').length },
    { id:'failed', label:'Fallidos', count: MOCK_VIDEOS.filter(v=>v.status==='failed').length },
  ];

  const filtered = MOCK_VIDEOS.filter(v => {
    if (filter !== 'all' && v.status !== filter) return false;
    if (kind !== 'all' && v.kind !== kind) return false;
    return true;
  });

  return (
    <MeshBg intensity={0.5}>
      <div style={{ flex:1, overflow:'auto', padding:'28px 28px 40px' }}>
        <div style={{ maxWidth:1440, margin:'0 auto', display:'flex', flexDirection:'column', gap:18 }}>
          <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:14, flexWrap:'wrap' }}>
            <div>
              <Eyebrow style={{ marginBottom:6, display:'block' }}>· biblioteca · todos los vídeos</Eyebrow>
              <Display size={36} weight={600} style={{ color:T.fg }}>Library</Display>
              <p style={{ fontSize:13, color:T.fgDim, margin:'6px 0 0' }}>
                {MOCK_VIDEOS.length} vídeos · {MOCK_VIDEOS.filter(v=>v.kind==='short').length} shorts · {MOCK_VIDEOS.filter(v=>v.kind==='long').length} longs
              </p>
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <Btn variant="default" leading={<Icon name="filter" size={13}/>}>Filtros</Btn>
              <Btn variant="brand" leading={<Icon name="plus" size={13} color="#0B0F14"/>}>Nuevo vídeo</Btn>
            </div>
          </div>

          {/* Filter rail */}
          <Surface style={{ padding:'10px 14px', display:'flex', alignItems:'center', gap:14, flexWrap:'wrap' }}>
            <div style={{ display:'flex', gap:4 }}>
              {filters.map(f => {
                const active = filter === f.id;
                return (
                  <button key={f.id} onClick={() => setFilter(f.id)} style={{
                    padding:'6px 11px', borderRadius:6, border:'1px solid transparent',
                    background: active ? T.surfaceUp : 'transparent',
                    color: active ? T.fg : T.fgDim, fontFamily:'inherit',
                    fontSize:12, cursor:'pointer', display:'flex', alignItems:'center', gap:6,
                  }}>
                    {f.label}
                    <span style={{ fontFamily:"'JetBrains Mono', monospace", fontSize:10, color:T.muted }}>{f.count}</span>
                  </button>
                );
              })}
            </div>
            <div style={{ width:1, height:18, background:T.hairline }}/>
            <div style={{ display:'flex', gap:4 }}>
              {[['all','Todos'],['short','Shorts'],['long','Longs']].map(([id,l]) => {
                const active = kind === id;
                return (
                  <button key={id} onClick={() => setKind(id)} style={{
                    padding:'6px 11px', borderRadius:6, border:`1px solid ${active ? T.primaryR : 'transparent'}`,
                    background: active ? T.primaryS : 'transparent',
                    color: active ? T.primary : T.fgDim, fontFamily:'inherit',
                    fontSize:12, cursor:'pointer',
                  }}>{l}</button>
                );
              })}
            </div>
            <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8, color:T.muted, fontSize:11, fontFamily:"'JetBrains Mono', monospace" }}>
              <Icon name="search" size={12}/>
              <input placeholder="buscar título…" style={{ background:'transparent', border:'none', outline:'none', color:T.fg, fontFamily:'inherit', fontSize:12, width:160 }}/>
            </div>
          </Surface>

          {/* Grid */}
          {filtered.length > 0 ? (
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(220px, 1fr))', gap:14 }}>
              {filtered.map(v => <VideoCard key={v.id} v={v}/>)}
            </div>
          ) : (
            <EmptyState
              kind="library"
              title="No hay vídeos con esos filtros"
              body="Prueba a quitar algún filtro, o genera tu primer vídeo desde el panel de generación."
              cta="Generar mi primer vídeo"
              onCta={() => onNav('generate')}
            />
          )}
        </div>
      </div>
    </MeshBg>
  );
}

// ── EMPTY STATES (ilustradas en SVG, sin assets externos) ───────────────────
function EmptyIllustration({ kind, T }) {
  // SVGs construidos con primitivas; cada uno es ~140×100
  const stroke = T.hairline.replace('rgba(255,255,255,', 'rgba(255,255,255,').replace(/[\d.]+\)$/, '0.18)');
  if (kind === 'library') {
    return (
      <svg width="160" height="120" viewBox="0 0 160 120">
        <defs>
          <linearGradient id="emp1" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor={T.primary} stopOpacity="0.4"/>
            <stop offset="100%" stopColor={T.accent} stopOpacity="0.15"/>
          </linearGradient>
        </defs>
        {/* film strips */}
        <rect x="20" y="20" width="40" height="70" rx="4" fill="none" stroke={T.hairline} strokeWidth="1.2"/>
        <rect x="60" y="35" width="40" height="70" rx="4" fill="url(#emp1)" stroke={T.primaryR} strokeWidth="1.2"/>
        <rect x="100" y="20" width="40" height="70" rx="4" fill="none" stroke={T.hairline} strokeWidth="1.2"/>
        {/* sprocket holes */}
        {[0,1,2,3,4].map(i => (<circle key={`a-${i}`} cx={28+i*8} cy={15} r="1" fill={T.muted}/>))}
        {[0,1,2,3,4].map(i => (<circle key={`b-${i}`} cx={28+i*8} cy={95} r="1" fill={T.muted}/>))}
        {/* play */}
        <path d="M76,55 L88,65 L76,75 Z" fill={T.primary}/>
      </svg>
    );
  }
  if (kind === 'channels') {
    return (
      <svg width="160" height="120" viewBox="0 0 160 120">
        {/* stacked cards */}
        <rect x="30" y="30" width="100" height="60" rx="6" fill={T.surfaceUp} stroke={T.hairline} strokeWidth="1"/>
        <rect x="40" y="40" width="100" height="60" rx="6" fill={T.surface} stroke={T.primaryR} strokeWidth="1.2"/>
        <circle cx="60" cy="58" r="9" fill="none" stroke={T.primary} strokeWidth="1.5"/>
        <path d="M56,58 L58,60 L64,54" fill="none" stroke={T.primary} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <rect x="76" y="52" width="50" height="3" rx="1.5" fill={T.fgDim} opacity="0.5"/>
        <rect x="76" y="60" width="32" height="2.5" rx="1.5" fill={T.muted} opacity="0.5"/>
      </svg>
    );
  }
  if (kind === 'series') {
    return (
      <svg width="160" height="120" viewBox="0 0 160 120">
        {/* episode chain */}
        {[0,1,2,3].map(i => (
          <g key={i}>
            <rect x={20+i*30} y="40" width="22" height="40" rx="3" fill={i===0 ? T.accentS : 'none'} stroke={i===0 ? T.accent : T.hairline} strokeWidth="1.2"/>
            <text x={20+i*30+11} y="64" fontSize="9" fontFamily="JetBrains Mono, monospace" fill={i===0 ? T.accent : T.muted} textAnchor="middle">EP{i+1}</text>
            {i<3 && <line x1={20+i*30+22} y1="60" x2={20+(i+1)*30} y2="60" stroke={T.hairline} strokeDasharray="2 2"/>}
          </g>
        ))}
      </svg>
    );
  }
  if (kind === 'jobs') {
    return (
      <svg width="160" height="120" viewBox="0 0 160 120">
        {/* gauge */}
        <circle cx="80" cy="65" r="32" fill="none" stroke={T.hairline} strokeWidth="2"/>
        <path d="M80,33 a32,32 0 0,1 22.6,9.4" fill="none" stroke={T.primary} strokeWidth="2.5" strokeLinecap="round"/>
        <circle cx="80" cy="65" r="3" fill={T.primary}/>
        <line x1="80" y1="65" x2="98" y2="50" stroke={T.primary} strokeWidth="1.8" strokeLinecap="round"/>
        <text x="80" y="100" fontSize="9" fontFamily="JetBrains Mono, monospace" fill={T.muted} textAnchor="middle">idle</text>
      </svg>
    );
  }
  return null;
}

function EmptyState({ kind='library', title, body, cta, onCta, secondary, onSecondary }) {
  const T = useT();
  return (
    <Surface style={{ padding:'48px 28px', display:'flex', flexDirection:'column', alignItems:'center', textAlign:'center' }}>
      <div style={{ marginBottom:14 }}>
        <EmptyIllustration kind={kind} T={T}/>
      </div>
      <div style={{ fontFamily:"'Sora', sans-serif", fontSize:22, fontWeight:600, color:T.fg, letterSpacing:'-0.025em', marginBottom:8 }}>
        {title}
      </div>
      <p style={{ fontSize:13, color:T.fgDim, lineHeight:1.6, maxWidth:440, margin:'0 0 22px' }}>
        {body}
      </p>
      <div style={{ display:'flex', gap:8 }}>
        {secondary && <Btn variant="default" onClick={onSecondary}>{secondary}</Btn>}
        {cta && <Btn variant="brand" onClick={onCta} leading={<Icon name="sparkles" size={13} color="#0B0F14"/>}>{cta}</Btn>}
      </div>
    </Surface>
  );
}

// ── SERIES FRAME (rack horizontal con timeline) ─────────────────────────────
function FrameSeries({ onNav }) {
  const T = useT();
  return (
    <MeshBg intensity={0.5}>
      <div style={{ flex:1, overflow:'auto', padding:'28px 28px 40px' }}>
        <div style={{ maxWidth:1280, margin:'0 auto', display:'flex', flexDirection:'column', gap:18 }}>
          <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:14, flexWrap:'wrap' }}>
            <div>
              <Eyebrow style={{ marginBottom:6, display:'block' }}>· series · narrativas continuas</Eyebrow>
              <Display size={36} weight={600} style={{ color:T.fg }}>Series</Display>
              <p style={{ fontSize:13, color:T.fgDim, margin:'6px 0 0' }}>
                {MOCK_SERIES.length} series activas · {MOCK_SERIES.reduce((a,s)=>a+s.episodes,0)} episodios totales
              </p>
            </div>
            <Btn variant="brand" leading={<Icon name="plus" size={13} color="#0B0F14"/>}>Nueva serie</Btn>
          </div>

          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {MOCK_SERIES.map(s => {
              const ch = MOCK_CHANNELS.find(c => c.id === s.channel);
              return (
                <Surface key={s.id} hover style={{ padding:0, overflow:'hidden' }}>
                  <div style={{ display:'grid', gridTemplateColumns:'auto 1fr auto', gap:18, padding:'16px 20px', alignItems:'center' }}>
                    <div style={{
                      width:64, height:64, borderRadius:10, flexShrink:0,
                      background:`linear-gradient(135deg, color-mix(in oklch, ${s.accent} 35%, ${T.bg}), ${T.bg})`,
                      border:`1px solid color-mix(in oklch, ${s.accent} 30%, ${T.hairline})`,
                      display:'flex', alignItems:'center', justifyContent:'center', position:'relative', overflow:'hidden',
                    }}>
                      <span style={{ fontFamily:"'Sora', sans-serif", fontSize:24, fontWeight:700, color:s.accent, letterSpacing:'-0.04em' }}>{s.episodes}</span>
                      <span style={{ position:'absolute', bottom:4, right:4, fontFamily:"'JetBrains Mono', monospace", fontSize:8, color:s.accent, letterSpacing:'0.1em' }}>EPS</span>
                    </div>
                    <div style={{ minWidth:0 }}>
                      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                        <span style={{ fontFamily:"'Sora', sans-serif", fontSize:17, fontWeight:600, color:T.fg, letterSpacing:'-0.015em' }}>{s.name}</span>
                        <Chip mono>{ch.nickname}</Chip>
                      </div>
                      <div style={{ fontSize:12, color:T.fgDim, marginBottom:10 }}>
                        Última: <span style={{ color:T.fg }}>{s.last}</span> · Próxima: <span style={{ color:T.primary }}>{s.next}</span>
                      </div>
                      {/* timeline */}
                      <div style={{ display:'flex', gap:3, alignItems:'center' }}>
                        {Array.from({ length: 14 }).map((_, i) => (
                          <div key={i} style={{
                            flex:1, height:6, borderRadius:1.5,
                            background: i < s.episodes ? s.accent : T.hairline,
                            opacity: i < s.episodes ? (0.4 + i / s.episodes * 0.6) : 1,
                          }}/>
                        ))}
                        <span style={{ fontFamily:"'JetBrains Mono', monospace", fontSize:10, color:T.muted, marginLeft:6 }}>{s.episodes}/14</span>
                      </div>
                    </div>
                    <div style={{ display:'flex', gap:6 }}>
                      <Btn variant="default" leading={<Icon name="play" size={11}/>}>Generar próximo</Btn>
                      <Btn variant="ghost" iconOnly><Icon name="chevronR" size={14}/></Btn>
                    </div>
                  </div>
                </Surface>
              );
            })}
          </div>
        </div>
      </div>
    </MeshBg>
  );
}

Object.assign(window, { FrameLibrary, FrameSeries, EmptyState, EmptyIllustration, VideoCard, StatusDot });
