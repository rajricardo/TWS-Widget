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

// Risk Management DOM elements
const stopLossInput = document.getElementById('stopLoss');
const takeProfitInput = document.getElementById('takeProfit');

// Reconnect dialog
const reconnectDialog = document.getElementById('reconnectDialog');
const reconnectConfirmBtn = document.getElementById('reconnectConfirmBtn');
const reconnectCancelBtn = document.getElementById('reconnectCancelBtn');

// Error dialog
const errorDialog = document.getElementById('errorDialog');
const errorMessage = document.getElementById('errorMessage');
const errorOkBtn = document.getElementById('errorOkBtn');

// Option Chain DOM elements
const optionChainBtn = document.getElementById('optionChainBtn');
const optionChainDialog = document.getElementById('optionChainDialog');
const closeOptionChainBtn = document.getElementById('closeOptionChainBtn');
const optionChainContent = document.getElementById('optionChainContent');

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
        watchlist: ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT'],
        stopLoss: '',
        takeProfit: '',
        windowBounds: null
    };
}

function saveSettings(settings) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

function applyTheme(theme) {
    // Remove all theme classes first
    document.body.classList.remove('light-theme', 'pastel-theme');
    
    // Apply the selected theme
    if (theme === 'light') {
        document.body.classList.add('light-theme');
    } else if (theme === 'pastel') {
        document.body.classList.add('pastel-theme');
    }
    // 'dark' is the default, so no class needed
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
    if (currentSettings.watchlist.includes(ticker)) {
        showErrorDialog(`${ticker} is already in your watchlist`);
        newTickerInput.value = '';
        return;
    }

    // Validate ticker
    if (!isConnected) {
        showErrorDialog('Please connect to TWS first to validate tickers');
        return;
    }

    try {
        // Disable button and show loading state
        addTickerBtn.disabled = true;
        addTickerBtn.textContent = 'Validating...';
        
        const validationResult = await window.api.validateTicker(ticker);
        
        if (validationResult.success) {
            currentSettings.watchlist.push(ticker);
            saveSettings(currentSettings);
            renderWatchlist(currentSettings.watchlist);
            populateTickerDropdown(currentSettings.watchlist);
            showStatus(`${ticker} added to watchlist`, 'success');
            newTickerInput.value = '';
        } else {
            showErrorDialog(validationResult.message);
        }
    } catch (error) {
        showErrorDialog(`Error validating ticker: ${error.message}`);
    } finally {
        addTickerBtn.disabled = false;
        addTickerBtn.textContent = 'Add';
    }
}

async function initializeSettings() {
    const settings = await loadSettings();
    applyTheme(settings.theme);
    applyFontSize(settings.fontSize);
    populateTickerDropdown(settings.watchlist);
    
    // Restore window bounds if saved
    if (settings.windowBounds) {
        await window.api.setWindowBounds(settings.windowBounds);
    }
    
    // Listen for window bounds changes and save them
    window.api.onWindowBoundsChanged((bounds) => {
        saveWindowBounds(bounds);
    });
    
    return settings;
}

async function saveWindowBounds(bounds) {
    const currentSettings = await loadSettings();
    currentSettings.windowBounds = bounds;
    saveSettings(currentSettings);
}

// Set default expiry date to today
const today = new Date().toISOString().split('T')[0];
expiryInput.value = today;

// Event listeners for ticker change and refresh button
tickerInput.addEventListener('change', async () => {
    if (isConnected && tickerInput.value) {
        await fetchAndPopulatePrice();
        // Enable option chain button when ticker is selected
        optionChainBtn.disabled = false;
    } else {
        // Disable option chain button when no ticker selected
        optionChainBtn.disabled = true;
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
    stopLossInput.value = currentSettings.stopLoss || '';
    takeProfitInput.value = currentSettings.takeProfit || '';

    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === currentSettings.theme);
    });

    document.querySelectorAll('.font-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.size === currentSettings.fontSize);
    });

    renderWatchlist(currentSettings.watchlist);

    connectionSettingsChanged = false;
    settingsDialog.style.display = 'flex';
    
    // Reset scroll position to top
    const modalContent = settingsDialog.querySelector('.modal-content');
    if (modalContent) {
        modalContent.scrollTop = 0;
    }
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

