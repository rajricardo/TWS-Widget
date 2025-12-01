// Status message
const statusMessage = document.getElementById('statusMessage');

// Trading DOM elements
const tradingSection = document.getElementById('tradingSection');
const tickerInput = document.getElementById('ticker');
const quantityInput = document.getElementById('quantity');
const expiryInput = document.getElementById('expiry');
const strikeInput = document.getElementById('strike');
const buyBtn = document.getElementById('buyBtn');
const closeAllBtn = document.getElementById('closeAllBtn');
const refreshPriceBtn = document.getElementById('refreshPriceBtn');

// Portfolio elements
const portfolioBalance = document.getElementById('portfolioBalance');
const dailyPnLElement = document.getElementById('dailyPnL');

// Confirmation dialog
const confirmDialog = document.getElementById('confirmDialog');
const confirmDetails = document.getElementById('confirmDetails');
const confirmBtn = document.getElementById('confirmBtn');
const cancelBtn = document.getElementById('cancelBtn');

// Settings DOM elements
const settingsBtn = document.getElementById('settingsBtn');
const settingsDialog = document.getElementById('settingsDialog');
const closeSettingsBtn = document.getElementById('closeSettingsBtn');
const settingsHost = document.getElementById('settingsHost');
const settingsPort = document.getElementById('settingsPort');
const settingsClientId = document.getElementById('settingsClientId');

// Watchlist DOM elements
const newTickerInput = document.getElementById('newTicker');
const addTickerBtn = document.getElementById('addTickerBtn');
const tickerList = document.getElementById('tickerList');

// Reconnect dialog
const reconnectDialog = document.getElementById('reconnectDialog');
const reconnectConfirmBtn = document.getElementById('reconnectConfirmBtn');
const reconnectCancelBtn = document.getElementById('reconnectCancelBtn');

let isConnected = false;
let refreshInterval = null;
let pendingOrder = null;
let connectionSettingsChanged = false;

// Settings management
const SETTINGS_KEY = 'turbo_trader_settings';

async function loadSettings() {
    const savedSettings = localStorage.getItem(SETTINGS_KEY);
    if (savedSettings) {
        return JSON.parse(savedSettings);
    }

    const envSettings = await window.api.getConnectionSettings();

    return {
        host: envSettings.host,
        port: envSettings.port,
        clientId: envSettings.clientId,
        theme: 'dark',
        fontSize: 'medium',
        watchlist: ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT']
    };
}

function saveSettings(settings) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

function applyTheme(theme) {
    if (theme === 'light') {
        document.body.classList.add('light-theme');
    } else {
        document.body.classList.remove('light-theme');
    }
}

function applyFontSize(size) {
    document.body.classList.remove('font-small', 'font-medium', 'font-large');
    document.body.classList.add(`font-${size}`);
}

function populateTickerDropdown(watchlist) {
    tickerInput.innerHTML = '<option value="">Select Symbol</option>';
    watchlist.forEach(ticker => {
        const option = document.createElement('option');
        option.value = ticker;
        option.textContent = ticker;
        tickerInput.appendChild(option);
    });
}

function renderWatchlist(watchlist) {
    tickerList.innerHTML = '';
    watchlist.forEach(ticker => {
        const tickerItem = document.createElement('div');
        tickerItem.className = 'ticker-item';
        tickerItem.innerHTML = `
            <span class="ticker-symbol">${ticker}</span>
            <button class="remove-ticker" data-ticker="${ticker}">×</button>
        `;
        tickerList.appendChild(tickerItem);
    });

    document.querySelectorAll('.remove-ticker').forEach(btn => {
        btn.addEventListener('click', async () => {
            const ticker = btn.dataset.ticker;
            const currentSettings = await loadSettings();
            currentSettings.watchlist = currentSettings.watchlist.filter(t => t !== ticker);
            saveSettings(currentSettings);
            renderWatchlist(currentSettings.watchlist);
            populateTickerDropdown(currentSettings.watchlist);
        });
    });
}

