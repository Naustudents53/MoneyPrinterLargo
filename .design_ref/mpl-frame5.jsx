// ─────────────────────────────────────────────────────────────────────────────
// FRAME 5 — CONFIGURACIÓN (config.json visual editor)
// ─────────────────────────────────────────────────────────────────────────────

function ConfigField({ label, type='text', value, onChange, placeholder, hint, secret, onToggleSecret, options }) {
  const T = useT();
  if (type === 'switch') {
    return (
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:14, padding:'12px 0', borderBottom:`1px solid ${T.hairlineS}` }}>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:13, color:T.fg, fontWeight:500 }}>{label}</div>
          {hint && <div style={{ fontSize:11.5, color:T.muted, marginTop:2 }}>{hint}</div>}
        </div>
        <Switch value={value} onChange={onChange}/>
      </div>
    );
  }
  if (type === 'select') {
    return (
      <div style={{ padding:'12px 0', borderBottom:`1px solid ${T.hairlineS}`, display:'grid', gridTemplateColumns:'200px 1fr', gap:18, alignItems:'center' }}>
        <div>
          <div style={{ fontSize:13, color:T.fg, fontWeight:500 }}>{label}</div>
          {hint && <div style={{ fontSize:11, color:T.muted, marginTop:2 }}>{hint}</div>}
        </div>
        <select value={value} onChange={e => onChange(e.target.value)} style={{
          width:'100%', height:34, padding:'0 12px', background:T.bg,
          border:`1px solid ${T.hairline}`, borderRadius:8, color:T.fg,
          fontFamily:"'JetBrains Mono', monospace", fontSize:12, outline:'none',
        }}>
          {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    );
  }
  return (
    <div style={{ padding:'12px 0', borderBottom:`1px solid ${T.hairlineS}`, display:'grid', gridTemplateColumns:'200px 1fr', gap:18, alignItems:'center' }}>
      <div>
        <div style={{ fontSize:13, color:T.fg, fontWeight:500 }}>{label}</div>
        {hint && <div style={{ fontSize:11, color:T.muted, marginTop:2 }}>{hint}</div>}
      </div>
      <div style={{ display:'flex', gap:6, position:'relative' }}>
        <input type={secret ? 'password' : 'text'} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{
          flex:1, height:34, padding:'0 12px', background:T.bg,
          border:`1px solid ${T.hairline}`, borderRadius:8, color:T.fg,
          fontFamily:"'JetBrains Mono', monospace", fontSize:12, outline:'none',
        }}
          onFocus={e => e.target.style.borderColor=T.primaryR}
          onBlur={e => e.target.style.borderColor=T.hairline}/>
        {onToggleSecret && (
          <button onClick={onToggleSecret} style={{
            width:34, height:34, background:T.bg, border:`1px solid ${T.hairline}`, borderRadius:8,
            display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', color:T.fgDim,
          }}><Icon name={secret ? 'eye' : 'lock'} size={13}/></button>
        )}
      </div>
    </div>
  );
}

const CONFIG_SECTIONS = [
  { id:'core',    label:'Core',    icon:'settings', desc:'Workspace, scratch, defaults' },
  { id:'llm',     label:'LLM',     icon:'sparkles', desc:'Provider, model, temp' },
  { id:'image',   label:'Imagen',  icon:'image',    desc:'Backend, resolución, estilo' },
  { id:'audio',   label:'Audio',   icon:'mic',      desc:'TTS, voces, BSO' },
  { id:'twitter', label:'Twitter', icon:'twitter',  desc:'Cuenta, headless, perfil FF' },
  { id:'cron',    label:'Cron',    icon:'clock',    desc:'Programación' },
];

