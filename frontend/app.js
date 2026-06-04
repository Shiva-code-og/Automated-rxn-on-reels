// AutoReact Dashboard Logic

// State management
let appState = {
    status: 'idle', // idle, logging_in, 2fa_needed, connected, error
    username: '',
    is_running: false,
    logs: [],
    config: {
        react_target: 'all',
        specific_usernames: '',
        selected_emojis: '❤️,🔥,😂,😮,👏',
        use_random_emoji: false,
        poll_interval: 5,
        use_gemini: false,
        gemini_api_key: ''
    },
    // Available default emojis for the quick-select list
    defaultEmojis: ['❤️', '🔥', '😂', '😮', '👏', '🙌', '😍', '👍', '💯'],
    // Fetched friend list from DMs
    friends: []
};


async function authFetch(url, options = {}) {
    const token = localStorage.getItem('auto_react_token');
    if (!options.headers) options.headers = {};
    if (token) {
        options.headers['Authorization'] = 'Bearer ' + token;
    }
    const res = await fetch(url, options);
    if (res.status === 401) {
        localStorage.removeItem('auto_react_token');
        appState.status = 'idle';
        appState.username = '';
        updateUIState();
        throw new Error('Session expired. Please log in again.');
    }
    return res;
}

// DOM Elements
const loginScreen = document.getElementById('login-screen');
const dashboardScreen = document.getElementById('dashboard-screen');
const loginForm = document.getElementById('login-form');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const togglePasswordBtn = document.getElementById('toggle-password');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');
const errorMessage = document.getElementById('error-message');

const twoFactorModal = document.getElementById('twofactor-modal');
const twoFactorForm = document.getElementById('twofactor-form');
const twoFactorCodeInput = document.getElementById('twofactor-code');
const cancel2faBtn = document.getElementById('cancel-2fa');
const submit2faBtn = document.getElementById('submit-2fa');
const twoFactorError = document.getElementById('twofactor-error');
const twoFactorErrorMessage = document.getElementById('twofactor-error-message');

const displayUsername = document.getElementById('display-username');
const logoutBtn = document.getElementById('logout-btn');

const workerStatusPulse = document.getElementById('worker-status-pulse');
const workerStatusTitle = document.getElementById('worker-status-title');
const workerStatusDesc = document.getElementById('worker-status-desc');
const workerToggle = document.getElementById('worker-toggle');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnCheckNow = document.getElementById('btn-check-now');

const configForm = document.getElementById('config-form');
const specificUsernamesGroup = document.getElementById('specific-usernames-group');
const specificUsernamesInput = document.getElementById('specific-usernames');
const friendsSelectorContainer = document.getElementById('friends-selector-container');
const useRandomEmojiInput = document.getElementById('use-random-emoji');
const pollIntervalInput = document.getElementById('poll-interval');
const intervalDisplay = document.getElementById('interval-display');
const configStatus = document.getElementById('config-status');
const emojiBadgeContainer = document.getElementById('emoji-badge-container');
const addCustomEmojiInput = document.getElementById('add-custom-emoji');
const btnAddEmoji = document.getElementById('btn-add-emoji');
const useGeminiInput = document.getElementById('use-gemini');
const geminiApiKeyGroup = document.getElementById('gemini-api-key-group');
const geminiApiKeyInput = document.getElementById('gemini-api-key');
const toggleGeminiKeyBtn = document.getElementById('toggle-gemini-key');

const logListContainer = document.getElementById('log-list-container');
const totalReactedBadge = document.getElementById('total-reacted-badge');
const btnClearLogs = document.getElementById('btn-clear-logs');

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    const token = localStorage.getItem('auto_react_token');\n    if (!token) return;\n    fetchStatus().then(() => {
        if (appState.status === 'connected') {
            fetchConfig().then(() => fetchFriends());
            fetchLogs();
        }
    });
    
    // Periodically poll status & logs (every 5 seconds)
    setInterval(() => {
        if (appState.status === 'connected') {
            fetchStatus();
            fetchLogs();
        } else {
            fetchStatus();
        }
    }, 5000);
});

