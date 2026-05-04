
// ─────────────────────────────────────────────────────────────────────────────
// MPL SHARED — tokens, mock data, primitive components
// ─────────────────────────────────────────────────────────────────────────────

// ── TOKENS ──────────────────────────────────────────────────────────────────
const T = {
  // surfaces
  base:    '#0B0B0D',
  surf1:   '#131316',
  surf2:   '#1A1A1F',
  surf3:   '#222228',
  hairline: 'rgba(255,255,255,0.07)',
  hairlineS: 'rgba(255,255,255,0.04)',
  // text
  primary:   '#F5F5F4',
  secondary: '#A8A29E',
  muted:     '#57534E',
  // accent
  amber:     '#E8A24F',
  amberDim:  'rgba(232,162,79,0.12)',
  amberRing: 'rgba(232,162,79,0.35)',
  // status
  success:   '#4ADE80',
  successBg: 'rgba(74,222,128,0.10)',
  warning:   '#F59E0B',
  warningBg: 'rgba(245,158,11,0.10)',
  danger:    '#F87171',
  dangerBg:  'rgba(248,113,113,0.10)',
  info:      '#60A5FA',
  infoBg:    'rgba(96,165,250,0.10)',
};

// ── MOCK DATA ────────────────────────────────────────────────────────────────
const MOCK_RENDERS = [
  { id:'r1', title:'Supernova 1054: Brilló como la Luna', duration:'0:47', status:'uploaded', platform:'yt', aspect:'9:16', thumb:'#3D2A1A', date:'hace 2h', views:'12.4K' },
  { id:'r2', title:'¿Qué es un agujero negro?', duration:'0:52', status:'rendering', platform:'yt', aspect:'9:16', thumb:'#1A2A3D', date:'hace 4h', views:null },
  { id:'r3', title:'La señal Wow: ¿Contacto en 1977?', duration:'0:41', status:'draft', platform:'yt', aspect:'9:16', thumb:'#2A1A3D', date:'hace 1d', views:null },
  { id:'r4', title:'Agujeros Negros: El Secreto', duration:'18:32', status:'uploaded', platform:'yt', aspect:'16:9', thumb:'#1A3D2A', date:'hace 2d', views:'8.2K' },
  { id:'r5', title:'Venus: Secretos del lucero', duration:'0:49', status:'failed', platform:'yt', aspect:'9:16', thumb:'#3D1A2A', date:'hace 3d', views:null },
  { id:'r6', title:'Punto Frío: Huella de otro universo', duration:'0:44', status:'uploaded', platform:'yt', aspect:'9:16', thumb:'#2A3D1A', date:'hace 3d', views:'6.7K' },
];

const MOCK_SCHEDULE = [
  { time:'10:00', account:'Savirox', type:'short', topic:'Materia oscura', status:'pending' },
  { time:'14:00', account:'Savirox', type:'short', topic:'Galaxias lejanas', status:'pending' },
  { time:'20:00', account:'CosmosES', type:'long', topic:'Nebulosas EP.4', status:'pending' },
];

const MOCK_SERIES = [
  { id:'s1', name:'Cosmic Mysteries', slug:'cosmic-mysteries', episodes:12, lastDate:'May 2', nextDate:'May 5', voice:'es-ES-AlvaroNeural', imageStyle:'cinematic deep space, volumetric light', color:'#3D2A1A' },
  { id:'s2', name:'Forbidden Physics', slug:'forbidden-physics', episodes:7, lastDate:'Apr 28', nextDate:'May 6', voice:'es-ES-AlvaroNeural', imageStyle:'abstract physics, dark lab aesthetic', color:'#1A2A3D' },
  { id:'s3', name:'Lost Civilizations', slug:'lost-civilizations', episodes:5, lastDate:'Apr 25', nextDate:'May 8', voice:'es-MX-JorgeNeural', imageStyle:'ancient ruins, dramatic sky, golden hour', color:'#2A1A3D' },
  { id:'s4', name:'Quantum Horizons', slug:'quantum-horizons', episodes:3, lastDate:'Apr 20', nextDate:'May 10', voice:'es-ES-AlvaroNeural', imageStyle:'quantum visualization, neon particles', color:'#1A3D2A' },
];

