const API_BASE = '/api/v1';

let fileInput, uploadBtn, analysisResult, queryForm, queryResult, sessionId;
let currentCacheKey = null;

document.addEventListener('DOMContentLoaded', () => {
    initializeElements();
    setupEventListeners();
    sessionId = generateSessionId();
});

function initializeElements() {
    document.getElementById('root').innerHTML = `
        <div class="container">
            <h1>Smart Calendar Assistant</h1>
            
            <!-- Step 1: Upload ICS -->
            <div class="upload-section">
                <h2>1. Upload Calendar File</h2>
                <div class="upload-form">
                    <input type="file" id="fileInput" accept=".ics" />
                    <div class="form-row">
                        <label>
                            Timezone:
                            <select id="timezone">
                                <option value="Europe/Moscow">Europe/Moscow</option>
                                <option value="UTC">UTC</option>
                                <option value="America/New_York">America/New_York</option>
                                <option value="Europe/London">Europe/London</option>
                            </select>
                        </label>
                        <label>
                            Days Limit:
                            <input type="number" id="daysLimit" value="14" min="0" max="365" />
                        </label>
                    </div>
                    <div class="form-row">
                        <label>
                            <input type="checkbox" id="expandRecurring" checked /> Expand recurring events
                        </label>
                        <label>
                            Horizon Days:
                            <input type="number" id="horizonDays" value="30" min="1" max="365" />
                        </label>
                    </div>
                    <button id="uploadBtn" disabled>Process Calendar</button>
                </div>
                <div id="analysisResult" class="result-panel hidden"></div>
            </div>

            <!-- Step 2: Query for recommendation -->
            <div class="query-section hidden" id="querySection">
                <h2>2. Find Time Slot</h2>
                <form id="queryForm" class="query-form">
                    <div class="form-row">
                        <label>
                            Event Summary:
                            <input type="text" id="summary" required placeholder="Meeting with client" />
                        </label>
                        <label>
                            Duration (minutes):
                            <input type="number" id="duration" value="60" min="15" max="480" />
                        </label>
                    </div>
                    <div class="form-row">
                        <label>
                            Priority:
                            <select id="priority">
                                <option value="regular">Regular</option>
                                <option value="high">High</option>
                            </select>
                        </label>
                    </div>
                    <button type="submit">Get Recommendations</button>
                </form>
                <div id="queryResult" class="result-panel hidden"></div>
            </div>
        </div>
    `;

    fileInput = document.getElementById('fileInput');
    uploadBtn = document.getElementById('uploadBtn');
    analysisResult = document.getElementById('analysisResult');
    queryForm = document.getElementById('queryForm');
    queryResult = document.getElementById('queryResult');
}

function setupEventListeners() {
    fileInput.addEventListener('change', () => {
        uploadBtn.disabled = !fileInput.files.length;
    });

    uploadBtn.addEventListener('click', handleUpload);
    queryForm.addEventListener('submit', handleQuery);
}

function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

async function handleUpload() {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('timezone', document.getElementById('timezone').value);
    formData.append('expand_recurring', document.getElementById('expandRecurring').checked);
    formData.append('horizon_days', document.getElementById('horizonDays').value);
    formData.append('days_limit', document.getElementById('daysLimit').value);
    formData.append('user_session', sessionId);

    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Processing...';
    
    showResult(analysisResult, 'Processing your calendar...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/flow/import+enrich+analyze`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail?.error || result.detail || 'Upload failed');
        }

        currentCacheKey = result.cache_key;

        showResult(analysisResult, formatAnalysisResult(result), 'success');

        await fetchAnalytics(result.cache_key);

        document.getElementById('querySection').classList.remove('hidden');

    } catch (error) {
        showResult(analysisResult, `Error: ${error.message}`, 'error');
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Process Calendar';
    }
}

