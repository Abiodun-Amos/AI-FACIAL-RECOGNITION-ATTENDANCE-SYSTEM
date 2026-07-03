// ─────────────────────────────────────────────────────────────
// FIREBASE CONFIGURATION
// ─────────────────────────────────────────────────────────────
const FIREBASE_CONFIG = {
  apiKey:            "AIzaSyDsV4-sbeIKZ2aUzHSqoCWaXwrRvZ-cEfA",
  authDomain:        "ai-facial-recognition-system.firebaseapp.com",
  projectId:         "ai-facial-recognition-system",
  storageBucket:     "ai-facial-recognition-system.firebasestorage.app",
  messagingSenderId: "441893940383",
  appId:             "1:441893940383:web:df3f6d70b4ece49b4886aa"
};

firebase.initializeApp(FIREBASE_CONFIG);
const db = firebase.firestore();


// ─────────────────────────────────────────────────────────────
// NAVIGATION
// ─────────────────────────────────────────────────────────────
const PAGE_TITLES = {
  overview:      'Live <span>Overview</span>',
  attendance:    'Attendance <span>Records</span>',
  intruders:     'Intruder <span>Alerts</span>',
  analytics:     'Attendance <span>Analytics</span>',
  students:      'Student <span>Management</span>',
  timetable:     'Timetable <span>Management</span>',
  lecturers:     'Lecturer <span>Registry</span>',
  cancellations: 'Session <span>Cancellations</span>',
};

const ACTION_LABELS = {
  overview:      '⬇ Export CSV',
  attendance:    '⬇ Export CSV',
  intruders:     '🔄 Refresh',
  analytics:     '🔄 Refresh',
  students:      '+ Pre-Register',
  timetable:     '+ Add Session',
  lecturers:     '+ Add Lecturer',
  cancellations: '✕ Cancel Session',
};

let currentPage = 'overview';
let charts      = {};

function navigate(page) {
  document.querySelectorAll('.page')
    .forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item')
    .forEach(n => n.classList.remove('active'));

  document.getElementById(`page-${page}`).classList.add('active');
  document.querySelector(`[onclick="navigate('${page}')"]`)
    .classList.add('active');

  document.getElementById('page-title').innerHTML =
    PAGE_TITLES[page] || page;
  document.getElementById('topbar-action').textContent =
    ACTION_LABELS[page] || '';

  currentPage = page;
  loadPage(page);
}

function topbarAction() {
  const actions = {
    overview:      exportCSV,
    attendance:    exportCSV,
    students:      () => document.getElementById('s-name').focus(),
    timetable:     () => document.getElementById('tt-course').focus(),
    lecturers:     () => document.getElementById('l-name').focus(),
    cancellations: () => document.getElementById('can-session').focus(),
  };
  (actions[currentPage] || refreshAll)();
}

function loadPage(page) {
  const loaders = {
    overview:      loadOverview,
    attendance:    loadAttendance,
    intruders:     loadIntruders,
    analytics:     loadAnalytics,
    students:      loadStudents,
    timetable:     loadTimetable,
    lecturers:     loadLecturers,
    cancellations: loadCancellations,
  };
  if (loaders[page]) loaders[page]();
}

function refreshAll() { loadPage(currentPage); }


// ─────────────────────────────────────────────────────────────
// LIVE CLOCK
// ─────────────────────────────────────────────────────────────
function tickClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleTimeString('en-GB');
  document.getElementById('clock-date').textContent =
    now.toLocaleDateString('en-GB', {
      weekday: 'long', day: '2-digit',
      month: 'short',  year: 'numeric',
    });
}
setInterval(tickClock, 1000);
tickClock();