const MOCK_ACCOUNTS = [
  { id:'a1', nickname:'Savirox', platform:'youtube', niche:'Universo / Cosmos', lang:'es-ES', flag:'🇪🇸', shortVoice:'Carlos', longVoice:'Bruno', imageStyle:'cinematic deep space, award-winning photography', profileLinked:true, uploads:16 },
  { id:'a2', nickname:'CosmosES', platform:'youtube', niche:'Astrofísica', lang:'es-MX', flag:'🇲🇽', shortVoice:'Dalia', longVoice:'Jorge', imageStyle:'minimalist scientific diagrams, dark bg', profileLinked:true, uploads:8 },
  { id:'a3', nickname:'SpaceBot_X', platform:'twitter', niche:'Space Facts', lang:'en-US', flag:'🇺🇸', shortVoice:'Jasper', longVoice:'—', imageStyle:'photorealistic space photography', profileLinked:true, uploads:42 },
  { id:'a4', nickname:'AffiliateES', platform:'twitter', niche:'Tech Products', lang:'es-ES', flag:'🇪🇸', shortVoice:'Carlos', longVoice:'—', imageStyle:'clean product photography, white bg', profileLinked:false, uploads:0 },
];

const MOCK_IMAGES = [
  { id:'i1', prompt:'supernova explosion, cinematic deep space, volumetric light rays, photorealistic, 8k', locked:false, color:'hsl(220,25%,12%)' },
  { id:'i2', prompt:'cosmic dust cloud collapsing, blue-white stellar nursery, award-winning astrophotography', locked:true, color:'hsl(200,30%,10%)' },
  { id:'i3', prompt:'neutron star surface, extreme close-up, plasma jets, dramatic lighting, hyperrealistic', locked:false, color:'hsl(240,20%,11%)' },
  { id:'i4', prompt:'earth as seen from 1054 AD, night sky with blinding supernova visible at daylight', locked:false, color:'hsl(210,35%,9%)' },
];

const MOCK_SCRIPT = [
  { id:'sc1', text:'En el año 1054, algo imposible iluminó el cielo.', active:false },
  { id:'sc2', text:'Una estrella explotó con la fuerza de mil millones de soles.', active:true },
  { id:'sc3', text:'Y durante 23 días seguidos, brilló tanto como la Luna llena.', active:false },
  { id:'sc4', text:'Los astrónomos chinos la llamaron "estrella invitada".', active:false },
  { id:'sc5', text:'Sus restos, hoy forman la Nebulosa del Cangrejo.', active:false },
];

const MOCK_LOG = [
  { ts:'10:42:01', stage:'script',  text:'Generating script for topic: La supernova del año 1054...', type:'info' },
  { ts:'10:42:03', stage:'script',  text:'Script generated — 5 sentences, ~47s estimated duration', type:'success' },
  { ts:'10:42:03', stage:'tts',     text:'Initializing Edge-TTS · es-ES-AlvaroNeural', type:'info' },
  { ts:'10:42:07', stage:'tts',     text:'Audio rendered — 8748216d.wav (2.1 MB)', type:'success' },
  { ts:'10:42:07', stage:'images',  text:'Queuing 4 image prompts → Nano Banana 2', type:'info' },
  { ts:'10:42:09', stage:'images',  text:'Image 1/4 generated ✓', type:'success' },
  { ts:'10:42:11', stage:'images',  text:'Image 2/4 generated ✓', type:'success' },
  { ts:'10:42:13', stage:'images',  text:'Image 3/4 generated ✓', type:'success' },
  { ts:'10:42:15', stage:'images',  text:'Image 4/4 generated ✓', type:'success' },
  { ts:'10:42:15', stage:'moviepy', text:'Compositing video — 1080×1920, 30fps', type:'info' },
  { ts:'10:42:18', stage:'moviepy', text:'Subtitles: running Whisper (base) on audio...', type:'info' },
  { ts:'10:42:22', stage:'moviepy', text:'Subtitles: 12 chunks generated', type:'success' },
  { ts:'10:42:22', stage:'moviepy', text:'Applying Ken Burns effect to 4 images', type:'info' },
  { ts:'10:42:28', stage:'moviepy', text:'Video export complete — 54209257.mp4 (18.3 MB)', type:'success' },
  { ts:'10:42:28', stage:'upload',  text:'Opening Firefox profile · zhk1gwp4.default-release', type:'info' },
  { ts:'10:42:31', stage:'upload',  text:'Navigating to YouTube Studio...', type:'info' },
];