async function addTicker() {
    const ticker = newTickerInput.value.trim().toUpperCase();
    if (!ticker) return;

    const currentSettings = await loadSettings();
    if (!currentSettings.watchlist.includes(ticker)) {
        currentSettings.watchlist.push(ticker);
        saveSettings(currentSettings);
        renderWatchlist(currentSettings.watchlist);
        populateTickerDropdown(currentSettings.watchlist);
    }
    newTickerInput.value = '';
}

async function initializeSettings() {
    const settings = await loadSettings();
    applyTheme(settings.theme);
    applyFontSize(settings.fontSize);
    populateTickerDropdown(settings.watchlist);
    return settings;
}

// Set default expiry date to today
const today = new Date().toISOString().split('T')[0];
expiryInput.value = today;

// Event listeners for ticker change and refresh button
tickerInput.addEventListener('change', async () => {
    if (isConnected && tickerInput.value) {
        await fetchAndPopulatePrice();
    }
});

refreshPriceBtn.addEventListener('click', async () => {
    await fetchAndPopulatePrice();
});

// Get option type from radio buttons
function getOptionType() {
    const radioButtons = document.getElementsByName('optionType');
    for (const radio of radioButtons) {
        if (radio.checked) {
            return radio.value;
        }
    }
    return 'C'; // Default to Call
}

async function fetchAndPopulatePrice() {
    const ticker = tickerInput.value.trim().toUpperCase();

    if (!ticker) {
        showStatus('Please select a ticker symbol first', 'error');
        return;
    }

    try {
        refreshPriceBtn.disabled = true;
        refreshPriceBtn.classList.add('loading');

        const result = await window.api.getTickerPrice(ticker);

        if (result.success && result.price > 0) {
            strikeInput.value = Math.floor(result.price).toFixed(2);
        } else {
            showStatus(result.message || 'Failed to fetch price', 'error');
        }
    } catch (error) {
        showStatus(`Error fetching price: ${error.message}`, 'error');
    } finally {
        refreshPriceBtn.disabled = false;
        refreshPriceBtn.classList.remove('loading');
    }
}

// Auto-connect on page load
window.addEventListener('DOMContentLoaded', async () => {
    await initializeSettings();
    await handleConnect();
});

settingsBtn.addEventListener('click', async () => {
    const currentSettings = await loadSettings();
    settingsHost.value = currentSettings.host;
    settingsPort.value = currentSettings.port;
    settingsClientId.value = currentSettings.clientId;

    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === currentSettings.theme);
    });

    document.querySelectorAll('.font-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.size === currentSettings.fontSize);
    });

    renderWatchlist(currentSettings.watchlist);

    connectionSettingsChanged = false;
    settingsDialog.style.display = 'flex';
});

closeSettingsBtn.addEventListener('click', () => {
    settingsDialog.style.display = 'none';
    if (connectionSettingsChanged) {
        reconnectDialog.style.display = 'flex';
    }
});

settingsDialog.addEventListener('click', (e) => {
    if (e.target === settingsDialog) {
        settingsDialog.style.display = 'none';
        if (connectionSettingsChanged) {
            reconnectDialog.style.display = 'flex';
        }
    }
});

settingsHost.addEventListener('change', async () => {
    const currentSettings = await loadSettings();
    currentSettings.host = settingsHost.value.trim() || '127.0.0.1';
    saveSettings(currentSettings);
    await window.api.updateConnectionSettings(currentSettings);
    connectionSettingsChanged = true;
});

settingsPort.addEventListener('change', async () => {
    const currentSettings = await loadSettings();
    currentSettings.port = settingsPort.value.trim() || '4002';
    saveSettings(currentSettings);
    await window.api.updateConnectionSettings(currentSettings);
    connectionSettingsChanged = true;
});

settingsClientId.addEventListener('change', async () => {
    const currentSettings = await loadSettings();
    currentSettings.clientId = settingsClientId.value.trim() || '1';
    saveSettings(currentSettings);
    await window.api.updateConnectionSettings(currentSettings);
    connectionSettingsChanged = true;
});

