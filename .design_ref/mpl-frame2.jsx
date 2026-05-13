// ─────────────────────────────────────────────────────────────────────────────
// FRAME 2 — GENERAR (panel de control tipo DAW: INPUT · TRANSFORM · OUTPUT)
// ─────────────────────────────────────────────────────────────────────────────

function Knob({ label, value, onChange, min=0, max=100, suffix='', accent }) {
  const T = useT();
  const a = accent || T.primary;
  const pct = ((value - min) / (max - min)) * 100;
  const angle = -135 + (pct / 100) * 270;
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:6, minWidth:64 }}>
      <div style={{
        position:'relative', width:56, height:56, borderRadius:'50%',
        background: T.bg, border:`1px solid ${T.hairline}`, cursor:'pointer',
        boxShadow:`inset 0 1px 0 ${T.hairlineS}, 0 2px 8px rgba(0,0,0,0.3)`,
      }}>
        {/* Arc track */}
        <svg width="56" height="56" style={{ position:'absolute', inset:0 }}>
          <circle cx="28" cy="28" r="22" fill="none" stroke={T.surfaceUp} strokeWidth="2.5" strokeDasharray="103.6 138" strokeDashoffset="34.5" transform="rotate(135 28 28)" strokeLinecap="round"/>
          <circle cx="28" cy="28" r="22" fill="none" stroke={a} strokeWidth="2.5"
            strokeDasharray={`${pct * 1.036} 138`} strokeDashoffset="34.5"
            transform="rotate(135 28 28)" strokeLinecap="round"/>
        </svg>
        {/* Indicator */}
        <div style={{
          position:'absolute', top:'50%', left:'50%', width:2, height:13, background:a, borderRadius:1,
          transform:`translate(-50%, -100%) rotate(${angle}deg)`, transformOrigin:'50% 100%',
        }}/>
      </div>
      <span style={{ fontSize:11.5, fontFamily:"'JetBrains Mono', monospace", color:T.fg, fontVariantNumeric:'tabular-nums' }}>
        {value}{suffix}
      </span>
      <span style={{ fontSize:9.5, fontFamily:"'JetBrains Mono', monospace", color:T.muted, textTransform:'uppercase', letterSpacing:'0.16em' }}>
        {label}
      </span>
    </div>
  );
}