const CONFIG_FIELDS = {
  core: [
    { k:'workspace',     label:'Workspace path',  hint:'Ruta donde MPL guarda outputs', val:'~/MoneyPrinterLargo' },
    { k:'scratch',       label:'Scratch dir',     hint:'.mp/ — vídeos, imágenes y audio temporal', val:'.mp/' },
    { k:'aspect',        label:'Aspect ratio',    type:'select', options:['9:16 (Short)','16:9 (Long)','1:1 (Square)'], val:'9:16 (Short)' },
    { k:'auto_clean',    label:'Auto-clean scratch', type:'switch', val:true, hint:'Borra archivos > 7 días automáticamente' },
    { k:'analytics',     label:'Telemetría anónima', type:'switch', val:false, hint:'Solo conteos de jobs · sin contenido' },
  ],
  llm: [
    { k:'provider',  label:'Provider',     type:'select', options:['Ollama','Gemini','Pollinations'], val:'Ollama' },
    { k:'model',     label:'Modelo',       hint:'Identificador exacto', val:'llama3.1:8b' },
    { k:'host',      label:'Host',         val:'http://localhost:11434' },
    { k:'api_key',   label:'API key',      secret:true, val:'sk-•••••••••••', hint:'Solo si provider lo requiere' },
    { k:'temp',      label:'Temperatura',  val:'0.7' },
    { k:'max_tokens',label:'Max tokens',   val:'2048' },
  ],
  image: [
    { k:'backend',    label:'Backend',     type:'select', options:['Nano Banana 2','SDXL local','Photo stock'], val:'Nano Banana 2' },
    { k:'res',        label:'Resolución',  type:'select', options:['1080×1920','1920×1080','1024×1024'], val:'1080×1920' },
    { k:'style',      label:'Estilo global',hint:'Sufijo añadido a cada prompt', val:'cinematic deep space, 8k, photorealistic' },
    { k:'neg',        label:'Negative prompt', val:'blurry, watermark, text, low quality' },
  ],
  audio: [
    { k:'tts_engine',  label:'Motor TTS',   type:'select', options:['KittenTTS','Edge-TTS','Bark'], val:'KittenTTS' },
    { k:'short_voice', label:'Voz Short',   val:'es-ES-AlvaroNeural' },
    { k:'long_voice',  label:'Voz Long',    val:'es-ES-AlvaroNeural' },
    { k:'music_dir',   label:'BSO directorio', val:'./Songs/' },
    { k:'music_vol',   label:'Volumen BSO', val:'0.35' },
    { k:'voice_vol',   label:'Volumen voz', val:'0.85' },
  ],
  twitter: [
    { k:'enabled',    label:'Twitter habilitado', type:'switch', val:false },
    { k:'profile',    label:'Perfil Firefox', val:'zhk1gwp4.default-release' },
    { k:'headless',   label:'Headless mode', type:'switch', val:true },
    { k:'rate_limit', label:'Rate limit (tweets/h)', val:'10' },
  ],
  cron: [
    { k:'enabled', label:'Cron habilitado', type:'switch', val:true },
    { k:'slots',   label:'Slots diarios',   val:'10:00, 14:00, 20:00' },
  ],
};