// Event Listeners
function initEventListeners() {
    // Password toggler
    togglePasswordBtn.addEventListener('click', () => {
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);
        const icon = togglePasswordBtn.querySelector('i');
        icon.className = type === 'password' ? 'fa-regular fa-eye' : 'fa-regular fa-eye-slash';
    });

    // Login submit
    loginForm.addEventListener('submit', handleLogin);

    // 2FA modal actions
    twoFactorForm.addEventListener('submit', handleTwoFactorSubmit);
    cancel2faBtn.addEventListener('click', close2faModal);

    // Logout
    logoutBtn.addEventListener('click', handleLogout);

    // Worker triggers
    workerToggle.addEventListener('change', toggleWorker);
    btnStart.addEventListener('click', startWorker);
    btnStop.addEventListener('click', stopWorker);
    btnCheckNow.addEventListener('click', checkNow);

    // Target Selection Conditional Toggle
    document.querySelectorAll('input[name="react_target"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            toggleTargetSelection(e.target.value);
        });
    });

    // Interval slider dynamic display
    pollIntervalInput.addEventListener('input', (e) => {
        intervalDisplay.textContent = `${e.target.value} mins`;
    });

    // Custom Emoji Addition
    btnAddEmoji.addEventListener('click', addCustomEmoji);
    addCustomEmojiInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addCustomEmoji();
        }
    });

    // Save Configuration
    configForm.addEventListener('submit', saveConfiguration);

    // Gemini toggling
    useGeminiInput.addEventListener('change', (e) => {
        toggleGeminiSection(e.target.checked);
    });

    // Toggle Gemini key visibility
    toggleGeminiKeyBtn.addEventListener('click', () => {
        const type = geminiApiKeyInput.getAttribute('type') === 'password' ? 'text' : 'password';
        geminiApiKeyInput.setAttribute('type', type);
        const icon = toggleGeminiKeyBtn.querySelector('i');
        icon.className = type === 'password' ? 'fa-regular fa-eye' : 'fa-regular fa-eye-slash';
    });

    // Clear Logs
    btnClearLogs.addEventListener('click', clearLogsHistory);
}

// ------------------- API OPERATIONS -------------------

// Fetch current backend status
async function fetchStatus() {
    try {
        const res = await authFetch('/api/status');
        const data = await res.json();
        
        const oldStatus = appState.status;
        appState.status = data.status;
        appState.username = data.username;
        appState.is_running = data.is_running;
        
        updateUIState();
        
        // If status just shifted to connected, load settings & logs
        if (oldStatus !== 'connected' && appState.status === 'connected') {
            fetchConfig().then(() => fetchFriends());
            fetchLogs();
        }
    } catch (err) {
        console.error("Error fetching status:", err);
    }
}

// Fetch Configurations
async function fetchConfig() {
    try {
        const res = await authFetch('/api/config');
        const data = await res.json();
        appState.config = data;
        
        // Populate inputs
        document.querySelector(`input[name="react_target"][value="${data.react_target}"]`).checked = true;
        toggleTargetSelection(data.react_target);
        
        // Sync hidden input with saved value
        specificUsernamesInput.value = data.specific_usernames;
        
        // Update friend selector pill states if friends are already loaded
        if (appState.friends.length > 0) {
            updateFriendsSelectorSelection();
        }
        useRandomEmojiInput.checked = data.use_random_emoji;
        pollIntervalInput.value = data.poll_interval;
        intervalDisplay.textContent = `${data.poll_interval} mins`;
        
        useGeminiInput.checked = data.use_gemini;
        toggleGeminiSection(data.use_gemini);
        geminiApiKeyInput.value = data.gemini_api_key || '';
        
        // Render emojis badges
        renderEmojiBadges();
    } catch (err) {
        console.error("Error fetching config:", err);
    }
}