const MOCK_LIBRARY = [
  ...MOCK_RENDERS,
  { id:'r7', title:'Saturno: El Señor de los Anillos', duration:'0:38', status:'uploaded', platform:'yt', aspect:'9:16', thumb:'#3D3A1A', date:'hace 4d', views:'22.1K' },
  { id:'r8', title:'Oumuamua: La verdad oculta', duration:'0:51', status:'uploaded', platform:'yt', aspect:'9:16', thumb:'#1A3A3D', date:'hace 5d', views:'5.3K' },
  { id:'r9', title:'Cosmic Mysteries EP.12 — Nebulosas', duration:'17:44', status:'uploaded', platform:'yt', aspect:'16:9', thumb:'#2A3D3D', date:'hace 1sem', views:'31.8K' },
  { id:'r10', title:'Marte: Terraformar imposible?', duration:'0:43', status:'rendering', platform:'yt', aspect:'9:16', thumb:'#3D1A1A', date:'hace 6d', views:null },
];

// ── PRIMITIVE COMPONENTS ─────────────────────────────────────────────────────

function StatusPill({ status, size = 'sm' }) {
  const map = {
    uploaded:  { label:'Uploaded',  color: T.success, bg: T.successBg },
    rendering: { label:'Rendering', color: T.warning, bg: T.warningBg },
    draft:     { label:'Draft',     color: T.secondary, bg: 'rgba(168,162,158,0.10)' },
    failed:    { label:'Failed',    color: T.danger, bg: T.dangerBg },
    pending:   { label:'Pending',   color: T.info, bg: T.infoBg },
    uploading: { label:'Uploading', color: T.amber, bg: T.amberDim },
  };
  const s = map[status] || map.draft;
  const pad = size === 'xs' ? '2px 7px' : '3px 9px';
  const fs = size === 'xs' ? 10 : 11;
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', gap:5,
      background: s.bg, color: s.color,
      borderRadius:99, padding: pad, fontSize: fs, fontWeight:500,
      letterSpacing:'0.01em', border: `1px solid ${s.color}22`,
    }}>
      <span style={{ width:5, height:5, borderRadius:'50%', background: s.color, flexShrink:0 }} />
      {s.label}
    </span>
  );
}

function PlatformGlyph({ platform, size=16 }) {
  if (platform === 'youtube' || platform === 'yt') {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="6" fill="#FF0000" opacity="0.15"/>
        <path d="M19.6 7.4a2.5 2.5 0 00-1.76-1.77C16.4 5.25 12 5.25 12 5.25s-4.4 0-5.84.38A2.5 2.5 0 004.4 7.4C4 8.85 4 12 4 12s0 3.15.4 4.6a2.5 2.5 0 001.76 1.77C7.6 18.75 12 18.75 12 18.75s4.4 0 5.84-.38a2.5 2.5 0 001.76-1.77C20 15.15 20 12 20 12s0-3.15-.4-4.6z" fill="#FF4444" opacity="0.9"/>
        <path d="M10 15.5l5-3.5-5-3.5v7z" fill="white"/>
      </svg>
    );
  }
  if (platform === 'twitter') {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="6" fill="rgba(255,255,255,0.06)"/>
        <path d="M4 4l6.5 9L4 20h2l5.3-6.1L16 20h4l-6.8-9.3L19.5 4h-2l-4.9 5.6L8 4H4z" fill={T.secondary}/>
      </svg>
    );
  }
  return null;
}

