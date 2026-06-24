/**
 * FenceGuard Lite — Dashboard Application
 *
 * Handles:
 * - WebSocket connection to gateway (binary frames + JSON messages)
 * - Video canvas rendering (PTZ broadcast + inset)
 * - Biomechanics panel updates
 * - Head-speed live chart (pure canvas, no external libs)
 * - Event timeline (lunge, impact, fencing response)
 * - Head Impact Risk clinical alert card
 * - File upload with progress
 */

// ── State ──────────────────────────────────────────────
let ws = null;
let apiKey = '';
let sessionId = null;
let isConnected = false;
let events = [];

// Canvas refs
const videoCanvas = document.getElementById('videoCanvas');
const videoCtx = videoCanvas.getContext('2d');
const insetCanvas = document.getElementById('insetCanvas');
const insetCtx = insetCanvas.getContext('2d');
const chartCanvas = document.getElementById('headSpeedChart');
const chartCtx = chartCanvas.getContext('2d');

// Head speed history for chart
const headSpeedHistory = [];
const MAX_CHART_POINTS = 200;

// Track whether the next binary message is an inset frame
let expectingInset = false;

// ── Connection ─────────────────────────────────────────

function handleConnect() {
    apiKey = document.getElementById('apiKeyInput').value.trim();
    if (!apiKey) {
        alert('Please enter an API key');
        return;
    }

    if (isConnected) {
        disconnectWs();
        return;
    }

    // If we have a sessionId from upload, start the session first
    if (sessionId) {
        startSessionApi(sessionId);
    } else {
        // Start webcam session
        startSessionApi('webcam');
    }
}