// ─────────────────────────────────────────────────────────────
// TOAST NOTIFICATION
// ─────────────────────────────────────────────────────────────
let _toastTimer;
function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className   = `show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ''; }, 3500);
}


// ─────────────────────────────────────────────────────────────
// UTILITY HELPERS
// ─────────────────────────────────────────────────────────────
function todayStr() {
  return new Date().toISOString().split('T')[0];
}

function fmtDate(s) {
  if (!s) return '—';
  return new Date(s).toLocaleString('en-GB', {
    day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtTime(s) {
  if (!s) return '—';
  return new Date(s).toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function statusBadge(s) {
  if (s === 'PRESENT') return `<span class="badge badge-present">PRESENT</span>`;
  if (s === 'LATE')    return `<span class="badge badge-late">LATE</span>`;
  return `<span class="badge badge-neutral">${s || '—'}</span>`;
}

function setLoader(id, msg = 'Loading...') {
  document.getElementById(id).innerHTML =
    `<div class="loader"><div class="spinner"></div>${msg}</div>`;
}

function setEmpty(id, icon, msg) {
  document.getElementById(id).innerHTML =
    `<div class="empty">
       <div class="empty-icon">${icon}</div>
       <p>${msg}</p>
     </div>`;
}

/**
 * Write a management command to Firestore.
 * The reverse_sync.py watcher on the Orange Pi polls this
 * collection and applies commands to the local SQLite database.
 */
async function writeCommand(type, payload) {
  const cmdId = Date.now().toString(36) +
                Math.random().toString(36).slice(2);
  await db.collection('management_commands').doc(cmdId).set({
    cmd_id:       cmdId,
    type:         type,
    payload:      payload,
    status:       'pending',
    created_at:   new Date().toISOString(),
    created_by:   'web_admin',
    processed_at: null,
    error:        null,
  });
  return cmdId;
}


// ─────────────────────────────────────────────────────────────
// PAGE: OVERVIEW
// ─────────────────────────────────────────────────────────────
async function loadOverview() {
  const today = todayStr();

  // Fetch attendance, intruders, and students in parallel
  const [attSnap, intSnap, usersSnap, sessSnap] = await Promise.all([
    db.collection('attendance').where('session_date', '==', today).get(),
    db.collection('intruders').where('session_date', '==', today).get(),
    db.collection('users').get(),
    db.collection('sessions').get(),
  ]);

  const records       = attSnap.docs.map(d => d.data());
  const present       = records.filter(r => r.status === 'PRESENT').length;
  const late          = records.filter(r => r.status === 'LATE').length;
  const intCount      = intSnap.size;
  const totalStudents = usersSnap.size;
  const rate          = totalStudents > 0
    ? Math.round((present + late) / totalStudents * 100) : 0;

  // Stat cards
  document.getElementById('ov-present').textContent  = present;
  document.getElementById('ov-late').textContent     = late;
  document.getElementById('ov-intruders').textContent = intCount;
  document.getElementById('ov-rate').textContent     = `${rate}%`;
  document.getElementById('ov-rate-sub').textContent =
    `${present + late} of ${totalStudents} enrolled`;

  // Intruder badge in sidebar
  const badge = document.getElementById('intruder-badge');
  badge.textContent    = intCount;
  badge.style.display  = intCount > 0 ? 'inline-block' : 'none';

  // Today's sessions
  const DAYS_JS = ['SUN','MON','TUE','WED','THU','FRI','SAT'];
  const todayDay = DAYS_JS[new Date().getDay()];
  const todaySessions = sessSnap.docs
    .map(d => d.data())
    .filter(s => s.day_of_week === todayDay);

  if (!todaySessions.length) {
    setEmpty('ov-sessions-wrap', '📅', 'No sessions scheduled today.');
  } else {
    const rows = todaySessions.map(s => {
      const sr = records.filter(r => r.session_id === s.session_id);
      return `<tr>
        <td><strong>${s.course_code}</strong></td>
        <td style="color:var(--text-dim)">${s.course_name || '—'}</td>
        <td style="font-family:var(--font-data);font-size:12px">
          ${s.start_time} – ${s.end_time}</td>
        <td>${s.lecturer_name || '—'}</td>
        <td>
          <span class="badge badge-present">
            ${sr.filter(r => r.status === 'PRESENT').length} present
          </span>
          <span class="badge badge-late" style="margin-left:4px">
            ${sr.filter(r => r.status === 'LATE').length} late
          </span>
        </td>
      </tr>`;
    }).join('');

    document.getElementById('ov-sessions-wrap').innerHTML = `
      <table>
        <thead><tr>
          <th>Course</th><th>Name</th><th>Time</th>
          <th>Lecturer</th><th>Attendance</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // Recent attendance (last 8 records, newest first)
  const recent = [...records]
    .sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
    .slice(0, 8);

  if (!recent.length) {
    setEmpty('ov-recent-wrap', '✓', 'No attendance recorded today yet.');
  } else {
    const rows2 = recent.map(r => `<tr>
      <td style="font-family:var(--font-data);font-size:11px">
        ${fmtTime(r.timestamp)}</td>
      <td><strong>${r.name || '—'}</strong></td>
      <td style="font-family:var(--font-data);font-size:11px">
        ${r.matric_no || '—'}</td>
      <td>${r.course_code || '—'}</td>
      <td>${statusBadge(r.status)}</td>
      <td style="font-family:var(--font-data);font-size:11px;
                 color:var(--text-dim)">
        ${r.confidence ? r.confidence.toFixed(3) : '—'}
      </td>
    </tr>`).join('');

    document.getElementById('ov-recent-wrap').innerHTML = `
      <table>
        <thead><tr>
          <th>Time</th><th>Student</th><th>Matric</th>
          <th>Course</th><th>Status</th><th>Score</th>
        </tr></thead>
        <tbody>${rows2}</tbody>
      </table>`;
  }
}