function Field({ label, hint, children, span=1 }) {
  const T = useT();
  return (
    <div style={{ gridColumn:`span ${span}`, display:'flex', flexDirection:'column', gap:6 }}>
      <label style={{ fontSize:11, color:T.fgDim, fontWeight:500, letterSpacing:'-0.01em', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <span>{label}</span>
        {hint && <span style={{ fontFamily:"'JetBrains Mono', monospace", fontSize:10, color:T.muted }}>{hint}</span>}
      </label>
      {children}
    </div>
  );
}

function TextInput({ value, onChange, placeholder, mono, multiline, rows=3 }) {
  const T = useT();
  const baseStyle = {
    width:'100%', background:T.bg, border:`1px solid ${T.hairline}`, borderRadius:8,
    padding:'9px 12px', fontSize:13, color:T.fg, outline:'none',
    fontFamily: mono ? "'JetBrains Mono', monospace" : 'inherit',
    transition:'border-color 120ms',
    resize: multiline ? 'vertical' : 'none',
  };
  return multiline
    ? <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={rows}
        onFocus={e => e.target.style.borderColor=T.primaryR}
        onBlur={e => e.target.style.borderColor=T.hairline}
        style={baseStyle}/>
    : <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        onFocus={e => e.target.style.borderColor=T.primaryR}
        onBlur={e => e.target.style.borderColor=T.hairline}
        style={{ ...baseStyle, height:36 }}/>;
}

function Segmented({ options, value, onChange, accent }) {
  const T = useT();
  const a = accent || T.primary;
  return (
    <div style={{
      display:'inline-flex', background:T.bg, border:`1px solid ${T.hairline}`,
      borderRadius:8, padding:3, gap:2,
    }}>
      {options.map(opt => {
        const v = typeof opt === 'string' ? opt : opt.value;
        const lbl = typeof opt === 'string' ? opt : opt.label;
        const isActive = value === v;
        return (
          <button key={v} onClick={() => onChange(v)} style={{
            padding:'5px 12px', borderRadius:6, border:'none', cursor:'pointer',
            background: isActive ? T.surface : 'transparent',
            color: isActive ? T.fg : T.fgDim,
            fontSize:12, fontWeight: isActive ? 500 : 400, fontFamily:'inherit',
            letterSpacing:'-0.01em',
            boxShadow: isActive ? `inset 0 0 0 1px color-mix(in oklch, ${a} 30%, transparent)` : 'none',
          }}>{lbl}</button>
        );
      })}
    </div>
  );
}

function Switch({ value, onChange, accent }) {
  const T = useT();
  const a = accent || T.primary;
  return (
    <button onClick={() => onChange(!value)} style={{
      width:34, height:20, borderRadius:99, position:'relative', cursor:'pointer',
      background: value ? a : T.surfaceUp, border:`1px solid ${value ? a : T.hairline}`,
      transition:'all 160ms ease', flexShrink:0,
    }}>
      <span style={{
        position:'absolute', top:1, left: value ? 15 : 1, width:16, height:16, borderRadius:'50%',
        background:'#fff', transition:'left 160ms ease', boxShadow:'0 1px 3px rgba(0,0,0,0.4)',
      }}/>
    </button>
  );
}

function ToggleRow({ label, hint, value, onChange, accent }) {
  const T = useT();
  return (
    <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:10, padding:'10px 0' }}>
      <div style={{ flex:1 }}>
        <div style={{ fontSize:13, color:T.fg, fontWeight:500, letterSpacing:'-0.01em' }}>{label}</div>
        {hint && <div style={{ fontSize:11.5, color:T.muted, marginTop:2 }}>{hint}</div>}
      </div>
      <Switch value={value} onChange={onChange} accent={accent}/>
    </div>
  );
}

