# TWS Electron App

A cross-platform Electron-based application for connecting to Interactive Brokers TWS (Trader Workstation) or IB Gateway via Python API.

![TWS Connection Interface](screenshot.png)

## Features

- 🖥️ Native macOS look and feel
- 🔌 Easy connection to TWS/IB Gateway
- 🐍 Python bridge for TWS API integration
- ✨ Clean and intuitive user interface
- ⚡ Real-time connection status feedback

## Prerequisites

### 1. Node.js and npm
- **Version:** Node.js 16.x or higher
- **Download:** https://nodejs.org/

### 2. Python 3
- **Version:** Python 3.7 or higher

### 3. TWS Python API Library

Install either `ib_insync` (recommended) or `ibapi`:

```bash
pip3 install ib_insync
```

### 4. Interactive Brokers TWS or IB Gateway
- **Download TWS:** https://www.interactivebrokers.com/en/trading/tws.php
- **Download IB Gateway:** https://www.interactivebrokers.com/en/trading/ibgateway-latest.php

**Important:** Enable API connections in TWS/Gateway:
1. Open TWS or IB Gateway
2. Go to **File → Global Configuration → API → Settings**
3. Check **Enable ActiveX and Socket Clients**
4. Add `127.0.0.1` to **Trusted IP Addresses**
5. Note the **Socket Port** (default: 7496 for TWS paper trading)

## Installation

1. Clone or download this repository
2. Navigate to the project directory:
   ```bash
   cd tws_electron_app
   ```
3. Install dependencies:
   ```bash
   npm install
   ```

## Running the Application

```bash
npm start
```

## Usage

### 1. Start TWS or IB Gateway
- Launch TWS or IB Gateway
- Log in to your account
- Ensure API connections are enabled

### 2. Configure Connection Settings

The application opens with default values:
- **Host:** `127.0.0.1` (localhost)
- **Port:** `7496` (TWS paper trading default)
- **Client ID:** `1`

**Common Ports:**
- `7496` - TWS Paper Trading
- `7497` - TWS Live Trading
- `4001` - IB Gateway Paper Trading
- `4002` - IB Gateway Live Trading

### 3. Connect

Click the **Connect** button. If successful, the button changes to **Disconnect**.

## Troubleshooting

### Connection Issues

If connection fails, verify:
1. ✅ TWS/IB Gateway is running
2. ✅ API connections are enabled in settings
3. ✅ Correct port number is used
4. ✅ No other application is using the same Client ID
5. ✅ Python TWS API is installed (`pip3 install ib_insync`)

### Common Errors

**"Connection timeout"**
- Verify TWS/IB Gateway is running
- Check if API connections are enabled
- Confirm the correct port number

**"Client ID already in use"**
- Use a different Client ID in the app
- Close other applications using the same Client ID
- Restart TWS/IB Gateway

## License

MIT License

---

**Happy Trading! 📈**