function FrameSettings() {
  const T = useT();
  const [section, setSection] = React.useState('core');
  const [showSecrets, setShowSecrets] = React.useState(false);
  const [values, setValues] = React.useState(() => {
    const v = {};
    Object.entries(CONFIG_FIELDS).forEach(([sec, fields]) => {
      fields.forEach(f => v[`${sec}.${f.k}`] = f.val);
    });
    return v;
  });

  const setVal = (k, v) => setValues(prev => ({ ...prev, [k]: v }));
  const fields = CONFIG_FIELDS[section];
  const cur = CONFIG_SECTIONS.find(s => s.id === section);

  return (
    <MeshBg intensity={0.4}>
      <div style={{ flex:1, overflow:'auto', padding:'28px 28px 40px' }}>
        <div style={{ maxWidth:1280, margin:'0 auto', display:'flex', flexDirection:'column', gap:20 }}>
          <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:14, flexWrap:'wrap' }}>
            <div>
              <Eyebrow style={{ marginBottom:6, display:'block' }}>· config.json · editor visual</Eyebrow>
              <Display size={36} weight={600} style={{ color:T.fg }}>Configuración</Display>
              <p style={{ fontSize:13, color:T.fgDim, margin:'6px 0 0' }}>
                ~/MoneyPrinterLargo/config.json · {Object.keys(values).length} campos
              </p>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <ToggleRow label="Mostrar secrets" hint="" value={showSecrets} onChange={setShowSecrets}/>
              <Btn variant="default" leading={<Icon name="refresh" size={13}/>}>Recargar</Btn>
              <Btn variant="brand" leading={<Icon name="check" size={13} color="#0B0F14"/>}>Guardar cambios</Btn>
            </div>
          </div>

          {/* Two-column: section nav + field editor */}
          <Surface style={{ padding:0, overflow:'hidden' }}>
            <div style={{ display:'grid', gridTemplateColumns:'240px 1fr', minHeight:540 }}>
              {/* Left: sections */}
              <div style={{ borderRight:`1px solid ${T.hairline}`, padding:'14px 10px', display:'flex', flexDirection:'column', gap:2, background:T.bgRaised }}>
                {CONFIG_SECTIONS.map(s => {
                  const active = s.id === section;
                  return (
                    <button key={s.id} onClick={() => setSection(s.id)} style={{
                      display:'flex', alignItems:'center', gap:10, padding:'10px 12px',
                      borderRadius:8, border:'1px solid transparent', cursor:'pointer',
                      background: active ? T.surface : 'transparent',
                      color: active ? T.fg : T.fgDim, fontFamily:'inherit', textAlign:'left',
                      width:'100%', position:'relative',
                    }}>
                      {active && <span style={{ position:'absolute', left:-10, top:'50%', transform:'translateY(-50%)', width:2, height:18, borderRadius:'0 2px 2px 0', backgroundImage:BRAND_GRADIENT }}/>}
                      <span style={{
                        width:28, height:28, borderRadius:7, background: active ? T.primaryS : T.bg,
                        border:`1px solid ${active ? T.primaryR : T.hairline}`,
                        display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                      }}>
                        <Icon name={s.icon} size={14} color={active ? T.primary : T.fgDim}/>
                      </span>
                      <div style={{ minWidth:0, flex:1 }}>
                        <div style={{ fontSize:13, fontWeight: active ? 500 : 400, letterSpacing:'-0.01em' }}>{s.label}</div>
                        <div style={{ fontSize:11, color:T.muted, marginTop:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{s.desc}</div>
                      </div>
                      <Chip mono style={{ fontSize:9.5, padding:'1px 5px' }}>{CONFIG_FIELDS[s.id].length}</Chip>
                    </button>
                  );
                })}
              </div>

              {/* Right: fields */}
              <div style={{ padding:'24px 28px' }}>
                <div style={{ marginBottom:18, display:'flex', alignItems:'center', gap:10 }}>
                  <Eyebrow color={T.primary}>· {section}</Eyebrow>
                  <span style={{ fontFamily:"'Sora', sans-serif", fontSize:18, fontWeight:600, color:T.fg, letterSpacing:'-0.02em' }}>{cur.label}</span>
                  <span style={{ fontSize:12, color:T.muted }}>{cur.desc}</span>
                </div>
                {fields.map(f => (
                  <ConfigField key={f.k}
                    label={f.label} hint={f.hint} type={f.type || 'text'}
                    options={f.options}
                    value={values[`${section}.${f.k}`]}
                    onChange={v => setVal(`${section}.${f.k}`, v)}
                    secret={f.secret && !showSecrets}
                    onToggleSecret={f.secret ? () => setShowSecrets(!showSecrets) : null}
                  />
                ))}
              </div>
            </div>
          </Surface>
        </div>
      </div>
    </MeshBg>
  );
}

Object.assign(window, { FrameSettings, Switch });