// Fetch Log entries
async function fetchLogs() {
    try {
        const res = await authFetch('/api/logs');
        const data = await res.json();
        appState.logs = data;
        renderLogs();
    } catch (err) {
        console.error("Error fetching logs:", err);
    }
}

// Handle login form submission
async function handleLogin(e) {
    e.preventDefault();
    loginBtn.classList.add('loading');
    loginBtn.disabled = true;
    loginError.style.display = 'none';
    
    const payload = {
        username: usernameInput.value.trim(),
        password: passwordInput.value
    };
    
    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || "Authentication failed.");
        }
        
        if (data.status === '2fa_needed') {
            appState.status = '2fa_needed';
            appState.username = payload.username;
            open2faModal();
        } else {
            localStorage.setItem('auto_react_token', data.token);
            appState.status = 'connected';
            appState.username = payload.username;
            fetchConfig().then(() => fetchFriends());
            fetchLogs();
        }
    } catch (err) {
        errorMessage.textContent = err.message;
        loginError.style.display = 'flex';
    } finally {
        loginBtn.classList.remove('loading');
        loginBtn.disabled = false;
    }
}

// Handle 2FA verification code submission
async function handleTwoFactorSubmit(e) {
    e.preventDefault();
    submit2faBtn.classList.add('loading');
    submit2faBtn.disabled = true;
    twoFactorError.style.display = 'none';
    
    const payload = {
        code: twoFactorCodeInput.value.trim(),\n        username: appState.username
    };
    
    try {
        const res = await fetch('/api/login/2fa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || "Verification failed.");
        }
        
        localStorage.setItem('auto_react_token', data.token);\n        twoFactorModal.classList.remove('active');
        appState.status = 'connected';
        await fetchStatus();
    } catch (err) {
        twoFactorErrorMessage.textContent = err.message;
        twoFactorError.style.display = 'flex';
    } finally {
        submit2faBtn.classList.remove('loading');
        submit2faBtn.disabled = false;
    }
}

let logoutConfirmTimeout = null;

// Handle Disconnect/Logout
async function handleLogout() {
    const btn = document.getElementById('logout-btn');
    if (!btn.classList.contains('confirm-state')) {
        btn.classList.add('confirm-state');
        btn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
        btn.title = "Click again to confirm disconnect";
        
        logoutConfirmTimeout = setTimeout(() => {
            btn.classList.remove('confirm-state');
            btn.innerHTML = '<i class="fa-solid fa-power-off"></i>';
            btn.title = "Disconnect Account";
        }, 3000);
        return;
    }
    
    clearTimeout(logoutConfirmTimeout);
    btn.classList.remove('confirm-state');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    
    try {
        await authFetch('/api/logout', { method: 'POST' });\n        localStorage.removeItem('auto_react_token');
        appState.status = 'idle';
        appState.username = '';
        appState.is_running = false;
        
        // Reset forms
        usernameInput.value = '';
        passwordInput.value = '';
        
        updateUIState();
    } catch (err) {
        console.error("Logout failed:", err);
    } finally {
        btn.innerHTML = '<i class="fa-solid fa-power-off"></i>';
        btn.title = "Disconnect Account";
    }
}

// Start worker
async function startWorker() {
    try {
        const res = await authFetch('/api/control/start', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            appState.is_running = true;
            updateWorkerStatusUI();
        } else {
            alert(data.detail || "Failed to start monitoring.");
        }
    } catch (err) {
        console.error("Start worker failed:", err);
    }
}

// Stop worker
async function stopWorker() {
    try {
        await authFetch('/api/control/stop', { method: 'POST' });
        appState.is_running = false;
        updateWorkerStatusUI();
    } catch (err) {
        console.error("Stop worker failed:", err);
    }
}

