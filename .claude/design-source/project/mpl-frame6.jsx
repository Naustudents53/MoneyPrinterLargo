
// ─────────────────────────────────────────────────────────────────────────────
// FRAME 6 — ACCOUNTS
// ─────────────────────────────────────────────────────────────────────────────

function FrameAccounts({ onNav }) {
  const [editId, setEditId] = React.useState(null);

  const platformColors = {
    youtube: '#FF4444',
    twitter: T.secondary,
  };

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <TopBar title="Accounts" onNew={() => {}}/>
      <div style={{ flex:1, overflow:'auto', padding:32 }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(300px,1fr))', gap:16 }}>
          {MOCK_ACCOUNTS.map(acc => (
            <div key={acc.id} style={{
              background: T.surf2, border:`1px solid ${T.hairline}`,
              borderRadius:12, padding:20, display:'flex', flexDirection:'column', gap:14,
              transition:'border-color 120ms',
            }}
              onMouseEnter={e => e.currentTarget.style.borderColor='rgba(255,255,255,0.12)'}
              onMouseLeave={e => e.currentTarget.style.borderColor=T.hairline}
            >
              {/* Header */}
              <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                <div style={{
                  width:40, height:40, borderRadius:'50%', flexShrink:0,
                  background:`linear-gradient(135deg, ${T.surf3}, ${T.base})`,
                  border:`2px solid ${platformColors[acc.platform]}33`,
                  display:'flex', alignItems:'center', justifyContent:'center',
                  fontSize:14, fontWeight:700, color: T.primary,
                }}>
                  {acc.nickname.slice(0,2).toUpperCase()}
                </div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <span style={{ fontSize:14, fontWeight:600, color: T.primary, letterSpacing:'-0.01em' }}>{acc.nickname}</span>
                    <PlatformGlyph platform={acc.platform} size={16}/>
                  </div>
                  <div style={{ fontSize:11, color: T.muted }}>{acc.niche}</div>
                </div>
                <div style={{ display:'flex', gap:6 }}>
                  <span style={{ fontSize:14 }}>{acc.flag}</span>
                  <span style={{ fontSize:10, color: T.muted, fontFamily:'Geist Mono, monospace', marginTop:2 }}>{acc.lang}</span>
                </div>
              </div>

              {/* Voices */}
              <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                <div style={{ display:'flex', flexDirection:'column', gap:3 }}>
                  <span style={{ fontSize:9, color: T.muted, textTransform:'uppercase', letterSpacing:'0.06em' }}>Short voice</span>
                  <Chip color={T.amber}>{acc.shortVoice}</Chip>
                </div>
                {acc.longVoice !== '—' && (
                  <div style={{ display:'flex', flexDirection:'column', gap:3 }}>
                    <span style={{ fontSize:9, color: T.muted, textTransform:'uppercase', letterSpacing:'0.06em' }}>Long voice</span>
                    <Chip color={T.info}>{acc.longVoice}</Chip>
                  </div>
                )}
              </div>

              {/* Image style */}
              <div>
                <div style={{ fontSize:9, color: T.muted, textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:4 }}>Image style</div>
                <div style={{
                  fontSize:10, fontFamily:'Geist Mono, monospace', color: T.secondary,
                  lineHeight:1.5, overflow:'hidden', textOverflow:'ellipsis',
                  display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical',
                  padding:'5px 8px', background: T.surf3, borderRadius:6,
                  border:`1px solid ${T.hairline}`,
                }}>
                  {acc.imageStyle}
                </div>
              </div>

              {/* Firefox profile + upload count */}
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <div style={{
                  display:'flex', alignItems:'center', gap:5, flex:1,
                  padding:'5px 8px', borderRadius:6,
                  background: acc.profileLinked ? T.successBg : T.dangerBg,
                  border:`1px solid ${acc.profileLinked ? T.success+'33' : T.danger+'33'}`,
                }}>
                  <Icon name={acc.profileLinked ? 'check' : 'alertC'} size={11} color={acc.profileLinked ? T.success : T.danger}/>
                  <span style={{ fontSize:10, color: acc.profileLinked ? T.success : T.danger }}>
                    {acc.profileLinked ? 'Firefox profile linked' : 'Profile not linked'}
                  </span>
                </div>
                <div style={{ fontSize:11, fontFamily:'Geist Mono, monospace', color: T.muted }}>
                  {acc.uploads} uploads
                </div>
              </div>

              {/* Edit button */}
              <button onClick={() => setEditId(acc.id === editId ? null : acc.id)} style={{
                width:'100%', padding:'7px', borderRadius:8,
                border:`1px solid ${acc.id === editId ? T.amberRing : T.hairline}`,
                background: acc.id === editId ? T.amberDim : 'transparent',
                color: acc.id === editId ? T.amber : T.secondary,
                fontSize:12, cursor:'pointer', transition:'all 120ms',
                display:'flex', alignItems:'center', justifyContent:'center', gap:6,
              }}>
                <Icon name="edit" size={12} color="currentColor"/>
                {acc.id === editId ? 'Editing…' : 'Edit'}
              </button>
            </div>
          ))}

          {/* Add new account */}
          <button style={{
            background:'transparent', border:`2px dashed ${T.hairline}`,
            borderRadius:12, padding:20, cursor:'pointer', minHeight:260,
            display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:8,
            color: T.muted, transition:'all 120ms',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor=T.amber+'44'; e.currentTarget.style.color=T.amber; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor=T.hairline; e.currentTarget.style.color=T.muted; }}
          >
            <Icon name="plus" size={22} color="currentColor"/>
            <span style={{ fontSize:12 }}>Add Account</span>
            <span style={{ fontSize:10, color: T.muted, textAlign:'center', maxWidth:160 }}>
              YouTube, Twitter, or Affiliate
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { FrameAccounts });