document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        const theme = btn.dataset.theme;
        const currentSettings = await loadSettings();
        currentSettings.theme = theme;
        saveSettings(currentSettings);

        applyTheme(theme);

        document.querySelectorAll('.theme-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

document.querySelectorAll('.font-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        const size = btn.dataset.size;
        const currentSettings = await loadSettings();
        currentSettings.fontSize = size;
        saveSettings(currentSettings);

        applyFontSize(size);

        document.querySelectorAll('.font-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

addTickerBtn.addEventListener('click', addTicker);

newTickerInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        addTicker();
    }
});

reconnectConfirmBtn.addEventListener('click', async () => {
    reconnectDialog.style.display = 'none';
    location.reload();
});

reconnectCancelBtn.addEventListener('click', () => {
    reconnectDialog.style.display = 'none';
    connectionSettingsChanged = false;
});

reconnectDialog.addEventListener('click', (e) => {
    if (e.target === reconnectDialog) {
        reconnectDialog.style.display = 'none';
        connectionSettingsChanged = false;
    }
});

async function handleConnect() {
    try {
        showStatus('<span class="spinner"></span>Connecting to TWS...', 'connecting');

        const currentSettings = await loadSettings();
        await window.api.updateConnectionSettings(currentSettings);

        const result = await window.api.connectTWS();

        if (result.success) {
            showStatus(result.message, 'success');
            isConnected = true;

            enableTradingSection();

            tradingSection.style.display = 'block';

            await refreshBalance();
            await refreshDailyPnL();

            startAutoRefresh();
        } else {
            showStatus(result.message, 'error');
        }
    } catch (error) {
        showStatus(`Error: ${error.message}`, 'error');
    }
}

// Trading functionality
buyBtn.addEventListener('click', () => {
    showOrderConfirmation('BUY');
});

closeAllBtn.addEventListener('click', () => {
    showCloseAllConfirmation();
});

// Confirmation dialog handlers
confirmBtn.addEventListener('click', async () => {
    confirmDialog.style.display = 'none';
    if (pendingOrder) {
        if (pendingOrder.type === 'BUY') {
            await executeBuyOrder(pendingOrder.data);
        } else if (pendingOrder.type === 'CLOSE_ALL') {
            await executeCloseAll();
        }
        pendingOrder = null;
    }
});

cancelBtn.addEventListener('click', () => {
    confirmDialog.style.display = 'none';
    pendingOrder = null;
});

// Close dialog on background click
confirmDialog.addEventListener('click', (e) => {
    if (e.target === confirmDialog) {
        confirmDialog.style.display = 'none';
        pendingOrder = null;
    }
});

function showOrderConfirmation(action) {
    const ticker = tickerInput.value.trim().toUpperCase();
    const quantity = parseInt(quantityInput.value);
    const expiry = expiryInput.value;
    const strike = parseFloat(strikeInput.value);
    const optionType = getOptionType();

    // Validate inputs
    if (!ticker) {
        showStatus('Please select a ticker symbol', 'error');
        return;
    }

    if (!quantity || quantity < 1) {
        showStatus('Please select a valid lot size', 'error');
        return;
    }

    if (!expiry) {
        showStatus('Please select an expiry date', 'error');
        return;
    }

    if (!strike || strike <= 0) {
        showStatus('Please enter a valid strike price', 'error');
        return;
    }

    const optionTypeName = optionType === 'C' ? 'Call' : 'Put';
    const details = `
        <p><strong>Action:</strong> ${action}</p>
        <p><strong>Symbol:</strong> ${ticker}</p>
        <p><strong>Quantity:</strong> ${quantity} contracts</p>
        <p><strong>Expiry:</strong> ${expiry}</p>
        <p><strong>Strike:</strong> $${strike.toFixed(2)}</p>
        <p><strong>Type:</strong> ${optionTypeName}</p>
    `;

    confirmDetails.innerHTML = details;
    confirmDialog.style.display = 'flex';
    
    pendingOrder = {
        type: 'BUY',
        data: {
            action: action,
            ticker: ticker,
            quantity: quantity,
            expiry: expiry.replace(/-/g, ''),
            strike: strike,
            optionType: optionType
        }
    };
}

