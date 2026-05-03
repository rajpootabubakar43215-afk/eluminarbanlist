from flask import Flask, jsonify, render_template_string
import paramiko
import time
import re
import requests
from datetime import datetime
from threading import Thread, Lock
import os

app = Flask(__name__)

# ── SFTP Settings ────────────────────────────────────────────
SFTP_HOST = "upsilon.optiklink.com"
SFTP_PORT = 2022
SFTP_USER = "m7wuj930.37f7cc15"
SFTP_PASS = "lolopopo"
BANS_FILE = "main/miscmod_bans.dat"
REFRESH_INTERVAL = 30  # seconds

# ── Cache ─────────────────────────────────────────────────────
bans_cache = []
last_updated = None
cache_lock = Lock()
geo_cache = {}

# ── CoD color code stripper ───────────────────────────────────
def strip_color(s):
    return re.sub(r'\^\d', '', s or '')

# ── GeoIP ─────────────────────────────────────────────────────
def get_country(ip):
    if not ip or ip == "Unknown":
        return {"code": "?", "name": "Unknown", "flag": "🏳️"}
    if ip in geo_cache:
        return geo_cache[ip]
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode",
            timeout=2
        ).json()
        if r.get("status") == "success":
            result = {
                "code": r.get("countryCode", "?"),
                "name": r.get("country", "Unknown"),
                "flag": ""
            }
            geo_cache[ip] = result
            return result
    except:
        pass
    return {"code": "?", "name": "Unknown", "flag": ""}

# ── Parse ban line ─────────────────────────────────────────────
# Format: IP%name%admin%duration%timestamp%reason
def parse_bans(content):
    bans = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("%")
        if len(parts) < 5:
            continue
        ip        = parts[0] if len(parts) > 0 else "Unknown"
        name      = strip_color(parts[1]) if len(parts) > 1 else "Unknown"
        admin     = strip_color(parts[2]) if len(parts) > 2 else "?"
        duration  = int(parts[3]) if len(parts) > 3 else -86400
        timestamp = int(parts[4]) if len(parts) > 4 else 0
        reason    = parts[5] if len(parts) > 5 else ""

        # Ban date from timestamp
        try:
            ban_date = datetime.fromtimestamp(timestamp).strftime("%Y/%m/%d")
        except:
            ban_date = "Unknown"

        # Duration label
        if duration < 0 or duration == -86400:
            duration_label = "Permanent"
        else:
            days = duration // 86400
            duration_label = f"{days}d" if days > 0 else f"{duration}s"

        country = get_country(ip)

        bans.append({
            "ip":       ip,
            "name":     name,
            "admin":    admin,
            "reason":   reason,
            "date":     ban_date,
            "duration": duration_label,
            "country":  country
        })

    # Sort by date descending
    bans.sort(key=lambda x: x["date"], reverse=True)
    return bans

# ── SFTP loader ────────────────────────────────────────────────
def load_bans():
    global bans_cache, last_updated
    while True:
        try:
            transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
            transport.connect(username=SFTP_USER, password=SFTP_PASS)
            sftp = paramiko.SFTPClient.from_transport(transport)

            with sftp.open(BANS_FILE, "r") as f:
                content = f.read().decode("utf-8", errors="ignore")

            sftp.close()
            transport.close()

            parsed = parse_bans(content)

            with cache_lock:
                bans_cache = parsed
                last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(f"[OK] Loaded {len(parsed)} bans")

        except Exception as e:
            print(f"[SFTP Error] {e}")

        time.sleep(REFRESH_INTERVAL)