// Toggle background worker from checkbox
function toggleWorker() {
    if (workerToggle.checked) {
        startWorker();
    } else {
        stopWorker();
    }
}

// Force immediate DM check
async function checkNow() {
    btnCheckNow.disabled = true;
    btnCheckNow.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';
    try {
        const res = await authFetch('/api/control/check-now', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            // Wait a moment then refresh logs
            setTimeout(() => {
                fetchLogs();
                btnCheckNow.disabled = false;
                btnCheckNow.innerHTML = '<i class="fa-solid fa-bolt"></i> Check Now';
            }, 8000);
        } else {
            alert(data.detail || 'Failed to trigger check.');
            btnCheckNow.disabled = false;
            btnCheckNow.innerHTML = '<i class="fa-solid fa-bolt"></i> Check Now';
        }
    } catch (err) {
        console.error('Check now failed:', err);
        btnCheckNow.disabled = false;
        btnCheckNow.innerHTML = '<i class="fa-solid fa-bolt"></i> Check Now';
    }
}

// Save configuration settings
async function saveConfiguration(e) {
    e.preventDefault();
    
    const target = document.querySelector('input[name="react_target"]:checked').value;
    const selectedEmojis = appState.config.selected_emojis;
    
    const payload = {
        react_target: target,
        specific_usernames: (specificUsernamesInput.value || '').trim(),
        selected_emojis: selectedEmojis,
        use_random_emoji: useRandomEmojiInput.checked,
        poll_interval: parseInt(pollIntervalInput.value),
        use_gemini: useGeminiInput.checked,
        gemini_api_key: geminiApiKeyInput.value.trim()
    };
    
    try {
        const res = await authFetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            configStatus.className = 'alert-box success';
            configStatus.innerHTML = '<i class="fa-solid fa-circle-check"></i> Settings saved successfully!';
            configStatus.style.display = 'flex';
            setTimeout(() => {
                configStatus.style.display = 'none';
            }, 3000);
        } else {
            const data = await res.json();
            configStatus.className = 'alert-box danger';
            configStatus.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> ${data.detail || "Error saving configuration."}`;
            configStatus.style.display = 'flex';
            setTimeout(() => {
                configStatus.style.display = 'none';
            }, 5000);
        }
    } catch (err) {
        console.error("Save config failed:", err);
        configStatus.className = 'alert-box danger';
        configStatus.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Connection error.`;
        configStatus.style.display = 'flex';
        setTimeout(() => {
            configStatus.style.display = 'none';
        }, 5000);
    }
}

let clearConfirmTimeout = null;