// ─────────────────────────────────────────────────────────────
// PAGE: ATTENDANCE
// ─────────────────────────────────────────────────────────────
async function loadAttendance() {
  setLoader('att-table-wrap');

  // Default date to today
  const dateInput = document.getElementById('att-date-filter');
  if (!dateInput.value) dateInput.value = todayStr();

  const dateFilter   = dateInput.value;
  const courseFilter = document.getElementById('att-course-filter').value;
  const statusFilter = document.getElementById('att-status-filter').value;

  const snap = await db.collection('attendance')
    .where('session_date', '==', dateFilter).get();
  let records = snap.docs.map(d => d.data());

  // Rebuild course dropdown from retrieved records
  const coursesSeen = [...new Set(records
    .map(r => r.course_code).filter(Boolean))].sort();
  const csel = document.getElementById('att-course-filter');
  const prev = csel.value;
  csel.innerHTML = '<option value="">All Courses</option>';
  coursesSeen.forEach(c => {
    csel.innerHTML +=
      `<option value="${c}" ${c === prev ? 'selected' : ''}>${c}</option>`;
  });

  // Apply filters in JavaScript (avoids composite index requirement)
  if (courseFilter) records = records.filter(r => r.course_code === courseFilter);
  if (statusFilter) records = records.filter(r => r.status === statusFilter);
  records.sort((a, b) =>
    (b.timestamp || '').localeCompare(a.timestamp || ''));

  if (!records.length) {
    setEmpty('att-table-wrap', '📋', 'No records for this filter.');
    window._attRecords = [];
    return;
  }

  const rows = records.map(r => `<tr>
    <td style="font-family:var(--font-data);font-size:11px">
      ${fmtDate(r.timestamp)}</td>
    <td><strong>${r.name || '—'}</strong></td>
    <td style="font-family:var(--font-data);font-size:11px">
      ${r.matric_no || '—'}</td>
    <td><span class="badge badge-blue">L${r.user_level || '?'}</span></td>
    <td>${r.course_code || '—'}</td>
    <td>${statusBadge(r.status)}</td>
    <td style="font-family:var(--font-data);font-size:11px;
               color:var(--text-dim)">
      ${r.confidence ? r.confidence.toFixed(3) : '—'}
    </td>
    <td style="font-size:12px;color:var(--text-dim)">${r.hall_name || '—'}</td>
  </tr>`).join('');

  document.getElementById('att-table-wrap').innerHTML = `
    <div style="padding:12px 16px;border-bottom:1px solid var(--border);
      font-family:var(--font-data);font-size:11px;color:var(--text-dim);">
      ${records.length} record(s) &nbsp;·&nbsp; ${dateFilter}
    </div>
    <table>
      <thead><tr>
        <th>Time</th><th>Student</th><th>Matric</th><th>Level</th>
        <th>Course</th><th>Status</th><th>Score</th><th>Hall</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  window._attRecords = records;  // stash for CSV export
}


// ─────────────────────────────────────────────────────────────
// CSV EXPORT
// ─────────────────────────────────────────────────────────────
function exportCSV() {
  const records = window._attRecords || [];
  if (!records.length) {
    toast('No records to export', 'error');
    return;
  }

  const header = 'Time,Name,Matric,Level,Course,Status,Score,Hall';
  const rows   = records.map(r =>
    [
      fmtDate(r.timestamp), r.name, r.matric_no,
      `L${r.user_level}`,   r.course_code, r.status,
      r.confidence?.toFixed(3), r.hall_name,
    ]
    .map(v => `"${(v || '').replace(/"/g, '""')}"`)
    .join(',')
  );

  const csv  = [header, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `attendance_${todayStr()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast('CSV exported ✓', 'success');
}


// ─────────────────────────────────────────────────────────────
// PAGE: INTRUDER ALERTS
// ─────────────────────────────────────────────────────────────
async function loadIntruders() {
  const gallery   = document.getElementById('intruder-gallery');
  gallery.innerHTML = `<div class="loader">
    <div class="spinner"></div> Loading alerts...</div>`;

  const dateInput = document.getElementById('int-date-filter');
  if (!dateInput.value) dateInput.value = todayStr();
  const dateFilter = dateInput.value;

  const snap = await db.collection('intruders')
    .where('session_date', '==', dateFilter).get();
  const records = snap.docs.map(d => d.data())
    .sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

  if (!records.length) {
    gallery.innerHTML = `<div class="empty">
      <div class="empty-icon">🛡️</div>
      <p>No intruder alerts for ${dateFilter}.</p>
    </div>`;
    return;
  }

  gallery.innerHTML = `<div class="intruder-grid">
    ${records.map((r, i) => `
      <div class="intruder-card"
           onclick="openIntruder(
             '${r.image_url || ''}',
             '${fmtDate(r.timestamp)}',
             '${r.confidence?.toFixed(3) || '—'}',
             '${r.hall_name || '—'}'
           )">
        <div class="intruder-img">
          ${r.image_url
            ? `<img src="${r.image_url}" alt="Intruder ${i + 1}"
                    loading="lazy">`
            : '📷'
          }
        </div>
        <div class="intruder-meta">
          <div class="intruder-time">${fmtTime(r.timestamp)}</div>
          <div class="intruder-conf">
            Similarity: ${r.confidence?.toFixed(3) || '—'}
          </div>
          <div class="intruder-hall">${r.hall_name || '—'}</div>
        </div>
      </div>`).join('')}
  </div>`;
}

function openIntruder(url, time, conf, hall) {
  if (!url) return;
  document.getElementById('intruder-modal-img').src = url;
  document.getElementById('intruder-modal-meta').innerHTML =
    `${time} &nbsp;·&nbsp; Score: ${conf} &nbsp;·&nbsp; ${hall}`;
  document.getElementById('intruder-modal').classList.add('open');
}

function closeIntruderModal(e) {
  if (!e || e.target.id === 'intruder-modal') {
    document.getElementById('intruder-modal').classList.remove('open');
  }
}


// ─────────────────────────────────────────────────────────────
// PAGE: ANALYTICS
// ─────────────────────────────────────────────────────────────
async function loadAnalytics() {
  const today = todayStr();
  const snap  = await db.collection('attendance')
    .where('session_date', '==', today).get();
  const records = snap.docs.map(d => d.data());

  // Destroy old chart instances before recreating
  Object.values(charts).forEach(c => c.destroy());
  charts = {};

  // Global Chart.js defaults for dark theme
  Chart.defaults.color = '#9aaac4';
  Chart.defaults.font  = {
    family: "'JetBrains Mono', monospace",
    size: 11,
  };

  const gridColor   = 'rgba(255,255,255,.04)';
  const tickColor   = '#6b7a99';

  // ── Chart 1: Attendance by course (bar) ──
  const byCourse = {};
  records.forEach(r => {
    if (r.course_code) {
      byCourse[r.course_code] = (byCourse[r.course_code] || 0) + 1;
    }
  });

  charts.courses = new Chart(
    document.getElementById('chart-courses').getContext('2d'), {
    type: 'bar',
    data: {
      labels: Object.keys(byCourse),
      datasets: [{
        data:            Object.values(byCourse),
        backgroundColor: 'rgba(245,166,35,.35)',
        borderColor:     '#f5a623',
        borderWidth:     1.5,
        borderRadius:    4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: tickColor } },
        y: {
          grid: { color: gridColor },
          ticks: { color: tickColor, stepSize: 1 },
          beginAtZero: true,
        },
      },
    },
  });

  // ── Chart 2: PRESENT vs LATE (doughnut) ──
  const present = records.filter(r => r.status === 'PRESENT').length;
  const late    = records.filter(r => r.status === 'LATE').length;

  charts.status = new Chart(
    document.getElementById('chart-status').getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: ['Present', 'Late'],
      datasets: [{
        data:            [present, late],
        backgroundColor: ['rgba(34,211,107,.4)', 'rgba(245,166,35,.4)'],
        borderColor:     ['#22d36b', '#f5a623'],
        borderWidth:     1.5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { padding: 16, color: '#9aaac4' },
        },
      },
    },
  });

  // ── Chart 3: 7-day trend (line) ──
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    return d.toISOString().split('T')[0];
  });

  const counts = await Promise.all(days.map(async day => {
    const s = await db.collection('attendance')
      .where('session_date', '==', day).get();
    return s.size;
  }));

  charts.trend = new Chart(
    document.getElementById('chart-trend').getContext('2d'), {
    type: 'line',
    data: {
      labels: days.map(d => {
        const [, m, dy] = d.split('-');
        return `${dy}/${m}`;
      }),
      datasets: [{
        label:           'Total Attendance',
        data:            counts,
        borderColor:     '#22d36b',
        backgroundColor: 'rgba(34,211,107,.08)',
        borderWidth:     2,
        pointBackgroundColor: '#22d36b',
        pointRadius:     4,
        tension:         .35,
        fill:            true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: tickColor } },
        y: {
          grid: { color: gridColor },
          ticks: { color: tickColor, stepSize: 1 },
          beginAtZero: true,
        },
      },
    },
  });
}


// ─────────────────────────────────────────────────────────────
// PAGE: STUDENTS
// ─────────────────────────────────────────────────────────────
async function loadStudents() {
  const snap  = await db.collection('users').get();
  const users = snap.docs.map(d => d.data())
    .sort((a, b) => (a.name || '').localeCompare(b.name || ''));

  if (!users.length) {
    setEmpty('students-table-wrap', '🎓', 'No students enrolled yet.');
    return;
  }

  document.getElementById('students-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Name</th><th>Matric No.</th><th>Level</th><th>Enrolled</th>
      </tr></thead>
      <tbody>
        ${users.map(u => `<tr>
          <td><strong>${u.name || '—'}</strong></td>
          <td style="font-family:var(--font-data);font-size:12px">
            ${u.matric_no || '—'}</td>
          <td><span class="badge badge-blue">L${u.user_level || '?'}</span></td>
          <td style="font-family:var(--font-data);font-size:11px;
                     color:var(--text-dim)">
            ${u.registered_date ? u.registered_date.split('T')[0] : '—'}
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function preRegisterStudent() {
  const name   = document.getElementById('s-name').value.trim();
  const matric = document.getElementById('s-matric').value.trim().toUpperCase();
  const level  = parseInt(document.getElementById('s-level').value);

  if (!name || !matric) {
    toast('Name and matric number required', 'error');
    return;
  }

  try {
    const cmdId = await writeCommand('PRE_REGISTER_USER', {
      name, matric_no: matric, user_level: level,
    });
    toast(
      `Pre-registration sent ✓ — run reverse sync on device to apply.`,
      'success'
    );
    document.getElementById('s-name').value   = '';
    document.getElementById('s-matric').value = '';
    // Refresh student table after a short delay
    setTimeout(loadStudents, 1500);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}


// ─────────────────────────────────────────────────────────────
// PAGE: TIMETABLE
// ─────────────────────────────────────────────────────────────
async function loadTimetable() {
  // Load courses, lecturers, and sessions concurrently
  const [csSnap, lecSnap, sessSnap] = await Promise.all([
    db.collection('courses').get(),
    db.collection('lecturers').get(),
    db.collection('sessions').get(),
  ]);

  const courses   = csSnap.docs.map(d => d.data())
    .sort((a, b) => (a.course_code || '').localeCompare(b.course_code || ''));
  const lecturers = lecSnap.docs.map(d => d.data())
    .sort((a, b) => (a.full_name || '').localeCompare(b.full_name || ''));
  const sessions  = sessSnap.docs.map(d => d.data());

  // Populate course dropdown
  const csel = document.getElementById('tt-course');
  csel.innerHTML = '<option value="">Select course...</option>';
  courses.forEach(c => {
    csel.innerHTML +=
      `<option value="${c.course_id}" data-code="${c.course_code}">
         ${c.course_code} — ${c.course_name}
       </option>`;
  });

  // Populate lecturer dropdown
  const lsel = document.getElementById('tt-lecturer');
  lsel.innerHTML = '<option value="">Select lecturer...</option>';
  lecturers.forEach(l => {
    lsel.innerHTML +=
      `<option value="${l.lecturer_id}">${l.full_name}</option>`;
  });

  // Also populate the cancellations session dropdown (it shares this data)
  const canSess = document.getElementById('can-session');
  if (canSess) {
    canSess.innerHTML = '<option value="">Select session...</option>';
    const DAYS_ORDER = ['MON','TUE','WED','THU','FRI','SAT','SUN'];
    [...sessions]
      .sort((a, b) =>
        DAYS_ORDER.indexOf(a.day_of_week) - DAYS_ORDER.indexOf(b.day_of_week) ||
        (a.start_time || '').localeCompare(b.start_time || ''))
      .forEach(s => {
        canSess.innerHTML +=
          `<option value="${s.session_id}">
             ${s.day_of_week} ${s.start_time}–${s.end_time} ${s.course_code}
           </option>`;
      });
  }

  // Render timetable
  const DAYS_ORDER = ['MON','TUE','WED','THU','FRI','SAT','SUN'];
  sessions.sort((a, b) =>
    DAYS_ORDER.indexOf(a.day_of_week) - DAYS_ORDER.indexOf(b.day_of_week) ||
    (a.start_time || '').localeCompare(b.start_time || ''));

  if (!sessions.length) {
    setEmpty('timetable-table-wrap', '📅', 'No sessions in timetable yet.');
    return;
  }

  document.getElementById('timetable-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Day</th><th>Time</th><th>Course</th>
        <th>Lecturer</th><th>Hall</th><th>Grace</th>
      </tr></thead>
      <tbody>
        ${sessions.map(s => `<tr>
          <td><span class="badge badge-neutral">${s.day_of_week}</span></td>
          <td style="font-family:var(--font-data);font-size:12px">
            ${s.start_time} – ${s.end_time}</td>
          <td>
            <strong>${s.course_code}</strong>
            <div style="font-size:11px;color:var(--text-dim)">
              L${s.course_level}
            </div>
          </td>
          <td>${s.lecturer_name || '—'}</td>
          <td style="font-size:12px;color:var(--text-dim)">
            ${s.hall_name || '—'}</td>
          <td style="font-family:var(--font-data);font-size:11px;
                     color:var(--text-dim)">
            ${s.grace_minutes} min</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function addSession() {
  const courseEl      = document.getElementById('tt-course');
  const course_id     = parseInt(courseEl.value);
  const course_code   = courseEl.selectedOptions[0]?.dataset.code || '';
  const lecturer_id   = parseInt(document.getElementById('tt-lecturer').value);
  const day_of_week   = document.getElementById('tt-day').value;
  const start_time    = document.getElementById('tt-start').value;
  const end_time      = document.getElementById('tt-end').value;
  const grace_minutes = parseInt(document.getElementById('tt-grace').value) || 60;

  if (!course_id || !lecturer_id || !start_time || !end_time) {
    toast('All fields are required', 'error'); return;
  }
  if (start_time >= end_time) {
    toast('End time must be after start time', 'error'); return;
  }

  try {
    await writeCommand('ADD_SESSION', {
      course_id, course_code, lecturer_id,
      day_of_week, start_time, end_time, grace_minutes,
    });
    toast('Session command sent ✓ — run reverse sync on device to apply.',
          'success');
    setTimeout(loadTimetable, 1000);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

async function addCourse() {
  const code  = document.getElementById('c-code').value.trim().toUpperCase();
  const name  = document.getElementById('c-name').value.trim();
  const level = parseInt(document.getElementById('c-level').value);

  if (!code || !name) {
    toast('Course code and name are required', 'error');
    return;
  }

  try {
    await writeCommand('ADD_COURSE', {
      course_code:  code,
      course_name:  name,
      course_level: level,
    });
    toast(`Course ${code} sent ✓ — run reverse sync on device to apply.`,
          'success');
    document.getElementById('c-code').value = '';
    document.getElementById('c-name').value = '';
    // Refresh the page so the new course appears in the Add Session dropdown
    setTimeout(loadTimetable, 1500);
  } catch(e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ─────────────────────────────────────────────────────────────
// PAGE: LECTURERS
// ─────────────────────────────────────────────────────────────
async function loadLecturers() {
  const snap = await db.collection('lecturers').get();
  const lecs = snap.docs.map(d => d.data())
    .sort((a, b) => (a.full_name || '').localeCompare(b.full_name || ''));

  if (!lecs.length) {
    setEmpty('lecturers-table-wrap', '👤', 'No lecturers added yet.');
    return;
  }

  document.getElementById('lecturers-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Name</th><th>Staff ID</th><th>Department</th>
        <th>Email</th><th>Phone</th>
      </tr></thead>
      <tbody>
        ${lecs.map(l => `<tr>
          <td><strong>${l.full_name || '—'}</strong></td>
          <td style="font-family:var(--font-data);font-size:11px">
            ${l.staff_id || '—'}</td>
          <td style="color:var(--text-dim);font-size:12px">
            ${l.department || '—'}</td>
          <td style="font-family:var(--font-data);font-size:11px;
                     color:var(--text-dim)">
            ${l.email || '—'}</td>
          <td style="font-family:var(--font-data);font-size:11px;
                     color:var(--text-dim)">
            ${l.phone || '—'}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function addLecturer() {
  const name    = document.getElementById('l-name').value.trim();
  const staffId = document.getElementById('l-staffid').value.trim();
  const dept    = document.getElementById('l-dept').value.trim();
  const email   = document.getElementById('l-email').value.trim();
  const phone   = document.getElementById('l-phone').value.trim();

  if (!name) { toast('Lecturer name required', 'error'); return; }

  try {
    await writeCommand('ADD_LECTURER', {
      full_name:  name,
      staff_id:   staffId  || null,
      department: dept     || 'Electrical Electronics',
      email:      email    || null,
      phone:      phone    || null,
    });
    toast('Lecturer command sent ✓ — run reverse sync on device to apply.',
          'success');
    // Clear form
    ['l-name', 'l-staffid', 'l-email', 'l-phone'].forEach(id => {
      document.getElementById(id).value = '';
    });
    setTimeout(loadLecturers, 1000);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}


// ─────────────────────────────────────────────────────────────
// PAGE: CANCELLATIONS
// ─────────────────────────────────────────────────────────────
async function loadCancellations() {
  // Default date to today
  const dateInput = document.getElementById('can-date');
  if (!dateInput.value) dateInput.value = todayStr();

  // Show upcoming + recent cancellation commands
  const snap = await db.collection('management_commands')
    .where('type', '==', 'CANCEL_SESSION').get();

  const cmds = snap.docs
    .map(d => d.data())
    .filter(c => (c.payload?.cancellation_date || '') >= todayStr())
    .sort((a, b) =>
      (a.payload?.cancellation_date || '')
        .localeCompare(b.payload?.cancellation_date || ''));

  if (!cmds.length) {
    setEmpty('cancellations-table-wrap', '✓',
             'No upcoming cancellations.');
    return;
  }

  document.getElementById('cancellations-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Date</th><th>Session</th><th>Reason</th>
        <th>Cancelled By</th><th>Status</th>
      </tr></thead>
      <tbody>
        ${cmds.map(c => {
          const badgeClass =
            c.status === 'processed' ? 'badge-present' :
            c.status === 'failed'    ? 'badge-danger'  : 'badge-late';
          return `<tr>
            <td style="font-family:var(--font-data);font-size:12px">
              ${c.payload?.cancellation_date || '—'}</td>
            <td>Session ${c.payload?.session_id || '—'}</td>
            <td>
              ${c.payload?.reason_category || '—'}
              ${c.payload?.reason_note
                ? `<div style="font-size:11px;color:var(--text-dim)">
                     ${c.payload.reason_note}
                   </div>`
                : ''}
            </td>
            <td>${c.payload?.cancelled_by || '—'}</td>
            <td>
              <span class="badge ${badgeClass}">
                ${c.status || 'pending'}
              </span>
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

async function cancelSession() {
  const session_id = document.getElementById('can-session').value;
  const date       = document.getElementById('can-date').value;
  const reason     = document.getElementById('can-reason').value;
  const by         = document.getElementById('can-by').value.trim();
  const note       = document.getElementById('can-note').value.trim();

  if (!session_id || !date || !by) {
    toast('Session, date, and cancelled-by are required', 'error');
    return;
  }

  try {
    await writeCommand('CANCEL_SESSION', {
      session_id:        parseInt(session_id),
      cancellation_date: date,
      reason_category:   reason,
      reason_note:       note || null,
      cancelled_by:      by,
    });
    toast('Cancellation sent ✓ — run reverse sync on device to apply.',
          'success');
    document.getElementById('can-by').value   = '';
    document.getElementById('can-note').value = '';
    setTimeout(loadCancellations, 1000);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}


// ─────────────────────────────────────────────────────────────
// INITIALISE — load overview on page start
// ─────────────────────────────────────────────────────────────
loadOverview();
