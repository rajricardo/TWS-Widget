
const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld(
  'api', {
    // Connection methods
    connectTWS: () => ipcRenderer.invoke('connect-tws'),
    disconnectTWS: () => ipcRenderer.invoke('disconnect-tws'),
    updateConnectionSettings: (settings) => ipcRenderer.invoke('update-connection-settings', settings),
    getConnectionSettings: () => ipcRenderer.invoke('get-connection-settings'),

    // Trading methods
    placeOrder: (orderParams) => ipcRenderer.invoke('place-order', orderParams),
    getPositions: () => ipcRenderer.invoke('get-positions'),
    getBalance: () => ipcRenderer.invoke('get-balance'),
    getDailyPnL: () => ipcRenderer.invoke('get-daily-pnl'),
    closePosition: (positionParams) => ipcRenderer.invoke('close-position', positionParams),
    closeAllPositions: () => ipcRenderer.invoke('close-all-positions'),
    getTickerPrice: (ticker) => ipcRenderer.invoke('get-ticker-price', ticker),
    validateTicker: (ticker) => ipcRenderer.invoke('validate-ticker', ticker)
  }
);
