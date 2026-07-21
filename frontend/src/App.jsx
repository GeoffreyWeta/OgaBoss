import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import { THEMES, applyTheme, loadTheme } from "./themes.js";
import { createContext, useContext } from "react";

const ThemeCtx = createContext({ style: "studio", mode: "light" });
const useThemeDef = () => THEMES[useContext(ThemeCtx).style] || THEMES.studio;

/* ——— shared ——— */

function NodeMark({ shape = "circle", size = 30, active }) {
  const c = active ? "#FF6B4A" : "#8B7FD4";
  return (
    <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true">
      {shape === "circle" && <circle cx="17" cy="17" r="9" fill="none" stroke={c} strokeWidth="2.5" />}
      {shape === "diamond" && <rect x="9.5" y="9.5" width="15" height="15" transform="rotate(45 17 17)" fill="none" stroke={c} strokeWidth="2.5" />}
      {shape === "square" && <rect x="9" y="9" width="16" height="16" rx="3" fill="none" stroke={c} strokeWidth="2.5" />}
      {shape === "chevron" && <path d="M9 21 L17 11 L25 21" fill="none" stroke={c} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
      {shape === "triad" && (
        <g fill={c}>
          <circle cx="17" cy="10" r="3.4" />
          <circle cx="10" cy="23" r="3.4" />
          <circle cx="24" cy="23" r="3.4" />
        </g>
      )}
    </svg>
  );
}

const STATUS_LABEL = {
  pending: "Awaiting decision",
  revision: "Team is revising",
  approved: "Executing…",
  artifact_pending: "Work ready for sign-off",
  done: "Done",
  rejected: "Rejected",
  failed: "Failed",
};

function md(text) {
  const parts = String(text || "").split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p
  );
}

/* ——— theme picker ——— */