// Clear log history
async function clearLogsHistory() {
    const btn = document.getElementById('btn-clear-logs');
    
    if (!btn.classList.contains('confirm-state')) {
        btn.classList.add('confirm-state');
        btn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Confirm?';
        btn.title = "Click again to clear logs";
        
        clearConfirmTimeout = setTimeout(() => {
            btn.classList.remove('confirm-state');
            btn.innerHTML = '<i class="fa-regular fa-trash-can"></i> Clear';
            btn.title = "Clear logs from database";
        }, 3000);
        return;
    }
    
    clearTimeout(clearConfirmTimeout);
    btn.classList.remove('confirm-state');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Clearing...';
    
    try {
        const res = await authFetch('/api/logs/clear', { method: 'POST' });
        if (res.ok) {
            appState.logs = [];
            renderLogs();
        } else {
            alert("Failed to clear logs from database.");
        }
    } catch (err) {
        console.error("Clear logs failed:", err);
        alert("Error connecting to server. Could not clear logs.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-regular fa-trash-can"></i> Clear';
        btn.title = "Clear logs from database";
    }
}

// ------------------- UI UTILITIES -------------------

// Update visibility of screens and modal overlays based on state
function updateUIState() {
    if (appState.status === 'connected') {
        loginScreen.classList.remove('active');
        dashboardScreen.classList.add('active');
        displayUsername.textContent = `@${appState.username}`;
        updateWorkerStatusUI();
    } else if (appState.status === '2fa_needed') {
        open2faModal();
    } else {
        // Disconnected or setup error states
        dashboardScreen.classList.remove('active');
        loginScreen.classList.add('active');
        
        if (appState.status === 'error' && appState.error_message) {
            errorMessage.textContent = appState.error_message;
            loginError.style.display = 'flex';
        }
    }
}

// Manage 2FA modal state
function open2faModal() {
    twoFactorModal.classList.add('active');
    twoFactorCodeInput.focus();
}

function close2faModal() {
    localStorage.setItem('auto_react_token', data.token);\n        twoFactorModal.classList.remove('active');
    appState.status = 'idle';
    updateUIState();
}

// Toggle usernames input field visibility based on selection
function toggleTargetSelection(value) {
    if (value === 'specific') {
        specificUsernamesGroup.classList.add('active');
        // Re-fetch friends when switching to specific list if they haven't been loaded yet
        if (appState.friends.length === 0 && appState.status === 'connected') {
            fetchFriends();
        }
    } else {
        specificUsernamesGroup.classList.remove('active');
    }
}

function toggleGeminiSection(enabled) {
    if (enabled) {
        geminiApiKeyGroup.classList.add('active');
        geminiApiKeyInput.required = true;
    } else {
        geminiApiKeyGroup.classList.remove('active');
        geminiApiKeyInput.required = false;
    }
}

// Toggle background worker statuses on the control center UI
function updateWorkerStatusUI() {
    if (appState.is_running) {
        workerStatusPulse.className = 'pulse-indicator running';
        workerStatusTitle.textContent = 'Monitoring Running';
        workerStatusDesc.textContent = 'Auto-react worker is polling and processing direct messages.';
        workerToggle.checked = true;
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        workerStatusPulse.className = 'pulse-indicator idle';
        workerStatusTitle.textContent = 'Monitoring Paused';
        workerStatusDesc.textContent = 'Automated reactions are currently paused.';
        workerToggle.checked = false;
        btnStart.disabled = false;
        btnStop.disabled = true;
    }
}

// Render dynamic emoji selection tags
function renderEmojiBadges() {
    emojiBadgeContainer.innerHTML = '';
    
    // Parse current configured emojis
    const activeEmojis = appState.config.selected_emojis.split(',').map(e => e.trim()).filter(Boolean);
    
    // Group active custom emojis with defaults to list them
    const allUniqueEmojis = Array.from(new Set([...appState.defaultEmojis, ...activeEmojis]));
    
    allUniqueEmojis.forEach(emoji => {
        const isSelected = activeEmojis.includes(emoji);
        
        const badge = document.createElement('div');
        badge.className = `emoji-badge ${isSelected ? 'selected' : ''}`;
        badge.innerHTML = `
            <span>${emoji}</span>
            <div class="remove-emoji" title="Remove emoji">&times;</div>
        `;
        
        // Toggle selected state
        badge.addEventListener('click', (e) => {
            // Prevent close trigger from clicking the badge itself
            if (e.target.classList.contains('remove-emoji')) return;
            
            toggleEmojiSelection(emoji, badge);
        });
        
        // Remove emoji button handler
        const removeBtn = badge.querySelector('.remove-emoji');
        removeBtn.addEventListener('click', () => {
            removeEmoji(emoji);
        });
        
        emojiBadgeContainer.appendChild(badge);
    });
}

// Handle toggle selection for emoji badges
function toggleEmojiSelection(emoji, element) {
    let activeEmojis = appState.config.selected_emojis.split(',').map(e => e.trim()).filter(Boolean);
    
    if (activeEmojis.includes(emoji)) {
        // Remove if selected, unless it's the last emoji left
        if (activeEmojis.length === 1) {
            alert("You must keep at least one reaction emoji.");
            return;
        }
        activeEmojis = activeEmojis.filter(e => e !== emoji);
        element.classList.remove('selected');
    } else {
        // Add if not selected
        activeEmojis.push(emoji);
        element.classList.add('selected');
    }
    
    appState.config.selected_emojis = activeEmojis.join(',');
}

// Remove custom emoji completely
function removeEmoji(emoji) {
    // Prevent removing defaults, only custom
    if (appState.defaultEmojis.includes(emoji)) {
        // Just de-select it from active selection if selected
        let activeEmojis = appState.config.selected_emojis.split(',').map(e => e.trim()).filter(Boolean);
        if (activeEmojis.includes(emoji)) {
            if (activeEmojis.length === 1) {
                alert("You must keep at least one reaction emoji.");
                return;
            }
            activeEmojis = activeEmojis.filter(e => e !== emoji);
            appState.config.selected_emojis = activeEmojis.join(',');
            renderEmojiBadges();
        }
        return;
    }
    
    // Filter active emojis list
    let activeEmojis = appState.config.selected_emojis.split(',').map(e => e.trim()).filter(Boolean);
    activeEmojis = activeEmojis.filter(e => e !== emoji);
    appState.config.selected_emojis = activeEmojis.join(',');
    
    renderEmojiBadges();
}

// Add user custom emoji
function addCustomEmoji() {
    const inputVal = addCustomEmojiInput.value.trim();
    // Validate if it is a single emoji character (rough validation)
    if (!inputVal) return;
    
    // Clean input
    addCustomEmojiInput.value = '';
    
    let activeEmojis = appState.config.selected_emojis.split(',').map(e => e.trim()).filter(Boolean);
    
    if (activeEmojis.includes(inputVal)) {
        return; // already active
    }
    
    activeEmojis.push(inputVal);
    appState.config.selected_emojis = activeEmojis.join(',');
    
    renderEmojiBadges();
}

// Render dynamic log rows
function renderLogs() {
    totalReactedBadge.textContent = `${appState.logs.length} reacted`;
    
    if (appState.logs.length === 0) {
        logListContainer.innerHTML = `
            <div class="empty-log-state">
                <i class="fa-solid fa-satellite-dish"></i>
                <h4>No Activity Logged</h4>
                <p>Reels sent by your friends will show up here as soon as the background worker detects and reacts to them.</p>
            </div>
        `;
        return;
    }
    
    logListContainer.innerHTML = '';
    
    appState.logs.forEach(log => {
        const item = document.createElement('div');
        item.className = 'log-item';
        
        // Safely parse YYYY-MM-DD HH:MM:SS format by replacing space with T (making it ISO compliant)
        let rawTime;
        if (log.local_timestamp) {
            rawTime = new Date(log.local_timestamp.replace(' ', 'T'));
        } else {
            rawTime = new Date();
        }
        
        // Check if date is valid before calling toLocaleString
        const isValidDate = rawTime instanceof Date && !isNaN(rawTime.getTime());
        const displayTime = isValidDate ? rawTime.toLocaleString([], { 
            month: 'short', 
            day: 'numeric', 
            hour: '2-digit', 
            minute: '2-digit' 
        }) : (log.local_timestamp || 'Just now');
        
        item.innerHTML = `
            <div class="log-info-group">
                <div class="log-avatar">
                    <i class="fa-solid fa-user-friends"></i>
                </div>
                <div class="log-details">
                    <span class="log-sender">@${log.sender_username}</span>
                    <span class="log-subtitle">${log.thread_title} • ${log.message_text}</span>
                    <span class="log-time"><i class="fa-regular fa-clock"></i> ${displayTime}</span>
                </div>
            </div>
            <div class="log-actions-group">
                <a href="${log.reel_url}" target="_blank" class="log-view-btn">
                    <i class="fa-solid fa-video"></i> View Reel
                </a>
                <div class="log-reaction-badge" title="Reaction sent">
                    ${log.reaction_emoji}
                </div>
            </div>
        `;
        
        logListContainer.appendChild(item);
    });
}

// ------------------- FRIEND SELECTOR LOGIC -------------------

// Fetch recent DM friends from backend
async function fetchFriends() {
    if (appState.status !== 'connected') return;
    
    try {
        friendsSelectorContainer.innerHTML = '<span class="friends-loading-text"><i class="fa-solid fa-spinner fa-spin"></i> Loading friends from DMs...</span>';
        
        const res = await authFetch('/api/friends');
        const data = await res.json();
        appState.friends = data;
        renderFriendsSelector(data);
    } catch (err) {
        console.error('Error fetching friends:', err);
        friendsSelectorContainer.innerHTML = '<span class="friends-loading-text"><i class="fa-solid fa-circle-exclamation"></i> Could not load friends. Connect your account first.</span>';
    }
}

// Render clickable friend pills into the selector container
function renderFriendsSelector(friends) {
    friendsSelectorContainer.innerHTML = '';
    
    if (!friends || friends.length === 0) {
        friendsSelectorContainer.innerHTML = '<span class="friends-loading-text"><i class="fa-solid fa-user-slash"></i> No recent DM friends found.</span>';
        return;
    }
    
    // Parse currently saved selected usernames
    const savedUsernames = (specificUsernamesInput.value || '').split(',').map(u => u.trim().toLowerCase()).filter(Boolean);
    
    friends.forEach(friend => {
        const isSelected = savedUsernames.includes(friend.username.toLowerCase());
        
        const pill = document.createElement('div');
        pill.className = `friend-select-pill ${isSelected ? 'selected' : ''}`;
        pill.dataset.username = friend.username;
        
        const displayName = friend.full_name ? `${friend.full_name}` : friend.username;
        pill.innerHTML = `
            <i class="avatar-icon ${isSelected ? 'fa-solid fa-check' : 'fa-solid fa-user-astronaut'}"></i>
            <span>${displayName}</span>
        `;
        pill.title = `@${friend.username}`;
        
        pill.addEventListener('click', () => {
            toggleFriendSelection(friend.username, pill);
        });
        
        friendsSelectorContainer.appendChild(pill);
    });
}

// Toggle a friend's selected state and update the hidden input
function toggleFriendSelection(username, pill) {
    let selectedUsernames = (specificUsernamesInput.value || '').split(',').map(u => u.trim()).filter(Boolean);
    const icon = pill.querySelector('.avatar-icon');
    
    if (pill.classList.contains('selected')) {
        // Deselect
        pill.classList.remove('selected');
        icon.className = 'avatar-icon fa-solid fa-user-astronaut';
        selectedUsernames = selectedUsernames.filter(u => u.toLowerCase() !== username.toLowerCase());
    } else {
        // Select
        pill.classList.add('selected');
        icon.className = 'avatar-icon fa-solid fa-check';
        if (!selectedUsernames.map(u => u.toLowerCase()).includes(username.toLowerCase())) {
            selectedUsernames.push(username);
        }
    }
    
    specificUsernamesInput.value = selectedUsernames.join(', ');
}

// Sync pill selection states with the current config value
function updateFriendsSelectorSelection() {
    const savedUsernames = (specificUsernamesInput.value || '').split(',').map(u => u.trim().toLowerCase()).filter(Boolean);
    
    const pills = friendsSelectorContainer.querySelectorAll('.friend-select-pill');
    pills.forEach(pill => {
        const username = (pill.dataset.username || '').toLowerCase();
        const icon = pill.querySelector('.avatar-icon');
        
        if (savedUsernames.includes(username)) {
            pill.classList.add('selected');
            if (icon) icon.className = 'avatar-icon fa-solid fa-check';
        } else {
            pill.classList.remove('selected');
            if (icon) icon.className = 'avatar-icon fa-solid fa-user-astronaut';
        }
    });
}