function startSessionApi(source) {
    fetch('/api/session/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey,
        },
        body: JSON.stringify({ source: source }),
    })
    .then(r => {
        if (!r.ok) throw new Error(`Session start failed: ${r.status}`);
        return r.json();
    })
    .then(data => {
        sessionId = data.sessionId;
        connectWebSocket();
    })
    .catch(err => {
        console.error('Session start error:', err);
        alert('Failed to start session. Check your API key and try again.');
    });
}

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws?token=${encodeURIComponent(apiKey)}`;

    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        isConnected = true;
        updateStatus(true);
        document.getElementById('emptyState').style.display = 'none';
        document.getElementById('connectBtn').textContent = 'Disconnect';
        document.getElementById('stopBtn').style.display = 'inline-block';
        console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
            handleBinaryFrame(event.data);
        } else {
            handleTextMessage(JSON.parse(event.data));
        }
    };

    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
    };

    ws.onclose = (event) => {
        isConnected = false;
        updateStatus(false);
        document.getElementById('connectBtn').textContent = 'Connect';
        document.getElementById('stopBtn').style.display = 'none';
        console.log('WebSocket closed:', event.code, event.reason);
    };
}

function disconnectWs() {
    if (ws) {
        ws.send('stop');
        ws.close();
        ws = null;
    }
    isConnected = false;
    updateStatus(false);
    document.getElementById('connectBtn').textContent = 'Connect';
    document.getElementById('stopBtn').style.display = 'none';
}

function stopSession() {
    disconnectWs();
}

function updateStatus(connected) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (connected) {
        dot.classList.remove('disconnected');
        text.textContent = 'Live';
        text.style.color = 'var(--severity-low)';
    } else {
        dot.classList.add('disconnected');
        text.textContent = 'Disconnected';
        text.style.color = 'var(--text-muted)';
    }
}

// ── Frame Rendering ────────────────────────────────────

function handleBinaryFrame(data) {
    const blob = new Blob([data], { type: 'image/jpeg' });
    const url = URL.createObjectURL(blob);
    const img = new Image();

    img.onload = () => {
        if (expectingInset) {
            // Render to inset canvas
            insetCanvas.width = img.width;
            insetCanvas.height = img.height;
            insetCtx.drawImage(img, 0, 0);
            document.getElementById('insetContainer').style.display = 'block';
            expectingInset = false;
        } else {
            // Render to main canvas
            videoCanvas.width = img.width;
            videoCanvas.height = img.height;
            videoCtx.drawImage(img, 0, 0);
        }
        URL.revokeObjectURL(url);
    };

    img.src = url;
}

// ── Text Message Handling ──────────────────────────────

function handleTextMessage(msg) {
    switch (msg.type) {
        case 'metrics':
            updateBiomechanics(msg.data);
            updateFps(msg.fps);
            break;
        case 'events':
            handleEvents(msg.data);
            break;
        case 'inset':
            expectingInset = true;
            break;
        case 'complete':
            console.log('Processing complete');
            disconnectWs();
            break;
        case 'error':
            console.error('Server error:', msg.message);
            break;
    }
}

// ── Biomechanics Updates ───────────────────────────────

function updateBiomechanics(metrics) {
    if (!metrics) return;

    const angles = metrics.joint_angles || {};
    const headKin = metrics.head_kinematics || {};
    const tracking = metrics.tracking || {};
    const ptz = metrics.ptz || {};

    // Joint angles
    setJointValue('leftElbow', angles.left_elbow);
    setJointValue('rightElbow', angles.right_elbow);
    setJointValue('leftKnee', angles.left_knee);
    setJointValue('rightKnee', angles.right_knee);
    setJointValue('torsoLean', angles.torso_lean);

    // Head speed
    const headSpeed = headKin.head_speed_normalized || 0;
    document.getElementById('headSpeedValue').textContent = headSpeed.toFixed(3);

    // Update chart
    headSpeedHistory.push(headSpeed);
    if (headSpeedHistory.length > MAX_CHART_POINTS) {
        headSpeedHistory.shift();
    }
    drawHeadSpeedChart();

    // PTZ badges
    if (ptz.zoom_level) {
        document.getElementById('zoomBadge').textContent = `Zoom: ${ptz.zoom_level}×`;
    }
    if (tracking.confidence) {
        document.getElementById('confidenceBadge').textContent =
            `${(tracking.confidence * 100).toFixed(0)}% conf`;
    }
}

function setJointValue(elementId, value) {
    const el = document.getElementById(elementId);
    if (value !== null && value !== undefined) {
        el.innerHTML = `${Math.round(value)}<span class="unit">°</span>`;
    } else {
        el.innerHTML = `--<span class="unit">°</span>`;
    }
}

function updateFps(fps) {
    const display = document.getElementById('fpsDisplay');
    display.style.display = 'inline-block';
    display.textContent = `${fps} FPS`;
}

// ── Head Speed Chart (Pure Canvas) ─────────────────────

function drawHeadSpeedChart() {
    const canvas = chartCanvas;
    const ctx = chartCtx;
    const dpr = window.devicePixelRatio || 1;

    // Set canvas size
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 120 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '120px';
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = 120;
    const data = headSpeedHistory;

    // Clear
    ctx.clearRect(0, 0, w, h);

    if (data.length < 2) return;

    // Find max for scale
    const maxVal = Math.max(...data, 0.1);
    const yScale = (h - 20) / maxVal;

    // Draw threshold line
    ctx.strokeStyle = 'rgba(239, 68, 68, 0.3)';
    ctx.setLineDash([4, 4]);
    const threshY = h - 10 - 3.0 * yScale; // impact threshold
    if (threshY > 0) {
        ctx.beginPath();
        ctx.moveTo(0, threshY);
        ctx.lineTo(w, threshY);
        ctx.stroke();
    }
    ctx.setLineDash([]);

    // Draw gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, 'rgba(34, 211, 238, 0.3)');
    gradient.addColorStop(1, 'rgba(34, 211, 238, 0.0)');

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(0, h - 10);

    const xStep = w / (MAX_CHART_POINTS - 1);
    const startX = w - (data.length - 1) * xStep;

    for (let i = 0; i < data.length; i++) {
        const x = startX + i * xStep;
        const y = h - 10 - data[i] * yScale;
        if (i === 0) ctx.moveTo(x, h - 10);
        ctx.lineTo(x, y);
    }

    ctx.lineTo(startX + (data.length - 1) * xStep, h - 10);
    ctx.closePath();
    ctx.fill();

    // Draw line
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
        const x = startX + i * xStep;
        const y = h - 10 - data[i] * yScale;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Draw current value dot
    if (data.length > 0) {
        const lastX = startX + (data.length - 1) * xStep;
        const lastY = h - 10 - data[data.length - 1] * yScale;
        ctx.fillStyle = '#22d3ee';
        ctx.beginPath();
        ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
        ctx.fill();
    }
}

// ── Event Timeline ─────────────────────────────────────

function handleEvents(eventData) {
    if (!eventData || !Array.isArray(eventData)) return;

    for (const evt of eventData) {
        events.push(evt);
        addEventCard(evt);

        // Show Head Impact Risk alert for fencing response
        if (evt.type === 'fencing_response' && evt.head_impact_risk) {
            showImpactAlert(evt.head_impact_risk);
        }
    }

    document.getElementById('eventCount').textContent = `${events.length} events`;
}

function addEventCard(evt) {
    const list = document.getElementById('eventList');

    // Remove placeholder text
    if (events.length === 1) {
        list.innerHTML = '';
    }

    const card = document.createElement('div');
    card.className = `event-card ${evt.type}`;

    const typeLabel = evt.type.replace(/_/g, ' ').toUpperCase();
    const timeStr = formatTime(evt.timestamp);
    const severityClass = evt.severity || 'LOW';

    let detailHtml = '';
    if (evt.type === 'lunge' && evt.metrics) {
        detailHtml = `Velocity: ${evt.metrics.velocity_ratio}× baseline`;
    } else if (evt.type === 'impact' && evt.metrics) {
        detailHtml = `Peak speed: ${evt.metrics.peak_head_speed}`;
    } else if (evt.type === 'fencing_response' && evt.metrics) {
        detailHtml = `Duration: ${evt.metrics.posture_duration_s}s — PROTOTYPE`;
    }

    card.innerHTML = `
        <div class="event-type">
            ${typeLabel}
            <span class="severity-badge ${severityClass}">${severityClass}</span>
        </div>
        <div class="event-time">${timeStr}</div>
        ${detailHtml ? `<div class="event-detail">${detailHtml}</div>` : ''}
    `;

    list.prepend(card);

    // Keep max 50 visible events
    while (list.children.length > 50) {
        list.removeChild(list.lastChild);
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(1);
    return `${mins.toString().padStart(2, '0')}:${secs.padStart(4, '0')}`;
}

// ── Head Impact Risk Alert ─────────────────────────────

function showImpactAlert(risk) {
    const alert = document.getElementById('impactAlert');
    alert.classList.add('active');

    document.getElementById('impactHeadSpeed').textContent =
        `${risk.head_speed_baseline_ratio}× baseline`;
    document.getElementById('impactDirChange').textContent =
        risk.direction_change_rate;
    document.getElementById('impactDuration').textContent =
        `${risk.sustained_posture_duration_s}s`;
    document.getElementById('impactPreSpeed').textContent =
        `${risk.pre_impact_head_speed} n.u.`;

    // Auto-hide after 15 seconds
    setTimeout(() => {
        alert.classList.remove('active');
    }, 15000);
}

// ── File Upload ────────────────────────────────────────

function showUploadModal() {
    document.getElementById('uploadModal').classList.add('active');
}

function hideUploadModal() {
    document.getElementById('uploadModal').classList.remove('active');
    document.getElementById('uploadProgress').style.display = 'none';
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    uploadFile(file);
}

// Drag and drop
const uploadZone = document.getElementById('uploadZone');
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});
uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
});

function uploadFile(file) {
    apiKey = document.getElementById('apiKeyInput').value.trim();
    if (!apiKey) {
        alert('Please enter an API key first');
        return;
    }

    const progressDiv = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('progressBar');
    const statusText = document.getElementById('uploadStatus');
    progressDiv.style.display = 'block';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('X-API-Key', apiKey);

    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const pct = (e.loaded / e.total * 100).toFixed(0);
            progressBar.style.width = pct + '%';
            statusText.textContent = `Uploading... ${pct}%`;
        }
    };

    xhr.onload = () => {
        if (xhr.status === 200) {
            const data = JSON.parse(xhr.responseText);
            sessionId = data.sessionId;
            statusText.textContent = `✓ Upload complete — Session: ${data.sessionId}`;
            progressBar.style.width = '100%';
            progressBar.style.background = 'var(--severity-low)';

            setTimeout(() => {
                hideUploadModal();
                // Auto-connect to start processing.
                // startSessionApi() opens the WebSocket itself on success,
                // so we must NOT also call connectWebSocket() here (double connect).
                startSessionApi(sessionId);
            }, 1000);
        } else {
            statusText.textContent = `✗ Upload failed: ${xhr.statusText}`;
            progressBar.style.background = 'var(--severity-critical)';
        }
    };

    xhr.onerror = () => {
        statusText.textContent = '✗ Upload failed: network error';
        progressBar.style.background = 'var(--severity-critical)';
    };

    xhr.send(formData);
}

// ── Initialize ─────────────────────────────────────────

// Wire up control handlers via addEventListener.
// (Inline onclick/onchange attributes are blocked by the strict
//  Content-Security-Policy `script-src 'self'`, so they must live here.)
document.getElementById('connectBtn').addEventListener('click', handleConnect);
document.getElementById('uploadBtn').addEventListener('click', showUploadModal);
document.getElementById('stopBtn').addEventListener('click', stopSession);
document.getElementById('cancelUploadBtn').addEventListener('click', hideUploadModal);
document.getElementById('fileInput').addEventListener('change', handleFileSelect);

// Clicking the upload zone opens the file picker. Guard against the
// programmatic click on the (hidden) input bubbling back here.
uploadZone.addEventListener('click', (e) => {
    if (e.target.id === 'fileInput') return;
    document.getElementById('fileInput').click();
});

// Draw empty chart
drawHeadSpeedChart();

// Resize chart on window resize
window.addEventListener('resize', () => {
    drawHeadSpeedChart();
});