function Chip({ children, color, style }) {
  return (
    <span style={{
      display:'inline-flex', alignItems:'center',
      background: color ? `${color}15` : T.surf3,
      border: `1px solid ${color ? `${color}30` : T.hairline}`,
      color: color || T.secondary,
      borderRadius:6, padding:'2px 8px', fontSize:11, fontWeight:500,
      fontFamily:'Geist Mono, JetBrains Mono, monospace', letterSpacing:'0.01em',
      ...style,
    }}>{children}</span>
  );
}

function NavIcon({ d, size=20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d={d}/>
    </svg>
  );
}

// Lucide-style icon paths
const ICONS = {
  home:     'M3 9.5L12 3l9 6.5V21a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z M9 22V12h6v10',
  film:     'M2 8h20M2 16h20M6 2v4M18 2v4M6 18v4M18 18v4M2 6a2 2 0 012-2h16a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V6z',
  layers:   'M2 12l10-7 10 7-10 7-10-7z M2 17l10 7 10-7 M2 7l10 7 10-7',
  calendar: 'M3 6a2 2 0 012-2h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V6zM3 10h18M8 2v4M16 2v4',
  users:    'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2 M23 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75',
  settings: 'M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z',
  plus:     'M12 5v14M5 12h14',
  chevronL: 'M15 18l-6-6 6-6',
  chevronR: 'M9 18l6-6-6-6',
  chevronD: 'M6 9l6 6 6-6',
  search:   'M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z',
  refresh:  'M23 4v6h-6 M1 20v-6h6 M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15',
  lock:     'M19 11H5a2 2 0 00-2 2v7a2 2 0 002 2h14a2 2 0 002-2v-7a2 2 0 00-2-2zM7 11V7a5 5 0 0110 0v4',
  download: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M7 10l5 5 5-5 M12 15V3',
  image:    'M21 19V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2z M8.5 10a1.5 1.5 0 100-3 1.5 1.5 0 000 3z M21 15l-5-5L5 21',
  mic:      'M12 2a3 3 0 013 3v7a3 3 0 01-6 0V5a3 3 0 013-3z M19 10v2a7 7 0 01-14 0v-2 M12 19v4 M8 23h8',
  play:     'M5 3l14 9-14 9V3z',
  check:    'M20 6L9 17l-5-5',
  x:        'M18 6L6 18M6 6l12 12',
  alertC:   'M12 9v4 M12 17h.01 M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z',
  edit:     'M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7 M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z',
  upload:   'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M17 8l-5-5-5 5 M12 3v12',
  globe:    'M12 2a10 10 0 100 20A10 10 0 0012 2z M2 12h20 M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20',
  cpu:      'M9 3H5a2 2 0 00-2 2v4m6-6h6m-6 0v18m6-18h4a2 2 0 012 2v4m-6-6v18M3 9h18M3 15h18m-9 6V9',
  db:       'M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7',
  music:    'M9 18V5l12-2v13 M9 9l12-2 M6 21a3 3 0 100-6 3 3 0 000 6z M18 19a3 3 0 100-6 3 3 0 000 6z',
  eye:      'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 12a3 3 0 100-6 3 3 0 000 6z',
  trash:    'M3 6h18 M8 6V4h8v2 M19 6l-1 14H6L5 6',
  filter:   'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
  hash:     'M4 9h16 M4 15h16 M10 3l-2 18 M16 3l-2 18',
  zap:      'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  external: 'M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6 M15 3h6v6 M10 14L21 3',
};

function Icon({ name, size=18, color='currentColor', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink:0, ...style }}>
      <path d={ICONS[name] || ''}/>
    </svg>
  );
}

// ── LAYOUT PRIMITIVES ────────────────────────────────────────────────────────

