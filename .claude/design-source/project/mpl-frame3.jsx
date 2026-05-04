
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 3 — RENDER STAGE (live)
// ─────────────────────────────────────────────────────────────────────────────

function FrameRender({ onNav }) {
  const [autoscroll, setAutoscroll] = React.useState(true);
  const [cancelConfirm, setCancelConfirm] = React.useState(false);
  const [progress, setProgress] = React.useState(72);
  const [scrubPos, setScrubPos] = React.useState(38);
  const logRef = React.useRef(null);

  // Animate progress
  React.useEffect(() => {
    const t = setInterval(() => {
      setProgress(p => p >= 98 ? 98 : p + 0.4);
    }, 400);
    return () => clearInterval(t);
  }, []);

  // Auto-scroll log
  React.useEffect(() => {
    if (autoscroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [autoscroll]);

  const stageColors = {
    script:  T.info,
    tts:     T.success,
    images:  T.amber,
    moviepy: '#C084FC',
    upload:  T.warning,
  };

  const substeps = [
    { label:'Generate script', done:true },
    { label:'Text-to-speech', done:true },
    { label:'Generate images', done:true },
    { label:'Composite video', done:true },
    { label:'Generate subtitles', done:false, active:true, progress:'4/12 chunks' },
    { label:'Apply Ken Burns', done:false },
    { label:'Export MP4', done:false },
    { label:'Upload to YouTube', done:false },
  ];

  const chapters = [
    { label:'Hook', start:0, end:20, color: T.amber },
    { label:'Body', start:20, end:65, color: T.info },
    { label:'CTA', start:65, end:85, color: T.success },
    { label:'Outro', start:85, end:100, color: T.secondary },
  ];

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <TopBar title="Rendering · Supernova 1054" onNew={() => {}}/>

      <div style={{ flex:1, display:'flex', overflow:'hidden' }}>
        {/* ── LEFT: log stream ─────────────────────────────────────── */}
        <div style={{
          flex:'0 0 40%', display:'flex', flexDirection:'column',
          borderRight:`1px solid ${T.hairline}`, background: T.base, overflow:'hidden',
        }}>
          <div style={{
            padding:'10px 16px', borderBottom:`1px solid ${T.hairline}`,
            display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0,
          }}>
            <span style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.06em', textTransform:'uppercase' }}>
              Log Stream
            </span>
            {!autoscroll && (
              <button onClick={() => setAutoscroll(true)} style={{
                fontSize:10, padding:'3px 8px', borderRadius:6,
                background: T.amberDim, border:`1px solid ${T.amberRing}`,
                color: T.amber, cursor:'pointer',
              }}>
                Resume autoscroll ↓
              </button>
            )}
          </div>

          <div ref={logRef} onScroll={(e) => {
            const el = e.currentTarget;
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
            if (!atBottom) setAutoscroll(false);
          }} style={{
            flex:1, overflow:'auto', padding:'12px 16px',
            fontFamily:'Geist Mono, JetBrains Mono, monospace', fontSize:11,
            display:'flex', flexDirection:'column', gap:2,
          }}>
            {MOCK_LOG.map((line, i) => (
              <div key={i} style={{ display:'flex', gap:10, lineHeight:1.7, alignItems:'flex-start' }}>
                <span style={{ color: T.muted, flexShrink:0, fontSize:10 }}>{line.ts}</span>
                <span style={{
                  padding:'0 5px', borderRadius:4, fontSize:9, fontWeight:600,
                  background: stageColors[line.stage] + '18',
                  color: stageColors[line.stage],
                  flexShrink:0, letterSpacing:'0.05em', marginTop:2,
                }}>
                  [{line.stage}]
                </span>
                <span style={{
                  color: line.type === 'success' ? T.success : line.type === 'error' ? T.danger : T.secondary,
                  flex:1, wordBreak:'break-word',
                }}>
                  {line.text}
                </span>
              </div>
            ))}
            {/* Live animated line */}
            <div style={{ display:'flex', gap:10, lineHeight:1.7, alignItems:'flex-start' }}>
              <span style={{ color: T.muted, fontSize:10 }}>10:42:29</span>
              <span style={{
                padding:'0 5px', borderRadius:4, fontSize:9, fontWeight:600,
                background: T.warning + '18', color: T.warning,
                flexShrink:0, letterSpacing:'0.05em', marginTop:2,
              }}>[moviepy]</span>
              <span style={{ color: T.secondary }}>
                Generating subtitles 4/12 chunks
                <span style={{ animation:'blink 1s step-end infinite', marginLeft:4 }}>▌</span>
              </span>
            </div>
          </div>
        </div>

        {/* ── RIGHT: video preview + timeline ──────────────────────── */}
        <div style={{
          flex:'0 0 60%', display:'flex', flexDirection:'column', overflow:'hidden',
          background: T.surf1,
        }}>
          {/* Preview area */}
          <div style={{
            flex:1, display:'flex', alignItems:'center', justifyContent:'center',
            padding:24, position:'relative', overflow:'hidden',
          }}>
            {/* Video frame (9:16 aspect) */}
            <div style={{
              height:'100%', maxHeight:360, aspectRatio:'9/16',
              borderRadius:12, overflow:'hidden', position:'relative',
              background:`linear-gradient(160deg, hsl(220,30%,8%), hsl(240,25%,6%))`,
              border:`1px solid ${T.hairline}`,
            }}>
              <div style={{
                position:'absolute', inset:0, opacity:0.1,
                backgroundImage:'repeating-linear-gradient(45deg, rgba(255,255,255,0.3) 0, rgba(255,255,255,0.3) 1px, transparent 0, transparent 50%)',
                backgroundSize:'8px 8px',
              }}/>
              <div style={{
                position:'absolute', inset:0,
                display:'flex', flexDirection:'column',
                alignItems:'center', justifyContent:'center', gap:8,
              }}>
                <div style={{ fontSize:10, fontFamily:'Geist Mono, monospace', color:'rgba(255,255,255,0.2)', textAlign:'center', padding:'0 16px' }}>
                  1080×1920 · frame accurate composite
                </div>
              </div>
              {/* Stage badge */}
              <div style={{
                position:'absolute', top:10, left:10,
                background: T.warningBg, border:`1px solid ${T.warning}33`,
                borderRadius:6, padding:'3px 8px',
                display:'flex', alignItems:'center', gap:5, fontSize:10, color: T.warning,
                fontFamily:'Geist Mono, monospace',
              }}>
                <span style={{ width:5, height:5, borderRadius:'50%', background: T.warning }} />
                Subtitles 4/12
              </div>
              {/* Scrub position indicator */}
              <div style={{
                position:'absolute', bottom:10, left:10, right:10, fontSize:10,
                fontFamily:'Geist Mono, monospace', color: T.secondary, textAlign:'center',
              }}>
                00:{String(Math.floor(scrubPos*47/100)).padStart(2,'0')} / 0:47
              </div>
            </div>

            {/* Completed stage badges — floating */}
            <div style={{
              position:'absolute', top:24, right:24,
              display:'flex', flexDirection:'column', gap:6,
            }}>
              {[
                { label:'Script', color: T.info },
                { label:'TTS', color: T.success },
                { label:'Images 4/4', color: T.amber },
                { label:'Composite', color:'#C084FC' },
              ].map(b => (
                <div key={b.label} style={{
                  display:'flex', alignItems:'center', gap:5,
                  padding:'3px 8px', borderRadius:6, fontSize:10,
                  background: b.color+'18', border:`1px solid ${b.color}33`,
                  color: b.color, fontFamily:'Geist Mono, monospace',
                }}>
                  <Icon name="check" size={9} color={b.color}/>
                  {b.label}
                </div>
              ))}
            </div>
          </div>

          {/* Timeline */}
          <div style={{
            padding:'12px 24px', borderTop:`1px solid ${T.hairline}`,
            flexShrink:0,
          }}>
            <div style={{ fontSize:11, fontWeight:600, color: T.muted, marginBottom:8, textTransform:'uppercase', letterSpacing:'0.06em' }}>Timeline</div>
            {/* Chapter track */}
            <div style={{ position:'relative', height:24, borderRadius:4, overflow:'hidden', marginBottom:8, display:'flex' }}>
              {chapters.map(ch => (
                <div key={ch.label} style={{
                  width:`${ch.end-ch.start}%`, height:'100%',
                  background: ch.color+'22', borderRight:`1px solid ${T.base}`,
                  display:'flex', alignItems:'center', justifyContent:'center',
                  fontSize:9, fontFamily:'Geist Mono, monospace', color: ch.color,
                  flexShrink:0,
                }}>
                  {ch.label}
                </div>
              ))}
              {/* Scrub head */}
              <div style={{
                position:'absolute', top:0, bottom:0,
                left:`${scrubPos}%`, width:2,
                background: T.amber, transition:'left 0.4s ease',
              }}/>
            </div>
            {/* Scrub slider */}
            <input type="range" min={0} max={100} value={scrubPos}
              onChange={e => setScrubPos(Number(e.target.value))}
              style={{ width:'100%', accentColor: T.amber }}
            />
          </div>

          {/* Progress + controls */}
          <div style={{
            padding:'12px 24px 16px', borderTop:`1px solid ${T.hairline}`,
            flexShrink:0,
          }}>
            {/* Substeps */}
            <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:12 }}>
              {substeps.map(s => (
                <div key={s.label} style={{
                  display:'flex', alignItems:'center', gap:4,
                  padding:'3px 8px', borderRadius:6, fontSize:10,
                  background: s.done ? T.successBg : s.active ? T.amberDim : T.surf2,
                  border:`1px solid ${s.done ? T.success+'33' : s.active ? T.amberRing : T.hairline}`,
                  color: s.done ? T.success : s.active ? T.amber : T.muted,
                  fontFamily:'Geist Mono, monospace',
                }}>
                  {s.done ? <Icon name="check" size={9} color={T.success}/> :
                   s.active ? <span style={{ width:6, height:6, borderRadius:'50%', background: T.amber, animation:'ping 1s ease-in-out infinite' }}/> :
                   <span style={{ width:6, height:6, borderRadius:'50%', background: T.muted }}/>
                  }
                  {s.label}{s.active && s.progress ? ` · ${s.progress}` : ''}
                </div>
              ))}
            </div>

            {/* Main progress bar */}
            <div style={{ marginBottom:8 }}>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:11, color: T.muted, marginBottom:6 }}>
                <span>Generating subtitles · 4/12 chunks</span>
                <span style={{ fontFamily:'Geist Mono, monospace', color: T.primary }}>{Math.round(progress)}%</span>
              </div>
              <div style={{ height:5, borderRadius:3, background: T.surf2, overflow:'hidden' }}>
                <div style={{
                  height:'100%', borderRadius:3, background:`linear-gradient(90deg, ${T.amber}, #C47A28)`,
                  width:`${progress}%`, transition:'width 0.4s ease',
                }}/>
              </div>
              <div style={{ marginTop:6, fontSize:10, color: T.muted, fontFamily:'Geist Mono, monospace' }}>
                ETA ~1m 12s · Started 10:42:01
              </div>
            </div>

            {/* Cancel */}
            <div style={{ display:'flex', justifyContent:'flex-end' }}>
              {!cancelConfirm ? (
                <button onClick={() => setCancelConfirm(true)} style={{
                  padding:'6px 14px', borderRadius:8,
                  border:`1px solid ${T.danger}44`, background:'transparent',
                  color: T.danger, fontSize:12, cursor:'pointer', transition:'all 120ms',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background=T.dangerBg; }}
                  onMouseLeave={e => { e.currentTarget.style.background='transparent'; }}
                >Cancel render</button>
              ) : (
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  <span style={{ fontSize:12, color: T.danger }}>Are you sure?</span>
                  <button onClick={() => setCancelConfirm(false)} style={{
                    padding:'5px 12px', borderRadius:8,
                    border:`1px solid ${T.hairline}`, background:'transparent',
                    color: T.secondary, fontSize:12, cursor:'pointer',
                  }}>No, keep going</button>
                  <button style={{
                    padding:'5px 12px', borderRadius:8,
                    border:`1px solid ${T.danger}`, background: T.dangerBg,
                    color: T.danger, fontSize:12, cursor:'pointer', fontWeight:600,
                  }}>Yes, cancel</button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes blink { 50% { opacity: 0; } }
        @keyframes ping { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
      `}</style>
    </div>
  );
}

Object.assign(window, { FrameRender });