async function handleQuery(event) {
    event.preventDefault();

    const summary = document.getElementById('summary').value;
    const duration = document.getElementById('duration').value;
    const priority = document.getElementById('priority').value;

    const formData = new FormData();
    formData.append('summary', summary);
    formData.append('duration_min', duration);
    formData.append('priority_type', priority);
    formData.append('cache_key', currentCacheKey);
    formData.append('user_session', sessionId);

    const submitBtn = queryForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Finding slots...';

    showResult(queryResult, 'Finding optimal time slots...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/flow/user_query+recommendation`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail?.error || result.detail || 'Query failed');
        }

        showResult(queryResult, formatRecommendationResult(result), 'success');

    } catch (error) {
        showResult(queryResult, `Error: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Get Recommendations';
    }
}

function showResult(element, content, type) {
    element.className = `result-panel ${type}`;
    element.innerHTML = content;
    element.classList.remove('hidden');
}

function formatAnalysisResult(result) {
    return `
        <h3>✅ Calendar Analysis Complete</h3>
        <div class="stats">
            <div class="stat-item">
                <strong>Events Imported:</strong> ${result.counts?.imported || 0}
            </div>
            <div class="stat-item">
                <strong>Events Enriched:</strong> ${result.counts?.enriched || 0}
            </div>
            <div class="stat-item">
                <strong>Cache Key:</strong> <code>${result.cache_key}</code>
            </div>
            <div class="stat-item">
                <strong>Status:</strong> ${result.message}
            </div>
        </div>
        <p class="next-step">✨ Now you can search for optimal time slots below!</p>
    `;
}

async function fetchAnalytics(cacheKey) {
    try {
        const resp = await fetch(`${API_BASE}/flow/analytics?cache_key=${cacheKey}`);
        if (!resp.ok) return;
        const data = await resp.json();
        analysisResult.innerHTML += formatAnalytics(data);
    } catch (err) {
        console.error('Analytics fetch failed', err);
    }
}

function formatAnalytics(data) {
    const agg = data.dashboard_aggregates || {};
    return `
        <h3>📊 Analytics</h3>
        <div class="stats">
            <div class="stat-item"><strong>Total events:</strong> ${agg.total_events || 0}</div>
            <div class="stat-item"><strong>Meetings hours:</strong> ${agg.meetings_hours || 0}</div>
            <div class="stat-item"><strong>Focus hours:</strong> ${agg.focus_hours || 0}</div>
        </div>
    `;
}

function formatRecommendationResult(result) {
    let html = '<h3>🎯 Time Slot Recommendations</h3>';

    if (result.recommendation) {
        const rec = result.recommendation;
        html += `
            <div class="recommendation primary">
                <h4>🏆 Best Recommendation</h4>
                <div class="time-slot">
                    <strong>Time:</strong> ${formatDateTime(rec.slot.start)} - ${formatDateTime(rec.slot.end)}
                </div>
                <div class="score">
                    <strong>Score:</strong> ${Math.round(rec.score * 100)}%
                </div>
                <div class="rationale">
                    <strong>Why this slot:</strong>
                    <ul>
                        ${rec.rationale.map(reason => `<li>${reason}</li>`).join('')}
                    </ul>
                </div>
            </div>
        `;
    }

    if (result.alternatives && result.alternatives.length > 0) {
        html += '<div class="alternatives"><h4>📋 Alternative Options</h4>';
        result.alternatives.forEach((alt, index) => {
            html += `
                <div class="recommendation alternative">
                    <div class="time-slot">
                        <strong>Option ${index + 1}:</strong> ${formatDateTime(alt.slot.start)} - ${formatDateTime(alt.slot.end)}
                    </div>
                    <div class="score">Score: ${Math.round(alt.score * 100)}%</div>
                </div>
            `;
        });
        html += '</div>';
    }

    if (result.search_stats) {
        html += `
            <div class="search-stats">
                <h4>📊 Search Statistics</h4>
                <div class="stats">
                    <span>Slots found: ${result.search_stats.slots_found}</span>
                    <span>Slots evaluated: ${result.search_stats.slots_evaluated}</span>
                    <span>Search days: ${result.search_stats.search_days}</span>
                </div>
            </div>
        `;
    }

    return html;
}

function formatDateTime(dateTimeStr) {
    const date = new Date(dateTimeStr);
    return date.toLocaleString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}