function showCloseAllConfirmation() {
    const details = `
        <p>Are you sure you want to close <strong>all open positions</strong>?</p>
        <p style="color: #ff4579; margin-top: 10px;">This action cannot be undone.</p>
    `;

    confirmDetails.innerHTML = details;
    confirmDialog.style.display = 'flex';
    
    pendingOrder = {
        type: 'CLOSE_ALL'
    };
}

async function executeBuyOrder(orderData) {
    try {
        // Disable buttons
        buyBtn.disabled = true;
        closeAllBtn.disabled = true;
        
        showStatus(`<span class="spinner"></span>Placing order...`, 'connecting');

        const result = await window.api.placeOrder(orderData);

        if (result.success) {
            showStatus(result.message, 'success');

            // Refresh balance and Daily P&L
            await refreshBalance();
            await refreshDailyPnL();
        } else {
            showStatus(result.message, 'error');
        }
    } catch (error) {
        showStatus(`Error: ${error.message}`, 'error');
    } finally {
        buyBtn.disabled = false;
        closeAllBtn.disabled = false;
    }
}

async function executeCloseAll() {
    try {
        // Disable buttons
        buyBtn.disabled = true;
        closeAllBtn.disabled = true;
        
        showStatus(`<span class="spinner"></span>Closing all positions...`, 'connecting');

        const result = await window.api.closeAllPositions();

        if (result.success) {
            showStatus(result.message, 'success');
            
            // Refresh balance and Daily P&L
            await refreshBalance();
            await refreshDailyPnL();
        } else {
            showStatus(result.message, 'error');
        }
    } catch (error) {
        showStatus(`Error: ${error.message}`, 'error');
    } finally {
        buyBtn.disabled = false;
        closeAllBtn.disabled = false;
    }
}

// Balance and Daily P&L refresh
async function refreshBalance() {
    try {
        const result = await window.api.getBalance();
        
        if (result.success) {
            portfolioBalance.textContent = `Balance: $${formatNumber(result.balance)}`;
        } else {
            console.error('Failed to fetch balance:', result.message);
        }
    } catch (error) {
        console.error('Error fetching balance:', error);
    }
}

async function refreshDailyPnL() {
    try {
        const result = await window.api.getDailyPnL();
        
        if (result.success) {
            const pnl = result.dailyPnL;
            const formattedPnL = formatNumber(Math.abs(pnl));
            const sign = pnl >= 0 ? '+' : '-';
            
            dailyPnLElement.textContent = `Daily P&L: ${sign}$${formattedPnL}`;
            
            // Remove previous classes
            dailyPnLElement.classList.remove('positive', 'negative');
            
            // Add appropriate class
            if (pnl >= 0) {
                dailyPnLElement.classList.add('positive');
            } else {
                dailyPnLElement.classList.add('negative');
            }
        } else {
            console.error('Failed to fetch daily P&L:', result.message);
        }
    } catch (error) {
        console.error('Error fetching daily P&L:', error);
    }
}

// Auto-refresh functionality
function startAutoRefresh() {
    // Refresh every 5 seconds
    refreshInterval = setInterval(async () => {
        if (isConnected) {
            await refreshBalance();
            await refreshDailyPnL();
        }
    }, 5000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Helper functions
function showStatus(message, type) {
    statusMessage.innerHTML = message;
    statusMessage.className = `status-message show ${type}`;
}

function enableTradingSection() {
    tickerInput.disabled = false;
    quantityInput.disabled = false;
    expiryInput.disabled = false;
    strikeInput.disabled = false;
    refreshPriceBtn.disabled = false;

    // Enable radio buttons
    const radioButtons = document.getElementsByName('optionType');
    radioButtons.forEach(radio => radio.disabled = false);

    buyBtn.disabled = false;
    closeAllBtn.disabled = false;
}

function formatNumber(num) {
    return parseFloat(num).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