function ThemePicker({ t, setT }) {
  const [openPanel, setOpenPanel] = useState(false);
  return (
    <>
      <button className="iconbtn" aria-label="Appearance" onClick={() => setOpenPanel(!openPanel)}>◐</button>
      {openPanel && (
        <div className="themepanel">
          <div className="modeseg">
            <button className={t.mode === "light" ? "on" : ""} onClick={() => setT({ ...t, mode: "light" })}>Light</button>
            <button className={t.mode === "dark" ? "on" : ""} onClick={() => setT({ ...t, mode: "dark" })}>Dark</button>
          </div>
          {Object.entries(THEMES).map(([id, th]) => (
            <button key={id} className={"themeopt " + (t.style === id ? "on" : "")} onClick={() => setT({ ...t, style: id })}>
              <span className="sw" style={{ background: th[t.mode]["--accent"], borderColor: th[t.mode]["--line"] }} />
              <span>
                {th.name}
                <div className="dim" style={{ fontSize: 11.5 }}>{th.hint}</div>
              </span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

/* ——— auth ——— */

function Auth({ onDone }) {
  const [mode, setMode] = useState("login"); // login | signup | forgot
  const [f, setF] = useState({ username: "", password: "", display_name: "", email: "", identifier: "" });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const switchMode = (m) => { setErr(""); setMsg(""); setMode(m); };

  async function go() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      if (mode === "forgot") {
        if (!f.identifier) { setBusy(false); return; }
        const d = await api("/auth/password/reset/", { method: "POST", body: JSON.stringify({ identifier: f.identifier }) });
        setMsg(d.note || "If an account matches, a reset link is on its way.");
        return;
      }
      if (!f.username || !f.password) { setBusy(false); return; }
      const path = mode === "login" ? "/auth/login/" : "/auth/register/";
      const body = mode === "login"
        ? { username: f.username, password: f.password }
        : { username: f.username, password: f.password, display_name: f.display_name, email: f.email };
      const d = await api(path, { method: "POST", body: JSON.stringify(body) });
      setToken(d.token);
      onDone();
      return;
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (mode === "forgot") {
    return (
      <div className="login">
        <div className="wordmark big">OgaBoss</div>
        <div className="eyebrow">Reset your password</div>
        <p className="body">Enter your username or email and we'll send a reset link.</p>
        <input className="in" placeholder="Username or email" value={f.identifier} onChange={set("identifier")} autoCapitalize="none" onKeyDown={(e) => e.key === "Enter" && go()} />
        {err && <div className="err">{err}</div>}
        {msg && <div className="body sm2" style={{ color: "var(--accent)" }}>{msg}</div>}
        <button className="btn coral" onClick={go} disabled={busy || !f.identifier}>{busy ? "…" : "Send reset link"}</button>
        <div className="row" style={{ justifyContent: "center" }}>
          <button className="btn ghost sm" onClick={() => switchMode("login")}>Back to log in</button>
        </div>
      </div>
    );
  }

  return (
    <div className="login">
      <div className="wordmark big">OgaBoss</div>
      <div className="eyebrow">Your company. Your call.</div>
      {mode === "signup" && <input className="in" placeholder="Your name" value={f.display_name} onChange={set("display_name")} />}
      <input className="in" placeholder="Username" value={f.username} onChange={set("username")} autoCapitalize="none" />
      {mode === "signup" && <input className="in" type="email" placeholder="Email (for password reset)" value={f.email} onChange={set("email")} autoCapitalize="none" />}
      <input className="in" type="password" placeholder={mode === "login" ? "Password" : "Password (8+ characters)"} value={f.password} onChange={set("password")} onKeyDown={(e) => e.key === "Enter" && go()} />
      {err && <div className="err">{err}</div>}
      <button className="btn coral" onClick={go} disabled={busy || !f.username || !f.password}>
        {busy ? "…" : mode === "login" ? "Enter the office" : "Create account"}
      </button>
      <div className="row" style={{ justifyContent: "center" }}>
        {mode === "login"
          ? <>
              <button className="btn ghost sm" onClick={() => switchMode("signup")}>Create an account</button>
              <button className="btn ghost sm" onClick={() => switchMode("forgot")}>Forgot password?</button>
            </>
          : <button className="btn ghost sm" onClick={() => switchMode("login")}>I already have an account</button>}
      </div>
    </div>
  );
}

function ResetPassword({ uid, token, onDone }) {
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (pw.length < 8) { setErr("Password must be at least 8 characters."); return; }
    if (pw !== pw2) { setErr("Passwords don't match."); return; }
    setBusy(true);
    setErr("");
    try {
      const d = await api("/auth/password/reset/confirm/", { method: "POST", body: JSON.stringify({ uid, token, new_password: pw }) });
      if (d.token) setToken(d.token);
      onDone();
    } catch (e) {
      setErr(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="wordmark big">OgaBoss</div>
      <div className="eyebrow">Set a new password</div>
      <input className="in" type="password" placeholder="New password (8+ characters)" value={pw} onChange={(e) => setPw(e.target.value)} />
      <input className="in" type="password" placeholder="Confirm new password" value={pw2} onChange={(e) => setPw2(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
      {err && <div className="err">{err}</div>}
      <button className="btn coral" onClick={submit} disabled={busy || !pw || !pw2}>{busy ? "…" : "Save new password"}</button>
    </div>
  );
}

function ChangePasswordModal({ onClose }) {
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (pw.length < 8) { setErr("New password must be at least 8 characters."); return; }
    if (pw !== pw2) { setErr("New passwords don't match."); return; }
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const d = await api("/auth/password/change/", { method: "POST", body: JSON.stringify({ current_password: cur, new_password: pw }) });
      if (d.token) setToken(d.token);
      setMsg("Password updated.");
      setCur(""); setPw(""); setPw2("");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 20 }} onClick={onClose}>
      <div className="login" style={{ margin: 0, paddingBottom: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="eyebrow">Change password</div>
        <input className="in" type="password" placeholder="Current password" value={cur} onChange={(e) => setCur(e.target.value)} />
        <input className="in" type="password" placeholder="New password (8+ characters)" value={pw} onChange={(e) => setPw(e.target.value)} />
        <input className="in" type="password" placeholder="Confirm new password" value={pw2} onChange={(e) => setPw2(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
        {err && <div className="err">{err}</div>}
        {msg && <div className="body sm2" style={{ color: "var(--accent)" }}>{msg}</div>}
        <button className="btn coral" onClick={submit} disabled={busy || !cur || !pw || !pw2}>{busy ? "…" : "Update password"}</button>
        <button className="btn ghost sm" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

function Onboarding({ onLogout, onDone }) {
  const [mode, setMode] = useState("choose"); // choose | found | join
  const [f, setF] = useState({ new_org_name: "", org_slug: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(kind) {
    setBusy(true);
    setErr("");
    try {
      if (kind === "found") {
        await api("/company/found/", { method: "POST", body: JSON.stringify({ new_org_name: f.new_org_name }) });
      } else {
        await api("/company/join/", { method: "POST", body: JSON.stringify({ org_slug: f.org_slug }) });
      }
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const backToChoose = () => { setErr(""); setMode("choose"); };

  return (
    <div className="login">
      <div className="wordmark big">OgaBoss</div>
      <div className="eyebrow">Set up your workspace</div>

      {mode === "choose" && (
        <>
          <p className="body">Create your own company and run it as CEO, or join one you've been given a code for.</p>
          <button className="btn coral" onClick={() => { setErr(""); setMode("found"); }}>Create a company</button>
          <button className="btn ghost" onClick={() => { setErr(""); setMode("join"); }}>Join a company</button>
        </>
      )}

      {mode === "found" && (
        <>
          <input className="in" placeholder="Company name" value={f.new_org_name} onChange={set("new_org_name")} onKeyDown={(e) => e.key === "Enter" && f.new_org_name && submit("found")} />
          {err && <div className="err">{err}</div>}
          <button className="btn coral" onClick={() => submit("found")} disabled={busy || !f.new_org_name}>{busy ? "…" : "Found the company"}</button>
          <button className="btn ghost sm" onClick={backToChoose}>Back</button>
        </>
      )}

      {mode === "join" && (
        <>
          <input className="in" placeholder="Company code" value={f.org_slug} onChange={set("org_slug")} autoCapitalize="none" onKeyDown={(e) => e.key === "Enter" && f.org_slug && submit("join")} />
          {err && <div className="err">{err}</div>}
          <button className="btn coral" onClick={() => submit("join")} disabled={busy || !f.org_slug}>{busy ? "…" : "Request to join"}</button>
          <button className="btn ghost sm" onClick={backToChoose}>Back</button>
        </>
      )}

      <div className="row" style={{ justifyContent: "center" }}>
        <button className="btn ghost sm" onClick={onLogout}>Log out</button>
      </div>
    </div>
  );
}

function Pending({ onLogout, onRefresh }) {
  return (
    <div className="login">
      <div className="wordmark big">OgaBoss</div>
      <div className="eyebrow">Enrollment pending</div>
      <p className="body">Your request is on the CEO's desk. Once approved, your role and department appear here.</p>
      <button className="btn coral" onClick={onRefresh}>Check again</button>
      <button className="btn ghost" onClick={onLogout}>Log out</button>
    </div>
  );
}

/* ——— desk ——— */

function ProposalItem({ p, open, idx }) {
  const def = useThemeDef();
  const hot = p.status === "pending" || p.status === "artifact_pending";
  const go = () => open("proposal", p.id);

  if (def.layout === "ledger") return (
    <button className="lrow" onClick={go}>
      <span className={"lnum" + (hot ? "" : " off")}>{String(idx + 1).padStart(2, "0")}</span>
      <span className="grow">
        <span className="nm">{p.title}</span>
        <div className="rl">{p.proposed_by || ""}{p.assigned_to && p.assigned_to !== p.proposed_by ? ` · executes ${p.assigned_to}` : ""} — {STATUS_LABEL[p.status]}</div>
        <div className="md2">{p.summary.slice(0, 130)}{p.summary.length > 130 ? "…" : ""}</div>
        {hot && <div className="lact">{p.status === "pending" ? "Decide →" : "Sign & release →"}</div>}
      </span>
    </button>
  );

  if (def.layout === "files") return (
    <button className="frow" onClick={go}>
      <span className="ftab">Case {String(p.id).padStart(3, "0")} · {(p.proposed_by || "—").toUpperCase()}</span>
      <div className="fbody">
        <span className={"fstamp" + (hot ? "" : " off")}>{hot ? (p.status === "pending" ? "PENDING" : "SIGN-OFF") : STATUS_LABEL[p.status].toUpperCase()}</span>
        <div className="nm" style={{ paddingRight: 76 }}>{p.title}</div>
        <div className="md2">{p.summary.slice(0, 120)}{p.summary.length > 120 ? "…" : ""}</div>
      </div>
    </button>
  );

  if (def.layout === "term") return (
    <button className="trow" onClick={go}>
      <div className="nm">» {p.title}</div>
      <div className="rl">agent: {(p.proposed_by || "—").toUpperCase()}{p.assigned_to && p.assigned_to !== p.proposed_by ? ` → ${p.assigned_to.toUpperCase()}` : ""} · status: {p.status.toUpperCase()}</div>
      {hot && <div className="tact">[{p.status === "pending" ? "DECIDE" : "SIGN-OFF"}]</div>}
    </button>
  );

  if (def.layout === "stamps") return (
    <button className="brow" onClick={go}>
      <span className={"btag" + (hot ? "" : " off")}>{hot ? (p.status === "pending" ? "Decide" : "Sign-off") : STATUS_LABEL[p.status]}</span>
      <div className="nm" style={{ paddingRight: 70 }}>{p.title}</div>
      <div className="rl">{p.proposed_by || ""}{p.assigned_to && p.assigned_to !== p.proposed_by ? ` → ${p.assigned_to}` : ""}</div>
      <div className="md2">{p.summary.slice(0, 120)}{p.summary.length > 120 ? "…" : ""}</div>
    </button>
  );

  return (
    <button className="card" onClick={go}>
      <span className="grow">
        <span className="nm">{p.title}</span>
        <div className="rl">
          {p.proposed_by ? `Proposed by ${p.proposed_by}` : ""}
          {p.assigned_to && p.assigned_to !== p.proposed_by ? ` · executes: ${p.assigned_to}` : ""}
        </div>
        <div className="md2">{p.summary.slice(0, 140)}{p.summary.length > 140 ? "…" : ""}</div>
      </span>
      <span className={"pill " + (hot ? "hot" : "")}>{STATUS_LABEL[p.status]}</span>
    </button>
  );
}

function Desk({ open, me }) {
  const def = useThemeDef();
  const S = def.strings;
  const [data, setData] = useState(null);
  const [directive, setDirective] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(() => api("/desk/").then(setData).catch(() => {}), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  async function sendDirective() {
    const text = directive.trim();
    if (!text) return;
    setBusy(true);
    try {
      await api("/directives/", { method: "POST", body: JSON.stringify({ text }) });
      setDirective("");
      setNote("Routed to the right team — deliberation is running. It'll land here.");
      setTimeout(() => setNote(""), 6000);
      load();
    } catch (e) {
      setNote(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function daily() {
    setBusy(true);
    try {
      await api("/daily/", { method: "POST" });
      setNote("Daily cycle running — proactive ideas and standing orders incoming.");
      setTimeout(() => setNote(""), 6000);
    } catch (e) {
      setNote(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <div className="pad dim">Opening the desk…</div>;

  const Section = ({ title, items, empty }) => (
    <>
      <div className="deptlbl">{title}{def.layout === "ledger" ? ` — ${items.length}` : ""}</div>
      {items.length === 0 && <div className="empty">{empty}</div>}
      <div className={def.layout === "bento" ? "items bgrid" : "items"}>
        {items.map((p, i) => <ProposalItem key={p.id} p={p} open={open} idx={i} />)}
      </div>
    </>
  );

  return (
    <div className="pad">
      {(def.layout === "stack" || def.layout === "bento") && (
        <div className="pulse">
          <div><div className="pv">{data.pending.length}</div><div className="pk">need you</div></div>
          <div><div className="pv">{data.working.length}</div><div className="pk">in flight</div></div>
          <div><div className="pv">{data.recent.filter((p) => p.status === "done").length}</div><div className="pk">done</div></div>
        </div>
      )}
      {me.is_ceo && (
        <div className="composer">
          <textarea className="in" rows={2} value={directive}
            placeholder={S.directive}
            onChange={(e) => setDirective(e.target.value)} />
          <div className="row">
            <button className="btn coral" onClick={sendDirective} disabled={busy || !directive.trim()}>{S.send}</button>
            <button className="btn ghost" onClick={daily} disabled={busy}>{S.daily}</button>
          </div>
          {note && <div className="note">{note}</div>}
        </div>
      )}
      <Section title={S.pending} items={data.pending} empty="Nothing waiting." />
      <Section title={S.working} items={data.working} empty="Nothing executing right now." />
      <Section title={S.recent} items={data.recent} empty="No history yet." />
    </div>
  );
}

/* ——— proposal ——— */

function ProposalView({ id, back, me }) {
  const [p, setP] = useState(null);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDelib, setShowDelib] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(() => api(`/proposals/${id}/`).then(setP).catch((e) => setErr(e.message)), [id]);
  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  async function decide(action) {
    setBusy(true);
    setErr("");
    try {
      await api(`/proposals/${id}/decide/`, { method: "POST", body: JSON.stringify({ action, feedback }) });
      setFeedback("");
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function decideArtifact(aid, action) {
    setBusy(true);
    setErr("");
    try {
      await api(`/artifacts/${aid}/decide/`, { method: "POST", body: JSON.stringify({ action, feedback }) });
      setFeedback("");
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!p) return <div className="pad dim">{err || "Loading…"}</div>;

  const pendingArtifact = p.artifacts.find((a) => a.status === "pending");
  const canDecide = me.is_ceo || me.role === "head";

  return (
    <div className="pad">
      <button className="btn ghost sm" onClick={back}>← Back</button>
      <h2 className="h2">{p.title}</h2>
      <div className="rl">
        {p.proposed_by && `Proposed by ${p.proposed_by}`}
        {p.assigned_to && ` · executes: ${p.assigned_to}`} · <span className="pill hot">{STATUS_LABEL[p.status]}</span>
      </div>
      <p className="body">{md(p.summary)}</p>

      {p.rationale && (
        <div className="panel">
          <div className="eyebrow">How they got here</div>
          <p className="body sm2">{md(p.rationale)}</p>
        </div>
      )}

      {p.deliberation && (
        <div className="panel">
          <button className="btn ghost sm" onClick={() => setShowDelib(!showDelib)}>
            {showDelib ? "Hide meeting transcript" : `Read the meeting (${p.deliberation.messages.length} contributions)`}
          </button>
          {showDelib &&
            p.deliberation.messages.map((m, i) => (
              <div key={i} className="msg them">
                <div className="who">{m.agent} · {m.role}</div>
                {md(m.content)}
              </div>
            ))}
        </div>
      )}

      {p.artifacts.map((a) => (
        <div key={a.id} className="panel">
          <div className="eyebrow">Deliverable — {a.agent} · {a.status}{a.delivery ? ` · sent: ${a.delivery}` : ""}</div>
          <div className="nm">{a.title}</div>
          {a.kind === "html" ? (
            <iframe className="artframe" sandbox="" srcDoc={a.content} title={a.title} />
          ) : (
            <pre className="artpre">{a.content}</pre>
          )}
        </div>
      ))}

      {err && <div className="err">{err}</div>}

      {canDecide && (p.status === "pending" || pendingArtifact) && (
        <div className="decide">
          <textarea className="in" rows={2} value={feedback}
            placeholder="Optional notes — required if you send it back…"
            onChange={(e) => setFeedback(e.target.value)} />
          {p.status === "pending" ? (
            <div className="row">
              <button className="btn coral" disabled={busy} onClick={() => decide("approve")}>Approve — execute</button>
              <button className="btn ghost" disabled={busy || !feedback.trim()} onClick={() => decide("tweak")}>Send back with notes</button>
              <button className="btn ghost" disabled={busy} onClick={() => decide("reject")}>Reject</button>
            </div>
          ) : me.is_ceo ? (
            <div className="row">
              <button className="btn coral" disabled={busy} onClick={() => decideArtifact(pendingArtifact.id, "approve")}>Approve deliverable</button>
              <button className="btn ghost" disabled={busy || !feedback.trim()} onClick={() => decideArtifact(pendingArtifact.id, "redo")}>Redo with notes</button>
            </div>
          ) : (
            <div className="note">Final sign-off is with the CEO.</div>
          )}
        </div>
      )}
      {me.is_ceo && p.status === "failed" && (
        <div className="row">
          <button className="btn coral" disabled={busy} onClick={() => decide("approve")}>Retry execution</button>
        </div>
      )}
    </div>
  );
}

/* ——— meet ——— */

function Meet({ open }) {
  const [meetings, setMeetings] = useState([]);
  const [agents, setAgents] = useState([]);
  const [topic, setTopic] = useState("");
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(() => api("/meetings/").then((d) => setMeetings(d.meetings)).catch(() => {}), []);
  useEffect(() => {
    load();
    api("/org/").then((d) => setAgents(d.agents.filter((a) => !a.is_human && a.active))).catch(() => {});
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  async function convene() {
    setBusy(true);
    setErr("");
    try {
      const d = await api("/meetings/", { method: "POST", body: JSON.stringify({ topic, agent_ids: picked }) });
      setTopic("");
      setPicked([]);
      open("meeting", d.deliberation_id);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pad">
      <div className="deptlbl">Convene a room</div>
      <textarea className="in" rows={2} value={topic} placeholder="Topic — e.g. Should our pricing page lead with the free pilot?" onChange={(e) => setTopic(e.target.value)} />
      <div style={{ marginTop: 10 }}>
        {agents.map((a) => (
          <button key={a.id} className={"chip " + (picked.includes(a.id) ? "on" : "")}
            onClick={() => setPicked(picked.includes(a.id) ? picked.filter((x) => x !== a.id) : [...picked, a.id])}>
            {a.name} <span className="dim">· {a.role.split(" ")[0]}</span>
          </button>
        ))}
      </div>
      {err && <div className="err">{err}</div>}
      <button className="btn coral" onClick={convene} disabled={busy || !topic.trim() || picked.length === 0}>
        {busy ? "Convening…" : `Start meeting (${picked.length} in the room)`}
      </button>

      <div className="deptlbl">Recent meetings</div>
      {meetings.length === 0 && <div className="empty">No meetings yet.</div>}
      {meetings.map((m) => (
        <button key={m.id} className="card" onClick={() => open("meeting", m.id)}>
          <span className="grow">
            <span className="nm">{m.topic}</span>
            <div className="rl">{new Date(m.created_at).toLocaleString()}</div>
          </span>
          <span className={"pill " + (m.status === "running" ? "hot" : "")}>{m.status}</span>
        </button>
      ))}
    </div>
  );
}

function MeetingView({ id, back, open }) {
  const [d, setD] = useState(null);
  const load = useCallback(() => api(`/deliberations/${id}/`).then(setD).catch(() => {}), [id]);
  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);
  if (!d) return <div className="pad dim">Loading…</div>;
  return (
    <div className="pad">
      <button className="btn ghost sm" onClick={back}>← Meetings</button>
      <h2 className="h2">{d.topic}</h2>
      <div className="rl"><span className={"pill " + (d.status === "running" ? "hot" : "")}>{d.status}</span></div>
      {d.messages.map((m, i) => (
        <div key={i} className="msg them">
          <div className="who">{m.agent} · {m.role}</div>
          {md(m.content)}
        </div>
      ))}
      {d.status === "running" && <div className="msg them dim">The room is still talking…</div>}
      {d.error && <div className="err">{d.error}</div>}
      {d.proposal_ids.map((pid) => (
        <button key={pid} className="btn coral" onClick={() => open("proposal", pid)}>Open the resulting proposal →</button>
      ))}
    </div>
  );
}

/* ——— team ——— */

function Team({ open, me }) {
  const [agents, setAgents] = useState(null);
  useEffect(() => {
    api("/org/").then((d) => setAgents(d.agents)).catch(() => {});
  }, []);
  if (!agents) return <div className="pad dim">Loading the team…</div>;
  const visible = agents.filter((a) => a.active);
  const depts = [...new Set(visible.map((a) => a.department))];
  return (
    <div className="pad">
      {me.is_ceo && (
        <button className="btn ghost" onClick={() => open("agent-new", null)}>+ Hire a new agent</button>
      )}
      {depts.map((d) => (
        <div key={d}>
          <div className="deptlbl">{d}</div>
          {visible.filter((a) => a.department === d).map((a) => (
            <TeamRow key={a.id} a={a} visible={visible} me={me} open={open} />
          ))}
        </div>
      ))}
    </div>
  );
}

function TeamRow({ a, visible, me, open }) {
  const def = useThemeDef();
  if (def.layout === "ledger" || def.layout === "files") {
    return (
      <div className="trow-ledger">
        <button className="grow" style={{ all: "unset", cursor: a.is_human ? "default" : "pointer", flex: 1, minWidth: 0 }}
          onClick={() => !a.is_human && open("chat", a.id)}>
          <span className="nm">{def.layout === "files" ? `${String(a.id).padStart(2, "0")} · ` : ""}{a.name}{a.is_human ? " 👤" : ""}</span>
          <span className="rl" style={{ marginLeft: 8 }}>{a.role}</span>
        </button>
        {me.is_ceo && <button className="iconbtn" title="Edit" onClick={() => open("agent-edit", a.id)}>✎</button>}
      </div>
    );
  }
  return (
    <OldTeamCard key={a.id} a={a} visible={visible} me={me} open={open} />
  );
}

function OldTeamCard({ a, visible, me, open }) {
  return (
    <div className="card" style={{ cursor: "default" }}>
              <NodeMark shape={a.shape} active={a.is_head} />
              <button className="grow" style={{ all: "unset", cursor: a.is_human ? "default" : "pointer", flex: 1, minWidth: 0 }}
                onClick={() => !a.is_human && open("chat", a.id)}>
                <span className="nm">{a.name}{a.is_human ? " 👤" : ""}</span>
                <div className="rl">{a.role}{a.reports_to ? ` · reports to ${visible.find((x) => x.id === a.reports_to)?.name || "—"}` : ""}</div>
                <div className="md2">{a.mandate}</div>
              </button>
              {a.is_human ? <span className="pill">human</span>
                : a.capabilities?.some((c) => c.kind === "web_research") ? <span className="pill">web</span>
                : a.proactive ? <span className="pill">daily ideas</span> : null}
      {me.is_ceo && <button className="iconbtn" title="Edit" onClick={() => open("agent-edit", a.id)}>✎</button>}
    </div>
  );
}

const SHAPES = ["circle", "diamond", "square", "chevron", "triad"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function AgentEditor({ id, back }) {
  const isNew = !id;
  const [a, setA] = useState(isNew ? {
    name: "", role: "", department: "", mandate: "", persona: "",
    shape: "circle", is_head: false, proactive: false, active: true, reports_to: null,
  } : null);
  const [all, setAll] = useState([]);
  const [orders, setOrders] = useState([]);
  const [order, setOrder] = useState({ instruction: "", cadence: "weekly", weekday: 0 });
  const [caps, setCaps] = useState([]);
  const [cap, setCap] = useState({ kind: "data_source", label: "", url: "", auth_header: "", notes: "" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/org/").then((d) => setAll(d.agents)).catch(() => {});
    if (!isNew) {
      api(`/agents/${id}/`).then(setA).catch(() => {});
      api("/orders/").then((d) => setOrders(d.orders.filter((o) => o.agent_id === id))).catch(() => {});
      api(`/agents/${id}/capabilities/`).then((d) => setCaps(d.capabilities)).catch(() => {});
    }
  }, [id, isNew]);

  if (!a) return <div className="pad dim">Loading…</div>;
  const set = (k) => (e) => setA({ ...a, [k]: e.target.value });
  const toggle = (k) => () => setA({ ...a, [k]: !a[k] });

  async function save() {
    setBusy(true);
    setNote("");
    try {
      if (isNew) {
        await api("/agents/", { method: "POST", body: JSON.stringify(a) });
        setNote("Hired. They're on the org chart.");
        setTimeout(back, 800);
      } else {
        await api(`/agents/${id}/`, { method: "PUT", body: JSON.stringify(a) });
        setNote("Saved — takes effect on their next thought.");
      }
    } catch (e) {
      setNote(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function deactivate() {
    setBusy(true);
    try {
      await api(`/agents/${id}/`, { method: "DELETE" });
      back();
    } catch (e) {
      setNote(e.message);
      setBusy(false);
    }
  }

  async function addCap() {
    try {
      const d = await api(`/agents/${id}/capabilities/`, { method: "POST", body: JSON.stringify(cap) });
      setCaps(d.capabilities);
      setCap({ kind: "data_source", label: "", url: "", auth_header: "", notes: "" });
    } catch (e) {
      setNote(e.message);
    }
  }

  async function removeCap(cid) {
    try {
      await api(`/capabilities/${cid}/`, { method: "DELETE" });
      setCaps(caps.filter((c) => c.id !== cid));
    } catch (e) {
      setNote(e.message);
    }
  }

  async function addOrder() {
    try {
      const d = await api("/orders/", {
        method: "POST",
        body: JSON.stringify({ agent: id, instruction: order.instruction, cadence: order.cadence, weekday: Number(order.weekday) }),
      });
      setOrders(d.orders.filter((o) => o.agent_id === id));
      setOrder({ ...order, instruction: "" });
    } catch (e) {
      setNote(e.message);
    }
  }

  async function removeOrder(oid) {
    try {
      await api(`/orders/${oid}/`, { method: "DELETE" });
      setOrders(orders.filter((o) => o.id !== oid));
    } catch (e) {
      setNote(e.message);
    }
  }

  return (
    <div className="pad">
      <button className="btn ghost sm" onClick={back}>← Team</button>
      <h2 className="h2">{isNew ? "Hire a new agent" : `${a.name} — dossier`}</h2>
      {a.is_human && <div className="note">This is a real person's seat — edit the title, not the mind.</div>}

      <div className="fieldlbl">Name</div>
      <input className="in" value={a.name} onChange={set("name")} />
      <div className="fieldlbl">Role / title</div>
      <input className="in" value={a.role} onChange={set("role")} />
      <div className="fieldlbl">Department</div>
      <input className="in" value={a.department} onChange={set("department")} placeholder="e.g. Marketing" />
      <div className="fieldlbl">Mandate (one line)</div>
      <input className="in" value={a.mandate} onChange={set("mandate")} />
      {!a.is_human && (
        <>
          <div className="fieldlbl">Persona — who they are: character, expertise, experience, perspective</div>
          <textarea className="in" rows={7} value={a.persona} onChange={set("persona")}
            placeholder="World-class …, background in …, believes …, always …" />
        </>
      )}
      <div className="fieldlbl">Reports to</div>
      <select className="in" value={a.reports_to || ""} onChange={(e) => setA({ ...a, reports_to: e.target.value ? Number(e.target.value) : null })}>
        <option value="">— No one (top level)</option>
        {all.filter((x) => x.id !== id && x.active).map((x) => (
          <option key={x.id} value={x.id}>{x.name} — {x.role}</option>
        ))}
      </select>
      <div className="fieldlbl">Avatar shape</div>
      <div>
        {SHAPES.map((s) => (
          <button key={s} className={"chip " + (a.shape === s ? "on" : "")} onClick={() => setA({ ...a, shape: s })}>
            <NodeMark shape={s} size={18} active={a.shape === s} /> {s}
          </button>
        ))}
      </div>
      {!a.is_human && (
        <div className="row">
          <label className="toggle"><input type="checkbox" checked={a.is_head} onChange={toggle("is_head")} /> Department head</label>
          <label className="toggle"><input type="checkbox" checked={a.proactive} onChange={toggle("proactive")} /> Daily ideas</label>
        </div>
      )}


      {!isNew && !a.is_human && (
        <>
          <div className="fieldlbl">Connections &amp; powers — plug in tools, no code needed</div>
          {caps.map((c) => (
            <div key={c.id} className="subcard">
              <span className="grow">
                <span style={{ fontWeight: 500 }}>{c.label}</span>
                <span className="dim"> · {c.kind === "data_source" ? "reads live data" : c.kind === "webhook" ? "sends approved work out" : c.kind === "web_research" ? "searches the web" : "standing knowledge"}</span>
                {c.url && <div className="dim" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.url}{c.has_auth ? " · 🔑" : ""}</div>}
              </span>
              <button className="iconbtn" onClick={() => removeCap(c.id)}>✕</button>
            </div>
          ))}
          <div className="row">
            <select className="in" style={{ width: "auto" }} value={cap.kind} onChange={(e) => setCap({ ...cap, kind: e.target.value })}>
              <option value="data_source">Data source (read an API)</option>
              <option value="web_research">Web research</option>
              <option value="webhook">Outbound (post approved work)</option>
              <option value="web_note">Standing knowledge</option>
            </select>
            <input className="in grow" placeholder="Label — e.g. Google Analytics, Instagram" value={cap.label} onChange={(e) => setCap({ ...cap, label: e.target.value })} />
          </div>
          {(cap.kind === "data_source" || cap.kind === "webhook") && (
            <>
              <input className="in" style={{ marginTop: 8 }} placeholder="API URL — e.g. https://graph.facebook.com/v19.0/me/media?fields=…" value={cap.url} onChange={(e) => setCap({ ...cap, url: e.target.value })} />
              <input className="in" style={{ marginTop: 8 }} placeholder="Auth header (optional) — e.g. Authorization: Bearer YOUR_TOKEN" value={cap.auth_header} onChange={(e) => setCap({ ...cap, auth_header: e.target.value })} />
            </>
          )}
          {cap.kind === "web_note" && (
            <textarea className="in" style={{ marginTop: 8 }} rows={2} placeholder="What should they always know?" value={cap.notes} onChange={(e) => setCap({ ...cap, notes: e.target.value })} />
          )}
          <div className="row"><button className="btn ghost" onClick={addCap} disabled={!cap.label.trim()}>Connect</button></div>
        </>
      )}
      {!isNew && !a.is_human && (
        <>
          <div className="fieldlbl">Standing orders — recurring work, no asking needed</div>
          {orders.map((o) => (
            <div key={o.id} className="subcard">
              <span className="grow">{o.instruction} <span className="dim">· {o.cadence === "daily" ? "every day" : `every ${WEEKDAYS[o.weekday]}`}</span></span>
              <button className="iconbtn" onClick={() => removeOrder(o.id)}>✕</button>
            </div>
          ))}
          <div className="row">
            <input className="in grow" placeholder="e.g. One event flyer for this week's featured event" value={order.instruction} onChange={(e) => setOrder({ ...order, instruction: e.target.value })} />
          </div>
          <div className="row">
            <select className="in" style={{ width: "auto" }} value={order.cadence} onChange={(e) => setOrder({ ...order, cadence: e.target.value })}>
              <option value="weekly">Weekly</option>
              <option value="daily">Daily</option>
            </select>
            {order.cadence === "weekly" && (
              <select className="in" style={{ width: "auto" }} value={order.weekday} onChange={(e) => setOrder({ ...order, weekday: e.target.value })}>
                {WEEKDAYS.map((w, i) => <option key={w} value={i}>{w}</option>)}
              </select>
            )}
            <button className="btn ghost" onClick={addOrder} disabled={!order.instruction.trim()}>Add order</button>
          </div>
        </>
      )}

      {note && <div className="note" style={{ marginTop: 10 }}>{note}</div>}
      <div className="row">
        <button className="btn coral" onClick={save} disabled={busy || !a.name || !a.role}>{isNew ? "Hire" : "Save changes"}</button>
        {!isNew && <button className="btn ghost" onClick={deactivate} disabled={busy}>Deactivate</button>}
      </div>
    </div>
  );
}

/* ——— chat ——— */

function Chat({ id, back }) {
  const [data, setData] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    api(`/agents/${id}/chat/`).then(setData).catch(() => {});
  }, [id]);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [data, busy]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setData((d) => ({ ...d, messages: [...d.messages, { role: "user", content: text }] }));
    try {
      const d = await api(`/agents/${id}/chat/`, { method: "POST", body: JSON.stringify({ text }) });
      setData(d);
    } catch (e) {
      setData((d) => ({ ...d, messages: [...d.messages, { role: "assistant", content: e.message }] }));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <div className="pad dim">Loading…</div>;
  const a = data.agent;
  return (
    <div className="chatwrap">
      <div className="chathead2">
        <button className="btn ghost sm" onClick={back}>←</button>
        <NodeMark shape={a.shape} active size={26} />
        <div>
          <div className="nm">{a.name}</div>
          <div className="rl">{a.role}</div>
        </div>
      </div>
      <div className="scrollarea" ref={scrollRef}>
        {data.messages.length === 0 && <div className="empty">This conversation is remembered — pick it up any time.</div>}
        {data.messages.map((m, i) => (
          <div key={i} className={"msg " + (m.role === "user" ? "me" : "them")}>{md(m.content)}</div>
        ))}
        {busy && <div className="msg them dim">…</div>}
      </div>
      <div className="bar">
        <textarea className="in grow" rows={1} value={input} placeholder={`Message ${a.name}…`}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }} />
        <button className="btn coral" onClick={send} disabled={busy || !input.trim()}>Send</button>
      </div>
    </div>
  );
}

/* ——— admin ——— */

function Admin() {
  const [members, setMembers] = useState([]);
  const [pols, setPols] = useState([]);
  const [usage, setUsage] = useState(null);
  const [content, setContent] = useState("");
  const [playbook, setPlaybook] = useState("");
  const [note, setNote] = useState("");
  const [drafts, setDrafts] = useState({}); // member id -> {role, department}

  const load = useCallback(() => {
    api("/members/").then((d) => setMembers(d.members)).catch(() => {});
    api("/policies/").then((d) => setPols(d.policies)).catch(() => {});
    api("/usage/").then(setUsage).catch(() => {});
    api("/constitution/").then((d) => setContent(d.content)).catch(() => {});
    api("/playbook/").then((d) => setPlaybook(d.playbook)).catch(() => {});
  }, []);
  useEffect(load, [load]);

  async function decide(m, action) {
    const d = drafts[m.id] || { role: "member", department: "" };
    try {
      await api(`/members/${m.id}/`, { method: "POST", body: JSON.stringify({ action, ...d }) });
      load();
    } catch (e) {
      setNote(e.message);
    }
  }

  async function saveConst() {
    try {
      await api("/constitution/", { method: "PUT", body: JSON.stringify({ content }) });
      setNote("Constitution saved — every agent now acts on this.");
      setTimeout(() => setNote(""), 4000);
    } catch (e) {
      setNote(e.message);
    }
  }

  async function setPolicy(dep, field, value) {
    const cur = pols.find((x) => x.department === dep);
    try {
      const d = await api("/policies/", { method: "POST", body: JSON.stringify({ department: dep, proposal_approval: field === "p" ? value : cur.proposal_approval, artifact_approval: field === "a" ? value : cur.artifact_approval }) });
      setPols(d.policies);
    } catch (e) {
      setNote(e.message);
    }
  }

  const pending = members.filter((m) => m.status === "pending");
  const active = members.filter((m) => m.status === "active");

  return (
    <div className="pad">
      <div className="deptlbl">People — enrollment</div>
      {pending.length === 0 && <div className="empty">No pending requests.</div>}
      {pending.map((m) => (
        <div key={m.id} className="panel">
          <div className="nm">{m.display_name} <span className="dim">@{m.username}</span></div>
          <div className="row">
            <select className="in" style={{ width: "auto" }}
              value={(drafts[m.id] || {}).role || "member"}
              onChange={(e) => setDrafts({ ...drafts, [m.id]: { ...(drafts[m.id] || {}), role: e.target.value } })}>
              <option value="member">Member (view only)</option>
              <option value="head">Department head (decides their dept)</option>
            </select>
            <input className="in" style={{ width: 150 }} placeholder="Department"
              value={(drafts[m.id] || {}).department || ""}
              onChange={(e) => setDrafts({ ...drafts, [m.id]: { ...(drafts[m.id] || {}), department: e.target.value } })} />
            <button className="btn coral sm" onClick={() => decide(m, "approve")}>Enroll</button>
            <button className="btn ghost sm" onClick={() => decide(m, "remove")}>Decline</button>
          </div>
        </div>
      ))}
      {active.map((m) => (
        <div key={m.id} className="subcard">
          <span className="grow">{m.display_name} <span className="dim">@{m.username} · {m.role}{m.department ? ` of ${m.department}` : ""}</span></span>
          {m.role !== "ceo" && <button className="iconbtn" title="Remove" onClick={() => decide(m, "remove")}>✕</button>}
        </div>
      ))}

      <div className="deptlbl">Approvals — who signs what, per department</div>
      <div className="note" style={{ marginBottom: 8 }}>Internal proposals can be delegated — even to an AI manager. Deliverables that leave HQ always need a human signature.</div>
      {pols.map((pl) => (
        <div key={pl.department} className="panel" style={{ margin: "8px 0" }}>
          <div className="nm" style={{ fontSize: 14.5 }}>{pl.department}</div>
          <div className="row">
            <span className="dim" style={{ fontSize: 12.5 }}>Proposals:</span>
            <select className="in" style={{ width: "auto" }} value={pl.proposal_approval} onChange={(e) => setPolicy(pl.department, "p", e.target.value)}>
              <option value="ceo">CEO decides</option>
              <option value="head" disabled={!pl.has_human_head}>Human head decides{pl.has_human_head ? "" : " (none enrolled)"}</option>
              <option value="ai_manager" disabled={!pl.has_ai_managers}>AI manager auto-approves{pl.has_ai_managers ? "" : " (no AI manager)"}</option>
            </select>
          </div>
          <div className="row">
            <span className="dim" style={{ fontSize: 12.5 }}>Deliverables:</span>
            <select className="in" style={{ width: "auto" }} value={pl.artifact_approval} onChange={(e) => setPolicy(pl.department, "a", e.target.value)}>
              <option value="ceo">CEO signs</option>
              <option value="head" disabled={!pl.has_human_head}>Human head signs{pl.has_human_head ? "" : " (none enrolled)"}</option>
            </select>
          </div>
        </div>
      ))}

      <div className="deptlbl">Payroll — {usage?.month || "this month"}</div>
      {!usage || usage.rows.length === 0 ? (
        <div className="empty">No spend yet. Every agent thought will show up here, priced.</div>
      ) : (
        <>
          <table className="tbl">
            <thead><tr><th>Agent</th><th>Dept</th><th style={{ textAlign: "right" }}>Tokens</th><th style={{ textAlign: "right" }}>Est. USD</th></tr></thead>
            <tbody>
              {usage.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.agent}</td><td className="dim">{r.department}</td>
                  <td className="num">{((r.input_tokens + r.output_tokens) / 1000).toFixed(1)}k</td>
                  <td className="num">${r.est_usd.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="note" style={{ marginTop: 8 }}>Total ≈ ${usage.total_est_usd} this month (estimate).</div>
        </>
      )}

      <div className="deptlbl">Constitution</div>
      <textarea className="in const" style={{ minHeight: 260 }} value={content} onChange={(e) => setContent(e.target.value)} />
      <div className="row">
        <button className="btn coral" onClick={saveConst}>Save constitution</button>
        {note && <span className="note">{note}</span>}
      </div>
      <div className="panel">
        <div className="eyebrow">What the company has learned about you</div>
        <p className="body sm2">{playbook || "Nothing yet — this fills itself as you approve, tweak, and reject."}</p>
      </div>
    </div>
  );
}

/* ——— shell ——— */

export default function App() {
  const [theme, setTheme] = useState(loadTheme());
  useEffect(() => { applyTheme(theme); }, [theme]);
  const [authed, setAuthed] = useState(!!getToken());
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState("desk");
  const [detail, setDetail] = useState(null);
  const [pwOpen, setPwOpen] = useState(false);
  const [reset, setReset] = useState(() => {
    try {
      const url = new URL(window.location.href);
      if (url.pathname.replace(/\/+$/, "") === "/reset") {
        const uid = url.searchParams.get("uid");
        const token = url.searchParams.get("token");
        if (uid && token) return { uid, token };
      }
    } catch (e) { /* ignore malformed URL */ }
    return null;
  });

  const loadMe = useCallback(() => {
    if (!getToken()) return;
    api("/me/").then(setMe).catch(() => {});
  }, []);
  useEffect(() => {
    if (authed) loadMe();
  }, [authed, loadMe]);

  function logout() {
    setToken("");
    setAuthed(false);
    setMe(null);
    setDetail(null);
    setTab("desk");
  }

  if (reset) return <ThemeCtx.Provider value={theme}><div className="hq"><ResetPassword uid={reset.uid} token={reset.token} onDone={() => { try { window.history.replaceState({}, "", "/"); } catch (e) { /* ignore */ } setReset(null); setAuthed(true); loadMe(); }} /></div></ThemeCtx.Provider>;
  if (!authed) return <ThemeCtx.Provider value={theme}><div className="hq"><Auth onDone={() => setAuthed(true)} /></div></ThemeCtx.Provider>;
  if (!me) return <div className="hq"><div className="pad dim" style={{ margin: "auto" }}>Opening HQ…</div></div>;
  if (!me.status || me.status === "none") return <div className="hq"><Onboarding onLogout={logout} onDone={loadMe} /></div>;
  if (me.status !== "active") return <div className="hq"><Pending onLogout={logout} onRefresh={loadMe} /></div>;

  const open = (kind, id) => setDetail({ kind, id });
  const back = () => setDetail(null);

  const tabs = [["desk", "Desk"]];
  if (me.is_ceo || me.role === "head") tabs.push(["meet", "Meet"]);
  tabs.push(["team", "Team"]);
  if (me.is_ceo) tabs.push(["admin", "Admin"]);

  return (
    <ThemeCtx.Provider value={theme}>
    <div className="hq">
      <div className="top">
        <div className="wordmark">OgaBoss<span>.</span></div>
        <div className="eyebrow grow">{me.is_ceo ? "CEO's office" : me.role === "head" ? `Head — ${me.department}` : "Member"}</div>
        <ThemePicker t={theme} setT={setTheme} />
        <button className="btn ghost sm" onClick={() => setPwOpen(true)}>Password</button>
        <button className="btn ghost sm" onClick={logout}>Log out</button>
      </div>
      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}
      <div className="content">
        {detail?.kind === "proposal" ? (
          <ProposalView id={detail.id} back={back} me={me} />
        ) : detail?.kind === "meeting" ? (
          <MeetingView id={detail.id} back={back} open={open} />
        ) : detail?.kind === "chat" ? (
          <Chat id={detail.id} back={back} />
        ) : detail?.kind === "agent-edit" ? (
          <AgentEditor id={detail.id} back={back} />
        ) : detail?.kind === "agent-new" ? (
          <AgentEditor id={null} back={back} />
        ) : tab === "desk" ? (
          <Desk open={open} me={me} />
        ) : tab === "meet" ? (
          <Meet open={open} />
        ) : tab === "team" ? (
          <Team open={open} me={me} />
        ) : (
          <Admin />
        )}
      </div>
      {!detail && (
        <nav className="tabs">
          {tabs.map(([k, label]) => (
            <button key={k} className={"tab " + (tab === k ? "on" : "")} onClick={() => setTab(k)}>{label}</button>
          ))}
        </nav>
      )}
    </div>
    </ThemeCtx.Provider>
  );
}
