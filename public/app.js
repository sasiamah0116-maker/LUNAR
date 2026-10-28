(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const SHORT = { joyful: "Joyful", good: "Good", victory: "Victory", evil: "EVIL", full: "Full" };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} },
  };

  let tz = store.get("lunar.tz") || browserTz;
  let types = {};
  let monthDays = [];
  let today = null;
  let view = null; // {y, m}
  let selected = null;

  // Draws the lit part of the Moon for an elongation e (0 = new, 180 = full).
  function moonSVG(e) {
    const r = 45, c = 50, rad = (e * Math.PI) / 180;
    const rx = Math.abs(Math.cos(rad)) * r;
    const litRight = e < 180, crescent = Math.cos(rad) > 0;
    const s1 = litRight ? 1 : 0;
    const s2 = litRight ? (crescent ? 0 : 1) : (crescent ? 1 : 0);
    const lit = `M${c},${c - r} A${r},${r} 0 0 ${s1} ${c},${c + r} A${rx},${r} 0 0 ${s2} ${c},${c - r} Z`;
    return `<svg viewBox="0 0 100 100" role="img" aria-label="Moon phase">
      <defs><radialGradient id="g${Math.round(e)}" cx="40%" cy="35%"><stop offset="0" stop-color="#fff8dc"/><stop offset="1" stop-color="#e8cf86"/></radialGradient></defs>
      <circle cx="${c}" cy="${c}" r="${r}" fill="#1c2242" stroke="rgba(255,255,255,.12)"/>
      <path d="${lit}" fill="url(#g${Math.round(e)})"/>
    </svg>`;
  }

  const fmtDate = (iso, opts) => new Date(iso + "T12:00:00").toLocaleDateString(undefined, opts);
  const fmtTime = (iso) => new Date(iso).toLocaleString(undefined, { timeZone: tz, weekday: "short", hour: "numeric", minute: "2-digit" });

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }

  async function loadMonth() {
    const data = await api(`/api/month?y=${view.y}&m=${view.m}&tz=${encodeURIComponent(tz)}`);
    types = data.types;
    today = data.today;
    monthDays = data.days;
    renderGrid();
  }

  function renderHero(d) {
    const t = types[d.type];
    $("heroMoon").innerHTML = moonSVG(d.elongation);
    $("heroDate").textContent = "Today · " + fmtDate(d.date, { weekday: "long", month: "long", day: "numeric" });
    $("heroType").textContent = (d.type === "evil" ? "⛔ " : "") + t.name;
    $("heroSub").textContent = `Lunar Day ${d.lunar_day} · ${d.phase} · ${Math.round(d.illumination * 100)}% lit`;
    $("heroMeaning").textContent = t.meaning;
    document.querySelector(".hero").classList.toggle("evil", d.type === "evil");
    document.title = `${t.name} · LUNAR`;
  }

  function renderGrid() {
    const [y, m] = [view.y, view.m];
    $("calTitle").textContent = new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    const lead = new Date(y, m - 1, 1).getDay();
    let html = "";
    for (let i = 0; i < lead; i++) html += `<div class="day empty"></div>`;
    for (const d of monthDays) {
      const t = types[d.type];
      const cls = ["day", d.type === "evil" && "evil", d.date === today && "today", d.date === selected && "selected"].filter(Boolean).join(" ");
      html += `<button class="${cls}" style="--tc:${t.color}" data-date="${d.date}" aria-label="${fmtDate(d.date, { month: "long", day: "numeric" })}: ${t.name}, lunar day ${d.lunar_day}, ${d.phase}">
        <span class="num">${+d.date.slice(8)}</span><span class="emo">${d.emoji}</span>
        <span class="ld">Lunar day ${d.lunar_day}</span><span class="tl">${SHORT[d.type]}</span></button>`;
    }
    $("grid").innerHTML = html;
    if (!selected || !monthDays.some((d) => d.date === selected)) {
      selected = monthDays.some((d) => d.date === today) ? today : monthDays[0].date;
    }
    renderDetail();
    $("legend").innerHTML = Object.values(types).map((t) => `<span style="--tc:${t.color}">${t.name}</span>`).join("");
    const td = monthDays.find((d) => d.date === today);
    if (td) renderHero(td);
  }

  function renderDetail() {
    const d = monthDays.find((x) => x.date === selected);
    if (!d) return;
    document.querySelectorAll(".day.selected").forEach((el) => el.classList.remove("selected"));
    document.querySelector(`.day[data-date="${selected}"]`)?.classList.add("selected");
    const t = types[d.type];
    $("detail").innerHTML = `
      <div class="detail-head">${moonSVG(d.elongation)}
        <div><h3>${fmtDate(d.date, { weekday: "long", month: "long", day: "numeric" })}</h3>
        <span class="badge" style="--tc:${t.color}">${d.type === "evil" ? "⛔ " : ""}${t.name}</span></div>
      </div>
      <p>${t.meaning}</p>
      <dl class="facts">
        <dt>Lunar day</dt><dd>${d.lunar_day} of 30 · ${d.tithi}</dd>
        <dt>Half</dt><dd>${d.paksha}</dd>
        <dt>Lunar day ends</dt><dd>${fmtTime(d.lunar_day_ends)}</dd>
        <dt>Moon</dt><dd>${d.emoji} ${d.phase}, ${Math.round(d.illumination * 100)}% lit</dd>
      </dl>`;
  }

  async function loadPhases() {
    const { phases } = await api(`/api/phases?tz=${encodeURIComponent(tz)}&n=8`);
    $("phases").innerHTML = phases.map((p) => `<li><span class="pe">${p.emoji}</span>
      <div><div>${p.name}</div><div class="pt">${new Date(p.time).toLocaleString(undefined, { timeZone: tz, weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</div></div></li>`).join("");
  }

  function shiftMonth(delta) {
    const d = new Date(view.y, view.m - 1 + delta, 1);
    view = { y: d.getFullYear(), m: d.getMonth() + 1 };
    loadMonth().catch(showLoadError);
  }

  function showLoadError(err) {
    $("heroType").textContent = "Couldn't reach the moon";
    $("heroSub").textContent = err.message;
  }

  // ---- calendar sync ----
  function showSync(feed) {
    const https = location.origin + feed;
    const webcal = https.replace(/^https?:/, "webcal:");
    $("appleLink").href = webcal;
    // Google fetches an https cid directly; a webcal one costs it an extra http redirect.
    $("googleLink").href = "https://calendar.google.com/calendar/r?cid=" + encodeURIComponent(https);
    $("outlookLink").href = `https://outlook.live.com/calendar/0/addfromweb?url=${encodeURIComponent(https)}&name=LUNAR`;
    $("downloadLink").href = feed + "?download=1";
    $("feedUrl").value = https;
    $("syncResult").hidden = false;
  }

  $("syncForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = $("email").value.trim();
    const zone = $("tz").value.trim();
    $("formMsg").textContent = "";
    if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(email)) return ($("formMsg").textContent = "Please enter a valid email address.");
    try { new Intl.DateTimeFormat("en", { timeZone: zone }); } catch { return ($("formMsg").textContent = "Please pick a time zone from the list."); }
    $("syncBtn").disabled = true;
    try {
      const res = await api("/api/subscribe", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, tz: zone, alerts: $("alerts").checked }),
      });
      store.set("lunar.token", res.token);
      store.set("lunar.feed", res.feed);
      store.set("lunar.email", email);
      if (zone !== tz) { tz = zone; store.set("lunar.tz", tz); loadMonth(); loadPhases(); }
      $("syncOk").textContent = res.emailed
        ? `Done! We also emailed the links to ${email}. Pick your phone:`
        : "Your calendar is ready. Pick your phone:";
      showSync(res.feed);
      $("syncResult").scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (err) {
      $("formMsg").textContent = err.message;
    } finally {
      $("syncBtn").disabled = false;
    }
  });

  $("copyBtn").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("feedUrl").value); } catch { $("feedUrl").select(); document.execCommand("copy"); }
    $("copyBtn").textContent = "Copied ✓";
    setTimeout(() => ($("copyBtn").textContent = "Copy link"), 1800);
  });

  async function unsubscribe(token) {
    if (!confirm("Stop syncing LUNAR and delete your email?")) return;
    await api("/api/unsubscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) });
    store.set("lunar.token", null);
    store.set("lunar.feed", null);
    store.set("lunar.email", null);
    $("syncResult").hidden = true;
    $("formMsg").textContent = "";
    alert("Done. You can also remove the LUNAR calendar from your phone's calendar settings.");
  }
  $("unsubBtn").addEventListener("click", () => unsubscribe(store.get("lunar.token")));

  $("grid").addEventListener("click", (ev) => {
    const cell = ev.target.closest(".day[data-date]");
    if (!cell) return;
    selected = cell.dataset.date;
    renderDetail();
  });
  $("prevMonth").addEventListener("click", () => shiftMonth(-1));
  $("nextMonth").addEventListener("click", () => shiftMonth(1));

  // ---- start ----
  try {
    $("tzList").innerHTML = Intl.supportedValuesOf("timeZone").map((z) => `<option value="${z}">`).join("");
  } catch {}
  $("tz").value = tz;
  $("email").value = store.get("lunar.email") || "";
  const now = new Date();
  view = { y: now.getFullYear(), m: now.getMonth() + 1 };
  loadMonth().catch(showLoadError);
  loadPhases().catch(() => {});
  if (store.get("lunar.feed")) showSync(store.get("lunar.feed"));
  const unsub = new URLSearchParams(location.search).get("unsubscribe");
  if (unsub) unsubscribe(unsub).catch(() => {});
})();
