
// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTS STRIP — Design System Reference
// ─────────────────────────────────────────────────────────────────────────────

function ComponentsStrip() {
  const [btnLoading, setBtnLoading] = React.useState(false);

  const Section = ({ title, children }) => (
    <div style={{ marginBottom: 48 }}>
      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
        color: T.muted, marginBottom: 20, paddingBottom: 8,
        borderBottom: `1px solid ${T.hairline}`,
      }}>{title}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start' }}>
        {children}
      </div>
    </div>
  );

  const Row = ({ label, children }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 9, color: T.muted, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{label}</span>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{children}</div>
    </div>
  );

  // Button primitive
  const Btn = ({ label, variant = 'primary', size = 'md', loading = false, disabled = false, icon }) => {
    const sizes = { sm: { p: '4px 10px', fs: 11 }, md: { p: '7px 14px', fs: 13 }, lg: { p: '10px 20px', fs: 14 } };
    const s = sizes[size];
    const styles = {
      primary:     { bg: T.amber, color: '#0B0B0D', border: 'none' },
      secondary:   { bg: T.surf2, color: T.secondary, border: `1px solid ${T.hairline}` },
      ghost:       { bg: 'transparent', color: T.secondary, border: '1px solid transparent' },
      destructive: { bg: T.dangerBg, color: T.danger, border: `1px solid ${T.danger}44` },
    };
    const vs = styles[variant];
    return (
      <button disabled={disabled} style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: s.p, borderRadius: 8, border: vs.border,
        background: disabled ? T.surf3 : vs.bg,
        color: disabled ? T.muted : vs.color,
        fontSize: s.fs, fontWeight: variant === 'primary' ? 600 : 400,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1, transition: 'opacity 120ms',
        letterSpacing: '-0.01em',
      }}>
        {loading && <span style={{ width: 10, height: 10, borderRadius: '50%', border: `2px solid rgba(0,0,0,0.2)`, borderTopColor: '#0B0B0D', animation: 'spin 0.8s linear infinite', display: 'inline-block' }}/>}
        {icon && !loading && <Icon name={icon} size={size === 'lg' ? 16 : 12} color="currentColor"/>}
        {label}
      </button>
    );
  };

  // Input primitive
  const Input = ({ placeholder, type = 'text', label, mono = false, disabled = false }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {label && <label style={{ fontSize: 11, color: T.muted, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>{label}</label>}
      <input type={type} placeholder={placeholder} disabled={disabled} style={{
        background: disabled ? T.surf1 : T.surf2, border: `1px solid ${T.hairline}`,
        borderRadius: 8, color: T.primary, fontSize: 12, padding: '7px 12px',
        outline: 'none', width: 220, opacity: disabled ? 0.5 : 1,
        fontFamily: mono ? 'Geist Mono, monospace' : 'inherit',
      }}/>
    </div>
  );

  // LogLine component
  const LogLine = ({ ts, stage, text, type }) => {
    const stageColors = { script: T.info, tts: T.success, images: T.amber, moviepy: '#C084FC', upload: T.warning };
    return (
      <div style={{ display: 'flex', gap: 10, lineHeight: 1.7, alignItems: 'flex-start', fontFamily: 'Geist Mono, monospace', fontSize: 11 }}>
        <span style={{ color: T.muted, flexShrink: 0, fontSize: 10 }}>{ts}</span>
        <span style={{
          padding: '0 5px', borderRadius: 4, fontSize: 9, fontWeight: 600,
          background: (stageColors[stage] || T.secondary) + '18',
          color: stageColors[stage] || T.secondary,
          flexShrink: 0, letterSpacing: '0.05em', marginTop: 2,
        }}>[{stage}]</span>
        <span style={{ color: type === 'success' ? T.success : type === 'error' ? T.danger : T.secondary }}>{text}</span>
      </div>
    );
  };

  // Schedule row
  const ScheduleRow = ({ time, account, type, topic, status }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '8px 12px', borderRadius: 8,
      background: T.surf2, border: `1px solid ${T.hairline}`, width: 320,
    }}>
      <span style={{ fontSize: 11, fontFamily: 'Geist Mono, monospace', color: T.amber, flexShrink: 0, width: 40 }}>{time}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: T.primary, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{topic}</div>
        <div style={{ fontSize: 10, color: T.muted }}>{account} · {type}</div>
      </div>
      <StatusPill status={status} size="xs"/>
    </div>
  );

  // Toast
  const Toast = ({ message, type = 'success' }) => {
    const colors = { success: T.success, warning: T.warning, error: T.danger, info: T.info };
    const c = colors[type];
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '10px 14px', borderRadius: 10,
        background: T.surf2, border: `1px solid ${c}33`,
        boxShadow: `0 8px 24px rgba(0,0,0,0.4)`, minWidth: 260, maxWidth: 340,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: c, flexShrink: 0 }}/>
        <span style={{ fontSize: 12, color: T.primary, flex: 1 }}>{message}</span>
        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.muted, padding: 2 }}>
          <Icon name="x" size={12} color="currentColor"/>
        </button>
      </div>
    );
  };

  return (
    <div style={{
      background: T.base, minHeight: '100vh', padding: '48px',
      fontFamily: 'Geist Sans, Inter, sans-serif',
    }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>

        {/* Title */}
        <div style={{ marginBottom: 48 }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: T.primary, letterSpacing: '-0.03em', marginBottom: 6 }}>
            MoneyPrinterLargo — Design System
          </div>
          <div style={{ fontSize: 13, color: T.secondary }}>
            Component reference · tokens · patterns
          </div>
        </div>

        {/* ── TYPE SCALE ──────────────────────────────────────────────── */}
        <Section title="Type Scale — Geist Sans + Geist Mono">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
            {[
              { size: 56, label: '56 — Display', weight: 700, track: '-0.03em' },
              { size: 40, label: '40 — H1', weight: 700, track: '-0.03em' },
              { size: 28, label: '28 — H2', weight: 700, track: '-0.02em' },
              { size: 20, label: '20 — H3', weight: 600, track: '-0.02em' },
              { size: 16, label: '16 — Body Large', weight: 400, track: '-0.01em' },
              { size: 14, label: '14 — Body', weight: 400, track: '-0.01em' },
              { size: 13, label: '13 — UI Primary', weight: 400, track: '-0.01em' },
              { size: 12, label: '12 — UI Small', weight: 400, track: '0em' },
              { size: 11, label: '11 — Label', weight: 600, track: '0.04em', upper: true },
              { size: 10, label: '10 — Caption', weight: 400, track: '0em' },
            ].map(t => (
              <div key={t.size} style={{ display: 'flex', alignItems: 'baseline', gap: 24 }}>
                <span style={{ width: 40, fontSize: 10, color: T.muted, fontFamily: 'Geist Mono, monospace', flexShrink: 0 }}>{t.size}</span>
                <span style={{
                  fontSize: Math.min(t.size, 40), fontWeight: t.weight,
                  letterSpacing: t.track, textTransform: t.upper ? 'uppercase' : 'none',
                  color: T.primary, lineHeight: 1.2,
                }}>{t.label}</span>
              </div>
            ))}
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 10, color: T.muted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Mono — IDs, prompts, tokens</span>
              {['es-ES-AlvaroNeural', 'deepseek-v4-pro:cloud', '10:42:07', '18.3 MB', '#6bcfca83-1058'].map(m => (
                <span key={m} style={{ fontSize: 11, fontFamily: 'Geist Mono, monospace', color: T.secondary }}>{m}</span>
              ))}
            </div>
          </div>
        </Section>

        {/* ── COLORS ──────────────────────────────────────────────────── */}
        <Section title="Color Tokens">
          {[
            { name: 'base', val: T.base },
            { name: 'surf1', val: T.surf1 },
            { name: 'surf2', val: T.surf2 },
            { name: 'surf3', val: T.surf3 },
            { name: 'primary', val: T.primary },
            { name: 'secondary', val: T.secondary },
            { name: 'muted', val: T.muted },
            { name: 'amber', val: T.amber },
            { name: 'success', val: T.success },
            { name: 'warning', val: T.warning },
            { name: 'danger', val: T.danger },
            { name: 'info', val: T.info },
          ].map(c => (
            <div key={c.name} style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'center' }}>
              <div style={{
                width: 48, height: 48, borderRadius: 8, background: c.val,
                border: `1px solid ${T.hairline}`,
              }}/>
              <span style={{ fontSize: 9, color: T.muted, textAlign: 'center' }}>{c.name}</span>
              <span style={{ fontSize: 9, fontFamily: 'Geist Mono, monospace', color: T.muted }}>{c.val}</span>
            </div>
          ))}
        </Section>

        {/* ── SPACING ─────────────────────────────────────────────────── */}
        <Section title="Spacing Scale (8px grid)">
          {[4,8,12,16,20,24,32,40,48,64].map(s => (
            <div key={s} style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'center' }}>
              <div style={{ width: s, height: s, background: T.amber, opacity: 0.6, borderRadius: 2 }}/>
              <span style={{ fontSize: 9, fontFamily: 'Geist Mono, monospace', color: T.muted }}>{s}</span>
            </div>
          ))}
          <div style={{ width: '100%', marginTop: 8 }}>
            <span style={{ fontSize: 10, color: T.muted }}>Radii: 6px chips · 8px inputs/buttons · 12px cards · 99px pills</span>
          </div>
        </Section>

        {/* ── BUTTONS ─────────────────────────────────────────────────── */}
        <Section title="Buttons">
          <Row label="Variants">
            <Btn label="New render" variant="primary" icon="plus"/>
            <Btn label="Save draft" variant="secondary" icon="download"/>
            <Btn label="View all" variant="ghost"/>
            <Btn label="Cancel render" variant="destructive"/>
          </Row>
          <Row label="Sizes">
            <Btn label="Small" variant="primary" size="sm"/>
            <Btn label="Medium" variant="primary" size="md"/>
            <Btn label="Large" variant="primary" size="lg"/>
          </Row>
          <Row label="States">
            <Btn label="Loading…" variant="primary" loading={true}/>
            <Btn label="Disabled" variant="primary" disabled={true}/>
            <Btn label="Disabled" variant="secondary" disabled={true}/>
          </Row>
        </Section>

        {/* ── INPUTS ──────────────────────────────────────────────────── */}
        <Section title="Inputs">
          <Input label="Text" placeholder="Topic or subject…"/>
          <Input label="Mono" placeholder="http://127.0.0.1:11434" mono/>
          <Input label="Secret" placeholder="AIzaSy…" type="password"/>
          <Input label="Disabled" placeholder="Disabled state" disabled/>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: 11, color: T.muted, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>Textarea</label>
            <textarea placeholder="Script or description…" style={{
              background: T.surf2, border: `1px solid ${T.hairline}`,
              borderRadius: 8, color: T.primary, fontSize: 12, padding: '8px 12px',
              outline: 'none', width: 220, resize: 'vertical', minHeight: 72,
              fontFamily: 'inherit',
            }} rows={3}/>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: 11, color: T.muted, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>Voice picker</label>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px',
              background: T.surf2, border: `1px solid ${T.hairline}`, borderRadius: 8, width: 240,
            }}>
              <Icon name="mic" size={14} color={T.amber}/>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: T.primary, fontWeight: 500 }}>Carlos</div>
                <div style={{ fontSize: 10, fontFamily: 'Geist Mono, monospace', color: T.muted }}>es-ES-AlvaroNeural</div>
              </div>
              <Icon name="chevronD" size={12} color={T.muted}/>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: 11, color: T.muted, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>File path picker</label>
            <div style={{ display: 'flex', gap: 6 }}>
              <input readOnly value="C:\Users\danie\AppData\Roaming\Mozilla\..." style={{
                background: T.surf2, border: `1px solid ${T.hairline}`,
                borderRadius: 8, color: T.secondary, fontSize: 11, padding: '7px 12px',
                outline: 'none', width: 220, fontFamily: 'Geist Mono, monospace',
              }}/>
              <button style={{
                padding: '7px 12px', borderRadius: 8, border: `1px solid ${T.hairline}`,
                background: T.surf2, color: T.secondary, fontSize: 12, cursor: 'pointer',
              }}>Browse</button>
            </div>
          </div>
        </Section>

        {/* ── SELECT / DROPDOWN ───────────────────────────────────────── */}
        <Section title="Select">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: 11, color: T.muted, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>Select</label>
            <select style={{
              background: T.surf2, border: `1px solid ${T.hairline}`,
              borderRadius: 8, color: T.primary, fontSize: 12, padding: '7px 12px',
              outline: 'none', cursor: 'pointer',
            }}>
              <option>All accounts</option>
              <option>Savirox</option>
              <option>CosmosES</option>
            </select>
          </div>
        </Section>

        {/* ── CHIPS ───────────────────────────────────────────────────── */}
        <Section title="Chips">
          <Row label="Account">
            <Chip color={T.amber}>Savirox</Chip>
            <Chip color={T.info}>CosmosES</Chip>
            <Chip color={T.success}>SpaceBot_X</Chip>
          </Row>
          <Row label="Voice / Model">
            <Chip>es-ES-AlvaroNeural</Chip>
            <Chip>deepseek-v4-pro:cloud</Chip>
            <Chip color={T.amber}>Nano Banana 2</Chip>
          </Row>
          <Row label="Status">
            <StatusPill status="uploaded"/>
            <StatusPill status="rendering"/>
            <StatusPill status="draft"/>
            <StatusPill status="failed"/>
            <StatusPill status="pending"/>
          </Row>
        </Section>

        {/* ── STEPPER ─────────────────────────────────────────────────── */}
        <Section title="Stepper — Wizard Progress">
          <div style={{ width: '100%' }}>
            <Stepper steps={['Config','Script','Images','Thumbnail','Voice','Render','Upload']} current={2} onChange={() => {}}/>
          </div>
        </Section>

        {/* ── LOG LINE ────────────────────────────────────────────────── */}
        <Section title="Log Line — Render Stream">
          <div style={{
            background: T.base, borderRadius: 10, border: `1px solid ${T.hairline}`,
            padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 4, width: '100%',
          }}>
            <LogLine ts="10:42:01" stage="script" text="Generating script for topic: La supernova del año 1054..." type="info"/>
            <LogLine ts="10:42:03" stage="script" text="Script generated — 5 sentences, ~47s estimated duration" type="success"/>
            <LogLine ts="10:42:07" stage="tts" text="Audio rendered — 8748216d.wav (2.1 MB)" type="success"/>
            <LogLine ts="10:42:11" stage="images" text="Image 2/4 generated ✓" type="success"/>
            <LogLine ts="10:42:15" stage="moviepy" text="Compositing video — 1080×1920, 30fps" type="info"/>
            <LogLine ts="10:42:22" stage="upload" text="ERROR: Firefox profile locked by another process" type="error"/>
          </div>
        </Section>

        {/* ── VIDEO TILE ──────────────────────────────────────────────── */}
        <Section title="Video Tile — Three Sizes">
          <Row label="Small (sm)">
            <VideoTile render={MOCK_RENDERS[0]} size="sm"/>
            <VideoTile render={MOCK_RENDERS[3]} size="sm"/>
          </Row>
          <Row label="Medium (md)">
            <VideoTile render={MOCK_RENDERS[0]} size="md"/>
            <VideoTile render={MOCK_RENDERS[3]} size="md"/>
          </Row>
          <Row label="Large (lg)">
            <VideoTile render={MOCK_RENDERS[0]} size="lg"/>
            <VideoTile render={MOCK_RENDERS[3]} size="lg"/>
          </Row>
        </Section>

        {/* ── SCHEDULE ROW ────────────────────────────────────────────── */}
        <Section title="Schedule Row">
          {MOCK_SCHEDULE.map((s, i) => <ScheduleRow key={i} {...s}/>)}
        </Section>

        {/* ── TOAST ───────────────────────────────────────────────────── */}
        <Section title="Toast — Notifications">
          <Toast message="Render complete · Supernova 1054.mp4 (18.3 MB)" type="success"/>
          <Toast message="Generating subtitles · 4/12 chunks…" type="info"/>
          <Toast message="Upload failed · Firefox profile locked" type="error"/>
          <Toast message="Disk space low · 0.8 GB remaining" type="warning"/>
        </Section>

        {/* ── ACCENT USAGE ANNOTATION ─────────────────────────────────── */}
        <Section title="Accent Usage — #E8A24F Ember">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, color: T.secondary, width: '100%' }}>
            {[
              { use: 'Active nav indicator', sample: <span style={{ width: 3, height: 16, background: T.amber, borderRadius: 2, display: 'inline-block' }}/> },
              { use: 'Primary CTA button', sample: <Btn label="New render" variant="primary" size="sm"/> },
              { use: 'Active stepper segment', sample: <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, background: T.amberDim, border: `1px solid ${T.amberRing}`, color: T.amber, fontSize: 11 }}>▶ Images</div> },
              { use: 'Focus ring / hover border', sample: <input placeholder="Focused input" style={{ padding: '5px 10px', borderRadius: 8, background: T.surf2, border: `1px solid ${T.amber}`, color: T.primary, fontSize: 11, outline: 'none', width: 160 }}/> },
              { use: 'Timestamp in log', sample: <span style={{ fontFamily: 'Geist Mono, monospace', fontSize: 11, color: T.amber }}>10:42:07</span> },
              { use: 'Voice chip accent', sample: <Chip color={T.amber}>es-ES-AlvaroNeural</Chip> },
            ].map(r => (
              <div key={r.use} style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                <span style={{ width: 240, color: T.muted, fontSize: 11 }}>{r.use}</span>
                {r.sample}
              </div>
            ))}
          </div>
        </Section>

      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

Object.assign(window, { ComponentsStrip });
