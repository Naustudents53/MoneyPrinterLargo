
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 2 — NEW SHORT (Wizard · Images step)
// ─────────────────────────────────────────────────────────────────────────────

function FrameNewShort({ onNav, compact = false }) {
  const [step, setStep] = React.useState(2); // 0-indexed, Images=2
  const [lockedImages, setLockedImages] = React.useState([false, true, false, false]);
  const [hoveredImg, setHoveredImg] = React.useState(null);
  const [previewOpen, setPreviewOpen] = React.useState(false);

  const STEPS = ['Config','Script','Images','Thumbnail','Voice','Render','Upload'];

  const toggleLock = (i) => {
    const n = [...lockedImages]; n[i] = !n[i]; setLockedImages(n);
  };

  const imgColors = ['hsl(220,30%,11%)','hsl(200,35%,9%)','hsl(240,25%,10%)','hsl(210,40%,8%)'];

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <TopBar title="New Short" onNew={() => {}}/>
      <Stepper steps={STEPS} current={step} onChange={setStep}/>

      <div style={{
        flex:1, display:'flex', overflow:'hidden',
        flexDirection: compact ? 'column' : 'row',
      }}>
        {/* ── LEFT: image grid ─────────────────────────────────────────── */}
        <div style={{
          flex: compact ? 'none' : '0 0 60%',
          height: compact ? '60%' : 'auto',
          display:'flex', flexDirection:'column',
          borderRight: compact ? 'none' : `1px solid ${T.hairline}`,
          borderBottom: compact ? `1px solid ${T.hairline}` : 'none',
          overflow:'auto',
        }}>
          <div style={{ padding:'20px 24px 12px', display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0 }}>
            <div>
              <span style={{ fontSize:14, fontWeight:600, color: T.primary, letterSpacing:'-0.01em' }}>Scene Images</span>
              <span style={{ fontSize:12, color: T.muted, marginLeft:10 }}>4 of 4 generated</span>
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <button style={{
                display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
                background: T.surf2, border:`1px solid ${T.hairline}`,
                borderRadius:8, color: T.secondary, fontSize:12, cursor:'pointer',
                transition:'all 120ms',
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor=T.amberRing; e.currentTarget.style.color=T.primary; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.secondary; }}
              >
                <Icon name="refresh" size={12} color="currentColor"/>
                Regenerate all
              </button>
              <Chip color={T.amber}>Nano Banana 2</Chip>
            </div>
          </div>

          {/* 4-up grid */}
          <div style={{
            flex:1, padding:'0 24px 24px',
            display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:12,
            alignContent:'start', overflow:'auto',
          }}>
            {MOCK_IMAGES.map((img, i) => (
              <div key={img.id} style={{ display:'flex', flexDirection:'column', gap:6 }}
                onMouseEnter={() => setHoveredImg(i)}
                onMouseLeave={() => setHoveredImg(null)}
              >
                {/* Image tile */}
                <div style={{
                  aspectRatio:'9/16', borderRadius:10, overflow:'hidden',
                  background:`linear-gradient(160deg, ${imgColors[i]}, ${T.surf1})`,
                  border:`1px solid ${lockedImages[i] ? T.amber+'44' : T.hairline}`,
                  position:'relative', cursor:'pointer', transition:'border-color 120ms',
                }}>
                  {/* Stripe placeholder */}
                  <div style={{
                    position:'absolute', inset:0, opacity:0.10,
                    backgroundImage:'repeating-linear-gradient(135deg, rgba(255,255,255,0.3) 0, rgba(255,255,255,0.3) 1px, transparent 0, transparent 50%)',
                    backgroundSize:'8px 8px',
                  }}/>

                  {/* AI image label */}
                  <div style={{
                    position:'absolute', top:8, left:8, right:8,
                    fontSize:9, fontFamily:'Geist Mono, monospace',
                    color:'rgba(255,255,255,0.2)', lineHeight:1.4, textAlign:'center',
                  }}>
                    AI image {i+1}
                  </div>

                  {/* Lock badge */}
                  {lockedImages[i] && (
                    <div style={{
                      position:'absolute', top:6, right:6,
                      background: T.amber+'22', border:`1px solid ${T.amber}44`,
                      borderRadius:6, padding:'2px 5px',
                      display:'flex', alignItems:'center', gap:3,
                    }}>
                      <Icon name="lock" size={9} color={T.amber}/>
                    </div>
                  )}

                  {/* Hover overlay */}
                  {hoveredImg === i && (
                    <div style={{
                      position:'absolute', inset:0,
                      background:'rgba(0,0,0,0.72)',
                      display:'flex', flexDirection:'column',
                      alignItems:'center', justifyContent:'center', gap:6,
                      padding:8,
                    }}>
                      {[
                        { icon:'refresh', label:'Regen', action:()=>{} },
                        { icon:'edit', label:'Edit prompt', action:()=>{} },
                        { icon:'lock', label: lockedImages[i] ? 'Unlock' : 'Lock', action:()=>toggleLock(i) },
                        { icon:'image', label:'Real photo', action:()=>{} },
                        { icon:'download', label:'Download', action:()=>{} },
                      ].map(btn => (
                        <button key={btn.icon} onClick={btn.action} style={{
                          display:'flex', alignItems:'center', gap:5, width:'100%',
                          padding:'5px 8px', borderRadius:6, border:'none',
                          background:'rgba(255,255,255,0.07)', color: T.primary,
                          fontSize:10, cursor:'pointer', transition:'background 80ms',
                        }}
                          onMouseEnter={e => e.currentTarget.style.background='rgba(255,255,255,0.13)'}
                          onMouseLeave={e => e.currentTarget.style.background='rgba(255,255,255,0.07)'}
                        >
                          <Icon name={btn.icon} size={10} color="currentColor"/>
                          {btn.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Prompt */}
                <div style={{
                  fontSize:10, color: T.muted,
                  fontFamily:'Geist Mono, monospace',
                  lineHeight:1.5, overflow:'hidden',
                  display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical',
                }}>
                  {img.prompt}
                </div>
              </div>
            ))}

            {/* Add image tile */}
            <div style={{
              display:'flex', flexDirection:'column', gap:6,
            }}>
              <button style={{
                aspectRatio:'9/16', borderRadius:10,
                border:`2px dashed ${T.hairline}`,
                background:'transparent', cursor:'pointer',
                display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:6,
                color: T.muted, transition:'all 120ms',
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor=T.amber+'44'; e.currentTarget.style.color=T.amber; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.muted; }}
              >
                <Icon name="plus" size={18} color="currentColor"/>
                <span style={{ fontSize:10 }}>Add image</span>
              </button>
            </div>
          </div>

          {/* Footer */}
          <div style={{
            height:56, display:'flex', alignItems:'center', justifyContent:'space-between',
            padding:'0 24px', borderTop:`1px solid ${T.hairline}`, flexShrink:0,
          }}>
            <button onClick={() => setStep(1)} style={{
              padding:'7px 14px', borderRadius:8, border:`1px solid ${T.hairline}`,
              background:'transparent', color: T.secondary, fontSize:13, cursor:'pointer',
              transition:'all 120ms',
            }}
              onMouseEnter={e => { e.currentTarget.style.borderColor=T.amberRing; e.currentTarget.style.color=T.primary; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.secondary; }}
            >← Back</button>
            <div style={{ display:'flex', gap:8 }}>
              <button style={{
                padding:'7px 14px', borderRadius:8, border:`1px solid ${T.hairline}`,
                background:'transparent', color: T.secondary, fontSize:13, cursor:'pointer',
              }}>Save draft</button>
              <button onClick={() => setStep(3)} style={{
                padding:'7px 16px', borderRadius:8, border:'none',
                background: T.amber, color:'#0B0B0D', fontSize:13, fontWeight:600, cursor:'pointer',
                transition:'opacity 120ms',
              }}
                onMouseEnter={e => e.currentTarget.style.opacity='0.88'}
                onMouseLeave={e => e.currentTarget.style.opacity='1'}
              >Continue to Thumbnail →</button>
            </div>
          </div>
        </div>

        {/* ── RIGHT: live preview pane ──────────────────────────────────── */}
        <div style={{
          flex: compact ? 'none' : '0 0 40%',
          height: compact ? '40%' : 'auto',
          display:'flex', flexDirection:'column', overflow:'auto',
          background: T.surf1,
        }}>
          <div style={{ padding:'16px 20px 12px', flexShrink:0, borderBottom:`1px solid ${T.hairline}`, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <span style={{ fontSize:12, fontWeight:600, color: T.muted, letterSpacing:'0.06em', textTransform:'uppercase' }}>Preview</span>
            <div style={{ display:'flex', gap:6 }}>
              <span style={{ fontSize:11, fontFamily:'Geist Mono, monospace', color: T.amber }}>~47s</span>
            </div>
          </div>

          {/* Script */}
          <div style={{ padding:'16px 20px', flexShrink:0, borderBottom:`1px solid ${T.hairline}` }}>
            <div style={{ fontSize:11, fontWeight:600, color: T.muted, marginBottom:10, textTransform:'uppercase', letterSpacing:'0.06em' }}>Script</div>
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              {MOCK_SCRIPT.map((line, i) => (
                <div key={line.id} style={{
                  padding:'6px 10px', borderRadius:6, fontSize:12, lineHeight:1.6,
                  background: line.active ? T.amberDim : 'transparent',
                  border: `1px solid ${line.active ? T.amberRing : 'transparent'}`,
                  color: line.active ? T.primary : T.secondary,
                  transition:'all 120ms',
                }}>
                  {line.active && <span style={{ color: T.amber, fontSize:10, marginRight:6, fontFamily:'Geist Mono, monospace' }}>▶</span>}
                  {line.text}
                </div>
              ))}
            </div>
          </div>

          {/* Voice */}
          <div style={{ padding:'12px 20px', flexShrink:0, borderBottom:`1px solid ${T.hairline}` }}>
            <div style={{ fontSize:11, fontWeight:600, color: T.muted, marginBottom:8, textTransform:'uppercase', letterSpacing:'0.06em' }}>Voice</div>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{
                display:'flex', alignItems:'center', gap:8, padding:'7px 12px',
                background: T.surf2, border:`1px solid ${T.hairline}`,
                borderRadius:8, flex:1,
              }}>
                <Icon name="mic" size={14} color={T.amber}/>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:12, color: T.primary, fontWeight:500 }}>Pablo</div>
                  <div style={{ fontSize:10, fontFamily:'Geist Mono, monospace', color: T.muted }}>es-ES-AlvaroNeural</div>
                </div>
                <Icon name="chevronD" size={12} color={T.muted}/>
              </div>
              <div style={{ fontSize:11, fontFamily:'Geist Mono, monospace', color: T.amber }}>
                ~47s
              </div>
            </div>
          </div>

          {/* Music */}
          <div style={{ padding:'12px 20px', flexShrink:0 }}>
            <div style={{ fontSize:11, fontWeight:600, color: T.muted, marginBottom:8, textTransform:'uppercase', letterSpacing:'0.06em' }}>Music</div>
            <div style={{
              display:'flex', alignItems:'center', gap:8, padding:'7px 12px',
              background: T.surf2, border:`1px solid ${T.hairline}`, borderRadius:8,
            }}>
              <Icon name="music" size={14} color={T.secondary}/>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:12, color: T.primary, fontWeight:500 }}>infinity_cosmos.mp3</div>
                <div style={{ fontSize:10, color: T.muted }}>Eric Matyas — soundimage.org</div>
              </div>
              <label style={{ display:'flex', alignItems:'center', gap:5, cursor:'pointer' }}>
                <input type="checkbox" defaultChecked style={{ accentColor: T.amber, width:12, height:12 }}/>
                <span style={{ fontSize:10, color: T.muted }}>Attribution</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { FrameNewShort });