# ── Routes ─────────────────────────────────────────────────────
@app.route("/api/bans")
def api_bans():
    with cache_lock:
        return jsonify({
            "bans": bans_cache,
            "total": len(bans_cache),
            "updated": last_updated
        })

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Server Banlist</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0a0c0f;
    --surface:  #111418;
    --border:   #1e2530;
    --accent:   #00ff88;
    --accent2:  #ffcc00;
    --red:      #ff3b3b;
    --text:     #d0d8e8;
    --muted:    #556070;
    --header:   #12ff7020;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Rajdhani', sans-serif;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse 80% 40% at 50% -10%, #00ff4415 0%, transparent 70%),
      repeating-linear-gradient(0deg, transparent, transparent 40px, #ffffff03 40px, #ffffff03 41px),
      repeating-linear-gradient(90deg, transparent, transparent 40px, #ffffff03 40px, #ffffff03 41px);
  }

  /* ── Header ── */
  .site-header {
    text-align: center;
    padding: 48px 20px 32px;
    position: relative;
  }
  .site-header::after {
    content: '';
    display: block;
    width: 200px;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    margin: 20px auto 0;
  }
  .skull { font-size: 2.2rem; display: block; margin-bottom: 8px; }
  .site-header h1 {
    font-size: clamp(1.8rem, 5vw, 3rem);
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #fff;
  }
  .site-header h1 span { color: var(--accent); }
  .subtitle {
    font-family: 'Share Tech Mono', monospace;
    color: var(--muted);
    font-size: 0.78rem;
    margin-top: 6px;
    letter-spacing: 0.08em;
  }

  /* ── Stats bar ── */
  .stats {
    display: flex;
    justify-content: center;
    gap: 40px;
    margin: 0 auto 32px;
    padding: 16px;
    max-width: 800px;
  }
  .stat {
    text-align: center;
  }
  .stat-num {
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
    font-family: 'Share Tech Mono', monospace;
  }
  .stat-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-top: 2px;
  }

  /* ── Search ── */
  .search-wrap {
    max-width: 900px;
    margin: 0 auto 20px;
    padding: 0 20px;
    display: flex;
    gap: 10px;
  }
  .search-input {
    flex: 1;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 16px;
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.88rem;
    outline: none;
    transition: border-color 0.2s;
  }
  .search-input:focus { border-color: var(--accent); }
  .search-input::placeholder { color: var(--muted); }

  /* ── Table container ── */
  .table-wrap {
    max-width: 1200px;
    margin: 0 auto 60px;
    padding: 0 16px;
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
  }
  thead tr {
    background: var(--header);
    border-bottom: 2px solid var(--accent);
  }
  thead th {
    padding: 14px 16px;
    text-align: left;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.72rem;
    color: var(--accent);
    white-space: nowrap;
  }
  tbody tr {
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
  }
  tbody tr:hover { background: #ffffff05; }
  tbody tr.hidden { display: none; }
  td {
    padding: 11px 16px;
    vertical-align: middle;
  }

  /* ── Player name ── */
  .player-name {
    font-weight: 700;
    color: #fff;
    font-size: 0.96rem;
  }

  /* ── Reason badge ── */
  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .badge-wall  { background:#ff3b3b22; color:#ff6b6b; border:1px solid #ff3b3b44; }
  .badge-multi { background:#ff9b0022; color:#ffb030; border:1px solid #ff9b0044; }
  .badge-aim   { background:#a855f722; color:#c084fc; border:1px solid #a855f744; }
  .badge-cheat { background:#3b82f622; color:#60a5fa; border:1px solid #3b82f644; }
  .badge-other { background:#ffffff11; color:#aaa;    border:1px solid #ffffff22; }

  /* ── Duration ── */
  .perm { color: var(--red); font-weight: 700; font-family: 'Share Tech Mono', monospace; font-size: 0.82rem; }
  .temp { color: var(--accent2); font-family: 'Share Tech Mono', monospace; font-size: 0.82rem; }

  /* ── Admin ── */
  .admin-name { color: var(--accent2); font-size: 0.88rem; }

  /* ── Date ── */
  .date-cell {
    font-family: 'Share Tech Mono', monospace;
    color: var(--muted);
    font-size: 0.82rem;
    white-space: nowrap;
  }

  /* ── Country ── */
  .country-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }
  .flag-img {
    width: 24px;
    height: 16px;
    border-radius: 2px;
    object-fit: cover;
  }
  .country-name { font-size: 0.82rem; color: var(--muted); }

  /* ── Status bar ── */
  .status-bar {
    text-align: center;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.72rem;
    color: var(--muted);
    padding-bottom: 24px;
  }
  .status-dot {
    display: inline-block;
    width: 7px; height: 7px;
    background: var(--accent);
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.3; }
  }

  /* ── Row counter ── */
  .row-num {
    color: var(--muted);
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    width: 40px;
  }

  /* ── No results ── */
  .no-results {
    text-align: center;
    padding: 40px;
    color: var(--muted);
    font-family: 'Share Tech Mono', monospace;
    display: none;
  }
</style>
</head>
<body>

<header class="site-header">
  <span class="skull">💀</span>
  <h1><span>[=</span>SERVER<span>=]</span> Banlist</h1>
  <p class="subtitle">HALL OF SHAME — CHEATERS NEVER WIN</p>
</header>

<div class="stats">
  <div class="stat">
    <div class="stat-num" id="total-count">—</div>
    <div class="stat-label">Total Bans</div>
  </div>
  <div class="stat">
    <div class="stat-num" id="perm-count">—</div>
    <div class="stat-label">Permanent</div>
  </div>
  <div class="stat">
    <div class="stat-num" id="updated-time">—</div>
    <div class="stat-label">Last Updated</div>
  </div>
</div>

<div class="search-wrap">
  <input class="search-input" id="search" type="text"
         placeholder="Search player, reason, admin...">
</div>

<div class="table-wrap">
  <table id="ban-table">
    <thead>
      <tr>
        <th>#</th>
        <th>Player</th>
        <th>Reason</th>
        <th>Admin</th>
        <th>Duration</th>
        <th>Ban Date</th>
        <th>Country</th>
      </tr>
    </thead>
    <tbody id="ban-body">
      <tr><td colspan="7" style="text-align:center;padding:40px;color:#556070;font-family:monospace">Loading bans...</td></tr>
    </tbody>
  </table>
  <div class="no-results" id="no-results">No bans match your search.</div>
</div>

<div class="status-bar">
  <span class="status-dot"></span>
  <span id="status-text">Connecting to server...</span>
</div>

<script>
function getBadge(reason) {
  const r = (reason || '').toLowerCase();
  if (r.includes('wall'))  return `<span class="badge badge-wall">${reason}</span>`;
  if (r.includes('multi')) return `<span class="badge badge-multi">${reason}</span>`;
  if (r.includes('aim'))   return `<span class="badge badge-aim">${reason}</span>`;
  if (r.includes('cheat')) return `<span class="badge badge-cheat">${reason}</span>`;
  return `<span class="badge badge-other">${reason || '—'}</span>`;
}

function getFlagUrl(code) {
  if (!code || code === '?') return '';
  return `https://flagcdn.com/w40/${code.toLowerCase()}.png`;
}

async function loadBans() {
  try {
    const res  = await fetch('/api/bans');
    const data = await res.json();
    const bans = data.bans || [];

    // Stats
    document.getElementById('total-count').textContent = bans.length;
    document.getElementById('perm-count').textContent  =
      bans.filter(b => b.duration === 'Permanent').length;
    document.getElementById('updated-time').textContent =
      data.updated ? data.updated.slice(11, 16) : '—';
    document.getElementById('status-text').textContent  =
      `Last synced: ${data.updated || '...'} — ${bans.length} bans loaded`;

    const tbody = document.getElementById('ban-body');
    if (!bans.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#556070;font-family:monospace">No bans found.</td></tr>';
      return;
    }

    tbody.innerHTML = bans.map((b, i) => {
      const flagUrl = getFlagUrl(b.country?.code);
      const flagImg = flagUrl
        ? `<img class="flag-img" src="${flagUrl}" alt="${b.country?.code}">`
        : `<span style="font-size:1.2rem">${b.country?.flag || '🏳️'}</span>`;

      const dur = b.duration === 'Permanent'
        ? `<span class="perm">PERM</span>`
        : `<span class="temp">${b.duration}</span>`;

      return `<tr>
        <td class="row-num">${i + 1}</td>
        <td class="player-name">${b.name}</td>
        <td>${getBadge(b.reason)}</td>
        <td class="admin-name">${b.admin}</td>
        <td>${dur}</td>
        <td class="date-cell">${b.date}</td>
        <td><div class="country-cell">${flagImg}<span class="country-name">${b.country?.name || '?'}</span></div></td>
      </tr>`;
    }).join('');

    // Search
    document.getElementById('search').addEventListener('input', filterTable);

  } catch(e) {
    document.getElementById('status-text').textContent = 'Error loading bans: ' + e.message;
  }
}

function filterTable() {
  const q = document.getElementById('search').value.toLowerCase();
  const rows = document.querySelectorAll('#ban-body tr');
  let visible = 0;
  rows.forEach(row => {
    const match = row.textContent.toLowerCase().includes(q);
    row.classList.toggle('hidden', !match);
    if (match) visible++;
  });
  document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
}

// Load on start, then every 30s
loadBans();
setInterval(loadBans, 30000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

if __name__ == "__main__":
    # Start SFTP loader thread
    Thread(target=load_bans, daemon=True).start()
    # Give it a moment to load
    time.sleep(1)
    print("Server running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