function ChannelSelect({ value, onChange }) {
  const T = useT();
  const ch = MOCK_CHANNELS.find(c => c.id === value) || MOCK_CHANNELS[0];
  const [open, setOpen] = React.useState(false);
  return (
    <div style={{ position:'relative' }}>
      <button onClick={() => setOpen(!open)} style={{
        width:'100%', height:44, padding:'0 12px',
        background: T.bg, border:`1px solid ${T.hairline}`, borderRadius:8,
        display:'flex', alignItems:'center', gap:10, cursor:'pointer', color:T.fg, fontFamily:'inherit',
      }}>
        <span style={{
          width:26, height:26, borderRadius:6, background:`color-mix(in oklch, ${ch.accent} 16%, transparent)`,
          border:`1px solid color-mix(in oklch, ${ch.accent} 35%, transparent)`,
          color:ch.accent, fontSize:11, fontWeight:700,
          display:'flex', alignItems:'center', justifyContent:'center', fontFamily:"'Sora', sans-serif",
        }}>{ch.nickname[0]}</span>
        <div style={{ flex:1, textAlign:'left', minWidth:0 }}>
          <div style={{ fontSize:13, fontWeight:500, color:T.fg, lineHeight:1.2, letterSpacing:'-0.01em' }}>{ch.nickname}</div>
          <div style={{ fontSize:10.5, color:T.muted, fontFamily:"'JetBrains Mono', monospace" }}>{ch.lang} · {ch.uploads} subidas</div>
        </div>
        <Icon name="chevronD" size={14} color={T.muted}/>
      </button>
      {open && (
        <div onMouseLeave={() => setOpen(false)} style={{
          position:'absolute', top:'calc(100% + 6px)', left:0, right:0, zIndex:30,
          background:T.card, border:`1px solid ${T.hairline}`, borderRadius:10,
          boxShadow:'0 24px 60px -20px rgba(0,0,0,0.55)', padding:6,
        }}>
          {MOCK_CHANNELS.map(c => (
            <button key={c.id} onClick={() => { onChange(c.id); setOpen(false); }} style={{
              display:'flex', alignItems:'center', gap:10, width:'100%', padding:'8px 10px',
              background: c.id === value ? T.surface : 'transparent', border:'none', borderRadius:7,
              cursor:'pointer', color:T.fg, fontFamily:'inherit', textAlign:'left',
            }}>
              <span style={{
                width:24, height:24, borderRadius:6, background:`color-mix(in oklch, ${c.accent} 16%, transparent)`,
                border:`1px solid color-mix(in oklch, ${c.accent} 35%, transparent)`,
                color:c.accent, fontSize:11, fontWeight:700,
                display:'flex', alignItems:'center', justifyContent:'center', fontFamily:"'Sora', sans-serif",
              }}>{c.nickname[0]}</span>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12.5, color:T.fg, fontWeight:500 }}>{c.nickname}</div>
                <div style={{ fontSize:10.5, color:T.muted, fontFamily:"'JetBrains Mono', monospace" }}>{c.niche} · {c.subs}</div>
              </div>
              {c.id === value && <Icon name="check" size={13} color={T.primary}/>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function FrameGenerate({ onNav, onLaunch }) {
  const T = useT();
  const [channel, setChannel] = React.useState('c1');
  const [kind, setKind] = React.useState('short');
  const [topic, setTopic] = React.useState('La supernova del año 1054 que brilló como la Luna');
  const [duration, setDuration] = React.useState(60);
  const [imgSrc, setImgSrc] = React.useState('ai');
  const [series, setSeries] = React.useState('s1');
  const [autoUpload, setAutoUpload] = React.useState(true);
  const [previewEnd, setPreviewEnd] = React.useState(false);
  const [voiceVol, setVoiceVol] = React.useState(85);
  const [musicVol, setMusicVol] = React.useState(35);
  const [pace, setPace] = React.useState(50);
  const [seed, setSeed] = React.useState('1054');

  const ch = MOCK_CHANNELS.find(c => c.id === channel);

  return (
    <MeshBg intensity={0.55}>
      <div style={{ flex:1, overflow:'auto', padding:'24px 28px 40px' }}>
        <div style={{ maxWidth:1440, margin:'0 auto', display:'grid', gridTemplateColumns:'1fr 360px', gap:14 }}>

          {/* MAIN: 3-stage console */}
          <Surface style={{ padding:0, overflow:'hidden' }}>
            {/* Track headers */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', borderBottom:`1px solid ${T.hairline}` }}>
              {[
                ['INPUT',     '01', T.primary, 'Qué quieres contar'],
                ['TRANSFORM', '02', T.accent,  'Cómo se construye'],
                ['OUTPUT',    '03', T.gold,    'Dónde aterriza'],
              ].map(([lbl, n, c, sub], i) => (
                <div key={lbl} style={{
                  padding:'14px 18px', position:'relative',
                  borderRight: i < 2 ? `1px solid ${T.hairline}` : 'none',
                }}>
                  <div style={{ position:'absolute', top:0, left:0, width:'100%', height:2, background:c, opacity:0.7 }}/>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:2 }}>
                    <span style={{ fontFamily:"'JetBrains Mono', monospace", fontSize:10, color:c, fontWeight:600, letterSpacing:'0.16em' }}>· {n}</span>
                    <Eyebrow color={c}>{lbl}</Eyebrow>
                  </div>
                  <div style={{ fontSize:11.5, color:T.muted }}>{sub}</div>
                </div>
              ))}
            </div>

            {/* Track bodies */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr' }}>
              {/* INPUT */}
              <div style={{ padding:'18px 18px 22px', borderRight:`1px solid ${T.hairline}`, display:'flex', flexDirection:'column', gap:14 }}>
                <Field label="Canal">
                  <ChannelSelect value={channel} onChange={setChannel}/>
                </Field>
                <Field label="Formato">
                  <Segmented value={kind} onChange={setKind} accent={T.primary}
                    options={[{value:'short',label:'Short · 9:16'},{value:'long',label:'Long · 16:9'}]}/>
                </Field>
                <Field label="Tema" hint={`${topic.length} chars`}>
                  <TextInput value={topic} onChange={setTopic} placeholder="Tema del vídeo…" multiline rows={3}/>
                </Field>
                <Field label="Serie (opcional)">
                  <Segmented value={series} onChange={setSeries} accent={T.primary}
                    options={[{value:'',label:'Ninguna'}, ...MOCK_SERIES.filter(s => s.channel === channel).map(s => ({value:s.id,label:s.name}))]}/>
                </Field>
              </div>

              {/* TRANSFORM */}
              <div style={{ padding:'18px 18px 22px', borderRight:`1px solid ${T.hairline}`, display:'flex', flexDirection:'column', gap:18 }}>
                <Field label="Duración">
                  <Segmented value={String(duration)} onChange={v => setDuration(Number(v))} accent={T.accent}
                    options={[{value:'60',label:'60s'},{value:'120',label:'120s'},{value:'180',label:'180s'}]}/>
                </Field>
                <Field label="Fuente de imágenes">
                  <Segmented value={imgSrc} onChange={setImgSrc} accent={T.accent}
                    options={[{value:'ai',label:'AI · Nano Banana'},{value:'stock',label:'Stock fotos'}]}/>
                </Field>

                {/* Mixer-style knobs */}
                <div style={{
                  background:T.bg, border:`1px solid ${T.hairline}`, borderRadius:10,
                  padding:'14px 12px', display:'flex', alignItems:'center', justifyContent:'space-around', gap:6,
                }}>
                  <Knob label="VOZ" value={voiceVol} onChange={setVoiceVol} suffix="%" accent={T.accent}/>
                  <Knob label="BSO" value={musicVol} onChange={setMusicVol} suffix="%" accent={T.accent}/>
                  <Knob label="RITMO" value={pace} onChange={setPace} suffix="" accent={T.accent}/>
                </div>

                <Field label="Estilo de imagen" hint="del canal">
                  <div style={{
                    background:T.bg, border:`1px solid ${T.hairline}`, borderRadius:8,
                    padding:'8px 10px', fontSize:11.5, color:T.fgDim, fontFamily:"'JetBrains Mono', monospace",
                    lineHeight:1.5,
                  }}>
                    {ch?.imageStyle || '—'}
                  </div>
                </Field>
              </div>

              {/* OUTPUT */}
              <div style={{ padding:'18px 18px 22px', display:'flex', flexDirection:'column', gap:6 }}>
                <Field label="Seed (reproducible)">
                  <TextInput value={seed} onChange={setSeed} mono placeholder="1054"/>
                </Field>
                <ToggleRow label="Auto-subir a YouTube"
                  hint="Selenium contra YouTube Studio al terminar el render"
                  value={autoUpload} onChange={setAutoUpload} accent={T.gold}/>
                <div style={{ height:1, background:T.hairlineS }}/>
                <ToggleRow label="Preview al final"
                  hint="Muestra modal con el vídeo antes de subir"
                  value={previewEnd} onChange={setPreviewEnd} accent={T.gold}/>
                <div style={{ height:1, background:T.hairlineS }}/>
                <ToggleRow label="Programar para más tarde"
                  hint="Lánzalo a las 14:00 o el siguiente slot del cron"
                  value={false} onChange={()=>{}} accent={T.gold}/>

                <div style={{ marginTop:'auto', paddingTop:18 }}>
                  <Btn variant="brand" size="lg" fullWidth onClick={onLaunch}
                    leading={<Icon name="play" size={14} color="#0B0F14"/>}>
                    Imprimir vídeo
                  </Btn>
                  <div style={{ marginTop:10, display:'flex', alignItems:'center', justifyContent:'space-between', fontSize:11, color:T.muted, fontFamily:"'JetBrains Mono', monospace" }}>
                    <span>ETA ~{Math.round(duration*0.18+90)}s</span>
                    <span>· {kind === 'short' ? '1080×1920' : '1920×1080'} · 30fps</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer signal strip */}
            <div style={{
              display:'flex', alignItems:'center', gap:14, padding:'10px 20px',
              borderTop:`1px solid ${T.hairline}`, background:T.bg,
              fontFamily:"'JetBrains Mono', monospace", fontSize:11, color:T.fgDim,
            }}>
              <span style={{ color:T.success }}>● online</span>
              <span style={{ color:T.muted }}>·</span>
              <span>llm: ollama/llama3.1:8b</span>
              <span style={{ color:T.muted }}>·</span>
              <span>tts: KittenTTS · {ch?.shortVoice}</span>
              <span style={{ color:T.muted }}>·</span>
              <span>img: nano-banana-2</span>
              <span style={{ marginLeft:'auto', color:T.muted }}>headless · firefox profile zhk1gwp4</span>
            </div>
          </Surface>

          {/* SIDE: channel summary + tips */}
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <Surface style={{ padding:'18px 18px', position:'relative', overflow:'hidden' }}>
              <div style={{ position:'absolute', top:0, left:0, right:0, height:3, background:ch?.accent }}/>
              <Eyebrow color={ch?.accent} style={{ marginBottom:10, display:'block' }}>Canal seleccionado</Eyebrow>
              <Display size={22} weight={600} style={{ color:T.fg, marginBottom:4 }}>{ch?.nickname}</Display>
              <div style={{ fontSize:12, color:T.fgDim, marginBottom:14 }}>{ch?.niche} · {ch?.lang}</div>

              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:14 }}>
                {[
                  ['Subs', ch?.subs, T.primary],
                  ['Subidas', ch?.uploads, T.accent],
                ].map(([lbl, val, c]) => (
                  <div key={lbl} style={{ background:T.bg, border:`1px solid ${T.hairline}`, borderRadius:8, padding:'10px 12px' }}>
                    <Eyebrow color={c} style={{ fontSize:9 }}>{lbl}</Eyebrow>
                    <div style={{ fontFamily:"'Sora', sans-serif", fontSize:22, fontWeight:600, color:T.fg, fontVariantNumeric:'tabular-nums', letterSpacing:'-0.02em', marginTop:2 }}>{val}</div>
                  </div>
                ))}
              </div>

              <div style={{ display:'flex', flexDirection:'column', gap:8, fontSize:11.5 }}>
                {[
                  ['Voz Short', ch?.shortVoice],
                  ['Voz Long',  ch?.longVoice],
                  ['Última',    ch?.last + ' · ' + ch?.lastDate],
                ].map(([k,v]) => (
                  <div key={k} style={{ display:'flex', justifyContent:'space-between' }}>
                    <span style={{ color:T.muted, fontFamily:"'JetBrains Mono', monospace", fontSize:10, textTransform:'uppercase', letterSpacing:'0.10em' }}>{k}</span>
                    <span style={{ color:T.fg, fontFamily:"'JetBrains Mono', monospace", fontSize:11 }}>{v}</span>
                  </div>
                ))}
              </div>
            </Surface>

            <Surface style={{ padding:'18px 18px' }}>
              <Eyebrow color={T.muted} style={{ marginBottom:10, display:'block' }}>Tips</Eyebrow>
              <ul style={{ margin:0, padding:'0 0 0 16px', display:'flex', flexDirection:'column', gap:8, fontSize:12, color:T.fgDim, lineHeight:1.5 }}>
                <li><strong style={{ color:T.fg, fontWeight:500 }}>Tema corto y específico</strong> rinde mejor en Shorts (≤ 80 chars).</li>
                <li>Si activas <strong style={{ color:T.fg, fontWeight:500 }}>auto-subir</strong>, el render usa headless por defecto.</li>
                <li>El seed hace el resultado <strong style={{ color:T.fg, fontWeight:500 }}>reproducible</strong>: misma seed → mismas imágenes.</li>
                <li>Pulsa <Chip mono style={{ padding:'1px 5px' }}>⌘ ⏎</Chip> para imprimir desde aquí.</li>
              </ul>
            </Surface>
          </div>
        </div>
      </div>
    </MeshBg>
  );
}

Object.assign(window, { FrameGenerate });