function Sidebar({ activeFrame, onNav }) {
  const [expanded, setExpanded] = React.useState(true);

  const navItems = [
    { id:'home', label:'Studio', icon:'home' },
    { id:'library', label:'Library', icon:'film' },
    { id:'series', label:'Series', icon:'layers' },
    { id:'schedule', label:'Schedule', icon:'calendar' },
    { id:'accounts', label:'Accounts', icon:'users' },
    { id:'settings', label:'Settings', icon:'settings' },
  ];

  const w = expanded ? 240 : 64;

  return (
    <div style={{
      width: w, minWidth: w, height:'100%', display:'flex', flexDirection:'column',
      background: T.surf1, borderRight:`1px solid ${T.hairline}`,
      transition:'width 180ms cubic-bezier(0.4,0,0.2,1)',
      overflow:'hidden', flexShrink:0, position:'relative', zIndex:10,
    }}>
      {/* Logo */}
      <div style={{
        height:56, display:'flex', alignItems:'center', gap:10,
        padding: expanded ? '0 16px' : '0', justifyContent: expanded ? 'flex-start' : 'center',
        borderBottom:`1px solid ${T.hairline}`, flexShrink:0,
      }}>
        <div style={{
          width:28, height:28, borderRadius:8, background:`linear-gradient(135deg, ${T.amber} 0%, #C47A28 100%)`,
          display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 3l14 9-14 9V3z"/>
          </svg>
        </div>
        {expanded && (
          <span style={{ fontSize:13, fontWeight:600, color: T.primary, letterSpacing:'-0.02em', whiteSpace:'nowrap' }}>
            MoneyPrinter
          </span>
        )}
      </div>

      {/* Nav */}
      <nav style={{ flex:1, padding:'8px 8px', display:'flex', flexDirection:'column', gap:2 }}>
        {navItems.map(item => {
          const active = activeFrame === item.id;
          return (
            <button key={item.id} onClick={() => onNav(item.id)} style={{
              display:'flex', alignItems:'center', gap:10,
              padding: expanded ? '8px 10px' : '8px 0',
              justifyContent: expanded ? 'flex-start' : 'center',
              borderRadius:8, border:'none', cursor:'pointer',
              background: active ? T.amberDim : 'transparent',
              color: active ? T.amber : T.secondary,
              transition:'all 120ms ease', width:'100%',
              position:'relative',
            }}
              onMouseEnter={e => { if(!active) { e.currentTarget.style.background=T.surf2; e.currentTarget.style.color=T.primary; } }}
              onMouseLeave={e => { if(!active) { e.currentTarget.style.background='transparent'; e.currentTarget.style.color=T.secondary; } }}
            >
              {active && <span style={{
                position:'absolute', left:0, top:'50%', transform:'translateY(-50%)',
                width:2, height:16, borderRadius:'0 2px 2px 0',
                background: T.amber,
              }}/>}
              <Icon name={item.icon} size={18} color="currentColor"/>
              {expanded && <span style={{ fontSize:13, fontWeight: active ? 500 : 400, letterSpacing:'-0.01em', whiteSpace:'nowrap' }}>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Account switcher */}
      {expanded && (
        <div style={{
          padding:'12px 12px', borderTop:`1px solid ${T.hairline}`,
          display:'flex', alignItems:'center', gap:8,
        }}>
          <div style={{
            width:28, height:28, borderRadius:'50%',
            background:`linear-gradient(135deg, ${T.amber} 0%, #C47A28 100%)`,
            display:'flex', alignItems:'center', justifyContent:'center',
            fontSize:10, fontWeight:700, color:'white', flexShrink:0,
          }}>DL</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:500, color: T.primary, lineHeight:1.3 }}>Daniel L.</div>
            <div style={{ fontSize:11, color: T.muted, lineHeight:1.3 }}>Savirox</div>
          </div>
          <Icon name="chevronD" size={14} color={T.muted}/>
        </div>
      )}
      {!expanded && (
        <div style={{ padding:'12px 0', borderTop:`1px solid ${T.hairline}`, display:'flex', justifyContent:'center' }}>
          <div style={{
            width:28, height:28, borderRadius:'50%',
            background:`linear-gradient(135deg, ${T.amber} 0%, #C47A28 100%)`,
            display:'flex', alignItems:'center', justifyContent:'center',
            fontSize:10, fontWeight:700, color:'white',
          }}>DL</div>
        </div>
      )}

      {/* Toggle */}
      <button onClick={() => setExpanded(!expanded)} style={{
        height:36, display:'flex', alignItems:'center', justifyContent:'center',
        borderTop:`1px solid ${T.hairline}`, background:'transparent', border:'none',
        color: T.muted, cursor:'pointer', transition:'color 120ms',
      }}
        onMouseEnter={e => e.currentTarget.style.color=T.secondary}
        onMouseLeave={e => e.currentTarget.style.color=T.muted}
      >
        <Icon name={expanded ? 'chevronL' : 'chevronR'} size={14} color="currentColor"/>
      </button>
    </div>
  );
}

function TopBar({ title, onNew, renderQueue=0 }) {
  const [llmOpen, setLlmOpen] = React.useState(false);
  return (
    <div style={{
      height:56, display:'flex', alignItems:'center', gap:12, padding:'0 24px',
      borderBottom:`1px solid ${T.hairline}`,
      background: T.surf1, flexShrink:0, position:'relative',
    }}>
      <span style={{ fontSize:14, fontWeight:500, color: T.primary, flex:1, letterSpacing:'-0.01em' }}>{title}</span>

      {/* LLM chip */}
      <div onClick={() => setLlmOpen(!llmOpen)} style={{
        display:'flex', alignItems:'center', gap:6,
        background: T.surf2, border:`1px solid ${T.hairline}`,
        borderRadius:8, padding:'5px 10px', cursor:'pointer', position:'relative',
        transition:'border-color 120ms',
      }}
        onMouseEnter={e => e.currentTarget.style.borderColor=T.amberRing}
        onMouseLeave={e => e.currentTarget.style.borderColor=T.hairline}
      >
        <span style={{ width:6, height:6, borderRadius:'50%', background: T.success }} />
        <span style={{ fontSize:12, color: T.secondary, fontFamily:'Geist Mono, monospace' }}>
          Ollama
        </span>
        <span style={{ fontSize:12, color: T.muted }}>·</span>
        <span style={{ fontSize:12, color: T.primary, fontFamily:'Geist Mono, monospace' }}>
          deepseek-v4-pro
        </span>
        <Icon name="chevronD" size={12} color={T.muted}/>
        {llmOpen && (
          <div style={{
            position:'absolute', top:'calc(100% + 6px)', right:0, width:220,
            background: T.surf2, border:`1px solid ${T.hairline}`,
            borderRadius:10, padding:8, zIndex:100,
            boxShadow:'0 16px 40px rgba(0,0,0,0.5)',
          }}>
            {['Ollama · deepseek-v4-pro','Gemini · gemini-2.5-flash','Pollinations · openai'].map((m,i) => (
              <div key={i} style={{
                padding:'6px 10px', borderRadius:6, fontSize:12,
                fontFamily:'Geist Mono, monospace', color: i===0 ? T.amber : T.secondary,
                background: i===0 ? T.amberDim : 'transparent', cursor:'pointer',
                display:'flex', alignItems:'center', gap:6,
              }}>
                {i===0 && <span style={{width:5,height:5,borderRadius:'50%',background:T.success}}/>}
                {m}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Render queue */}
      {renderQueue > 0 && (
        <div style={{
          display:'flex', alignItems:'center', gap:6,
          background: T.warningBg, border:`1px solid ${T.warning}33`,
          borderRadius:8, padding:'5px 10px',
        }}>
          <span style={{ width:6, height:6, borderRadius:'50%', background: T.warning }} />
          <span style={{ fontSize:12, color: T.warning }}>{renderQueue} rendering</span>
        </div>
      )}

      {/* New button */}
      <button onClick={onNew} style={{
        display:'flex', alignItems:'center', gap:6,
        background: T.amber, border:'none', borderRadius:8,
        padding:'7px 14px', cursor:'pointer', color:'#0B0B0D',
        fontSize:13, fontWeight:600, letterSpacing:'-0.01em',
        transition:'opacity 120ms',
      }}
        onMouseEnter={e => e.currentTarget.style.opacity='0.88'}
        onMouseLeave={e => e.currentTarget.style.opacity='1'}
      >
        <Icon name="plus" size={14} color="#0B0B0D"/>
        New
      </button>

      {/* Avatar */}
      <div style={{
        width:30, height:30, borderRadius:'50%',
        background:`linear-gradient(135deg, ${T.amber}, #C47A28)`,
        display:'flex', alignItems:'center', justifyContent:'center',
        fontSize:11, fontWeight:700, color:'#0B0B0D', cursor:'pointer',
      }}>DL</div>
    </div>
  );
}

function VideoTile({ render, size='md' }) {
  const isVert = render.aspect === '9:16';
  const dims = {
    sm: isVert ? { w:70, h:124 } : { w:160, h:90 },
    md: isVert ? { w:90, h:160 } : { w:200, h:112 },
    lg: isVert ? { w:110, h:196 } : { w:240, h:135 },
  }[size];

  return (
    <div style={{ flexShrink:0, display:'flex', flexDirection:'column', gap:6, cursor:'pointer' }}>
      <div style={{
        width: dims.w, height: dims.h, borderRadius:8,
        background: `linear-gradient(135deg, ${render.thumb}, ${render.thumb}88)`,
        border:`1px solid ${T.hairline}`,
        position:'relative', overflow:'hidden',
        display:'flex', alignItems:'center', justifyContent:'center',
      }}>
        {/* Striped placeholder */}
        <div style={{
          position:'absolute', inset:0, opacity:0.15,
          backgroundImage:'repeating-linear-gradient(45deg, rgba(255,255,255,0.3) 0, rgba(255,255,255,0.3) 1px, transparent 0, transparent 50%)',
          backgroundSize:'6px 6px',
        }}/>
        <div style={{ position:'absolute', bottom:6, left:6, right:6, display:'flex', justifyContent:'space-between', alignItems:'flex-end' }}>
          <StatusPill status={render.status} size="xs"/>
          <PlatformGlyph platform={render.platform} size={16}/>
        </div>
        <span style={{ fontFamily:'Geist Mono, monospace', fontSize:9, color:'rgba(255,255,255,0.3)', textAlign:'center', padding:4 }}>
          {isVert ? '9:16' : '16:9'}
        </span>
      </div>
      {size !== 'sm' && (
        <div style={{ width: dims.w }}>
          <div style={{ fontSize:11, color: T.primary, fontWeight:500, lineHeight:1.4, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {render.title}
          </div>
          <div style={{ fontSize:10, color: T.muted, marginTop:2, fontFamily:'Geist Mono, monospace', display:'flex', gap:6 }}>
            <span>{render.duration}</span>
            {render.views && <span style={{color: T.success}}>{render.views}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function Stepper({ steps, current, onChange }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:0, padding:'0 24px', height:52, borderBottom:`1px solid ${T.hairline}`, flexShrink:0, overflowX:'auto' }}>
      {steps.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <React.Fragment key={step}>
            <button onClick={() => done && onChange(i)} style={{
              display:'flex', alignItems:'center', gap:8, padding:'6px 10px',
              borderRadius:8, border: active ? `1px solid ${T.amberRing}` : '1px solid transparent',
              background: active ? T.amberDim : 'transparent',
              color: active ? T.amber : done ? T.primary : T.muted,
              cursor: done ? 'pointer' : 'default', flexShrink:0,
              transition:'all 120ms',
            }}>
              <div style={{
                width:22, height:22, borderRadius:'50%',
                background: active ? T.amber : done ? T.successBg : T.surf2,
                border: `1px solid ${active ? T.amber : done ? T.success+'44' : T.hairline}`,
                display:'flex', alignItems:'center', justifyContent:'center',
                fontSize:11, fontWeight:600,
                color: active ? '#0B0B0D' : done ? T.success : T.muted,
                flexShrink:0,
              }}>
                {done ? '✓' : i+1}
              </div>
              <span style={{ fontSize:12, fontWeight: active ? 600 : 400, whiteSpace:'nowrap' }}>{step}</span>
            </button>
            {i < steps.length-1 && (
              <div style={{ width:20, height:1, background: T.hairline, flexShrink:0 }}/>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Export everything to window
Object.assign(window, {
  T, MOCK_RENDERS, MOCK_SCHEDULE, MOCK_SERIES, MOCK_ACCOUNTS, MOCK_IMAGES, MOCK_SCRIPT, MOCK_LOG, MOCK_LIBRARY,
  StatusPill, PlatformGlyph, Chip, Icon, ICONS,
  Sidebar, TopBar, VideoTile, Stepper,
});