stopLossInput.addEventListener('change', async () => {
    const currentSettings = await loadSettings();
    const value = stopLossInput.value.trim();
    currentSettings.stopLoss = value;
    saveSettings(currentSettings);
});

takeProfitInput.addEventListener('change', async () => {
    const currentSettings = await loadSettings();
    const value = takeProfitInput.value.trim();
    currentSettings.takeProfit = value;
    saveSettings(currentSettings);
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

// Error dialog event listeners
errorOkBtn.addEventListener('click', () => {
    errorDialog.style.display = 'none';
});

errorDialog.addEventListener('click', (e) => {
    if (e.target === errorDialog) {
        errorDialog.style.display = 'none';
    }
});

function showErrorDialog(message) {
    errorMessage.innerHTML = `<p>${message}</p>`;
    errorDialog.style.display = 'flex';
}

// Option Chain event listeners
optionChainBtn.addEventListener('click', async () => {
    await showOptionChain();
});

closeOptionChainBtn.addEventListener('click', () => {
    optionChainDialog.style.display = 'none';
});

optionChainDialog.addEventListener('click', (e) => {
    if (e.target === optionChainDialog) {
        optionChainDialog.style.display = 'none';
    }
});

async function showOptionChain() {
    const ticker = tickerInput.value.trim().toUpperCase();
    
    if (!ticker) {
        showStatus('Please select a ticker symbol first', 'error');
        return;
    }
    
    // Show dialog with loading state
    optionChainContent.innerHTML = `
        <div class="loading-spinner">
            <span class="spinner"></span>
            Loading option chain...
        </div>
    `;
    optionChainDialog.style.display = 'flex';
    
    try {
        const result = await window.api.getOptionChain(ticker);
        
        if (result.success && result.optionChain && result.optionChain.length > 0) {
            renderOptionChain(result.optionChain, result.currentPrice);
        } else {
            optionChainContent.innerHTML = `
                <div style="padding: 40px; text-align: center; color: #ff4579;">
                    <p>${result.message || 'No option chain data available'}</p>
                </div>
            `;
            // Also show error in status bar
            showStatus(result.message || 'Failed to load option chain', 'error');
        }
    } catch (error) {
        optionChainContent.innerHTML = `
            <div style="padding: 40px; text-align: center; color: #ff4579;">
                <p>Error: ${error.message}</p>
            </div>
        `;
        showStatus(`Error loading option chain: ${error.message}`, 'error');
    }
}

function renderOptionChain(optionChain, currentPrice) {
    if (!optionChain || optionChain.length === 0) {
        optionChainContent.innerHTML = '<p style="text-align: center; padding: 20px;">No option data available</p>';
        return;
    }
    
    // Build table HTML
    let tableHTML = `
        <table class="option-chain-table">
            <thead>
                <tr>
                    <th colspan="4" class="calls-header">CALLS</th>
                    <th class="strike-header">STRIKE</th>
                    <th colspan="4" class="puts-header">PUTS</th>
                </tr>
                <tr>
                    <th>Mid</th>
                    <th>IV</th>
                    <th>Delta</th>
                    <th>Theta</th>
                    <th>Price</th>
                    <th>IV</th>
                    <th>Delta</th>
                    <th>Theta</th>
                    <th>Mid</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    optionChain.forEach(option => {
        // Use the mid prices already calculated by the backend
        const callMid = option.callMid.toFixed(2);
        const putMid = option.putMid.toFixed(2);
        
        tableHTML += `
            <tr>
                <td class="call-side" data-type="C" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">$${callMid}</td>
                <td class="call-side greek-value" data-type="C" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">${option.callIV}</td>
                <td class="call-side greek-value" data-type="C" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">${Math.abs(option.callDelta)}</td>
                <td class="call-side greek-value" data-type="C" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">${Math.abs(option.callTheta)}</td>
                <td class="strike-cell">$${option.strike}</td>
                <td class="put-side greek-value" data-type="P" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">${option.putIV}</td>
                <td class="put-side greek-value" data-type="P" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">${Math.abs(option.putDelta)}</td>
                <td class="put-side greek-value" data-type="P" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">${Math.abs(option.putTheta)}</td>
                <td class="put-side" data-type="P" data-strike="${option.strike}" data-expiry="${option.expiryRaw}">$${putMid}</td>
            </tr>
        `;
    });
    
    tableHTML += `
            </tbody>
        </table>
    `;
    
    optionChainContent.innerHTML = tableHTML;
    
    // Add double-click event listeners to option cells
    const callCells = optionChainContent.querySelectorAll('.call-side');
    const putCells = optionChainContent.querySelectorAll('.put-side');
    
    callCells.forEach(cell => {
        cell.addEventListener('dblclick', () => {
            selectOption(cell.dataset.type, cell.dataset.strike, cell.dataset.expiry);
        });
    });
    
    putCells.forEach(cell => {
        cell.addEventListener('dblclick', () => {
            selectOption(cell.dataset.type, cell.dataset.strike, cell.dataset.expiry);
        });
    });
}

function selectOption(optionType, strike, expiry) {
    // Close the dialog
    optionChainDialog.style.display = 'none';
    
    // Format expiry from YYYYMMDD to YYYY-MM-DD
    const formattedExpiry = `${expiry.substring(0, 4)}-${expiry.substring(4, 6)}-${expiry.substring(6, 8)}`;
    
    // Populate the form fields
    expiryInput.value = formattedExpiry;
    strikeInput.value = parseFloat(strike).toFixed(2);
    
    // Set the option type radio button
    const radioButtons = document.getElementsByName('optionType');
    radioButtons.forEach(radio => {
        if (radio.value === optionType) {
            radio.checked = true;
        }
    });
    
    // Show confirmation message
    const optionTypeName = optionType === 'C' ? 'Call' : 'Put';
    showStatus(`Selected ${optionTypeName} option: Strike $${strike}, Expiry ${formattedExpiry}`, 'success');
}


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

async function showOrderConfirmation(action) {
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

    // Get current settings for SL/TP
    const currentSettings = await loadSettings();
    const stopLoss = currentSettings.stopLoss || '';
    const takeProfit = currentSettings.takeProfit || '';

    const optionTypeName = optionType === 'C' ? 'Call' : 'Put';
    let details = `
        <p><strong>Action:</strong> ${action}</p>
        <p><strong>Symbol:</strong> ${ticker}</p>
        <p><strong>Quantity:</strong> ${quantity} contracts</p>
        <p><strong>Expiry:</strong> ${expiry}</p>
        <p><strong>Strike:</strong> $${strike.toFixed(2)}</p>
        <p><strong>Type:</strong> ${optionTypeName}</p>
    `;

    // Add SL/TP info if set
    if (stopLoss || takeProfit) {
        details += '<p style="margin-top: 10px; font-weight: bold; color: #4a9eff;">Risk Management:</p>';
        if (stopLoss) {
            details += `<p><strong>Stop Loss:</strong> ${stopLoss}%</p>`;
        }
        if (takeProfit) {
            details += `<p><strong>Take Profit:</strong> ${takeProfit}%</p>`;
        }
    }

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
            optionType: optionType,
            stopLoss: stopLoss,
            takeProfit: takeProfit
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

// Global keyboard event listener for Esc key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        // Close settings dialog if open
        if (settingsDialog.style.display === 'flex') {
            settingsDialog.style.display = 'none';
            if (connectionSettingsChanged) {
                reconnectDialog.style.display = 'flex';
            }
        }
        // Close option chain dialog if open
        else if (optionChainDialog.style.display === 'flex') {
            optionChainDialog.style.display = 'none';
        }
        // Close error dialog if open
        else if (errorDialog.style.display === 'flex') {
            errorDialog.style.display = 'none';
        }
        // Close confirmation dialog if open
        else if (confirmDialog.style.display === 'flex') {
            confirmDialog.style.display = 'none';
            pendingOrder = null;
        }
        // Close reconnect dialog if open
        else if (reconnectDialog.style.display === 'flex') {
            reconnectDialog.style.display = 'none';
            connectionSettingsChanged = false;
        }
    }
});
