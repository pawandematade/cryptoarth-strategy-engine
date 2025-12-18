/**
 * TradingView Datafeed Adapter
 * Connects TradingView Charting Library to backend API
 */

// Backend API base URL - should be configured via environment or config
const BACKEND_BASE_URL = 'https://trade-api.cryptoarth.in/auth';

// Resolution mapping: TradingView resolution -> Backend resolution
const RESOLUTION_MAP = {
  '1': '1',
  '5': '5',
  '15': '15',
  '30': '15', // Map 30 to 15 (closest available)
  '60': '60',
  '240': '240',
  '1D': '1D',
  '1W': '1D', // Map 1W to 1D (closest available)
  '1M': '1D'  // Map 1M to 1D (closest available)
};

// Polling interval for real-time updates (milliseconds)
const POLLING_INTERVAL = 1000; // 1 second

/**
 * Convert TradingView resolution to backend resolution
 */
function mapResolution(tvResolution) {
  return RESOLUTION_MAP[tvResolution] || tvResolution;
}

/**
 * Get resolution in seconds for calculating time windows
 */
function getResolutionSeconds(resolution) {
  if (resolution === '1D') return 86400;
  if (resolution === '1W') return 604800;
  if (resolution === '1M') return 2592000;
  return parseInt(resolution) * 60; // Minutes to seconds
}

/**
 * Convert backend candle to TradingView bar format
 */
function candleToBar(candle) {
  return {
    time: candle.time * 1000, // Convert seconds to milliseconds
    open: parseFloat(candle.open),
    high: parseFloat(candle.high),
    low: parseFloat(candle.low),
    close: parseFloat(candle.close),
    volume: parseFloat(candle.volume || 0)
  };
}

/**
 * Fetch historical candles from backend API
 */
async function fetchCandles(symbol, resolution, start, end) {
  const url = `${BACKEND_BASE_URL}/history/candles`;
  const params = new URLSearchParams({
    symbol: symbol,
    resolution: resolution,
    start: start.toString(),
    end: end.toString()
  });

  try {
    const response = await fetch(`${url}?${params.toString()}`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    
    if (!data.candles || !Array.isArray(data.candles)) {
      return [];
    }

    return data.candles.map(candleToBar);
  } catch (error) {
    console.error('Error fetching candles:', error);
    throw error;
  }
}

/**
 * Fetch latest price/candle from backend
 * Optimized to fetch minimal data for real-time updates
 */
async function fetchLatestCandle(symbol, resolution) {
  const now = Math.floor(Date.now() / 1000);
  // Fetch last 2 periods worth of data to ensure we get the latest bar
  const resolutionSeconds = getResolutionSeconds(resolution);
  const start = now - (resolutionSeconds * 2);
  
  try {
    const bars = await fetchCandles(symbol, resolution, start, now);
    return bars.length > 0 ? bars[bars.length - 1] : null;
  } catch (error) {
    console.error('Error fetching latest candle:', error);
    return null;
  }
}

/**
 * TradingView Datafeed Implementation
 */
class Datafeed {
  constructor() {
    this.subscribers = new Map(); // Map<subscriberUID, {symbolInfo, resolution, callback, intervalId}>
  }

  /**
   * Called by TradingView to initialize the datafeed
   */
  onReady(callback) {
    setTimeout(() => {
      callback({
        supported_resolutions: ['1', '5', '15', '30', '60', '240', '1D', '1W', '1M'],
        supports_group_request: false,
        supports_marks: false,
        supports_search: false,
        supports_timescale_marks: false,
        supports_time: true
      });
    }, 0);
  }

  /**
   * Resolve symbol information
   */
  resolveSymbol(symbolName, onResolve, onError) {
    // Extract symbol from symbolName (format: "EXCHANGE:SYMBOL" or just "SYMBOL")
    const symbol = symbolName.includes(':') 
      ? symbolName.split(':')[1] 
      : symbolName;

    const symbolInfo = {
      name: symbolName,
      ticker: symbolName,
      description: symbol,
      type: 'crypto',
      session: '24x7',
      timezone: 'Etc/UTC',
      exchange: '',
      minmov: 1,
      pricescale: 100, // 2 decimal places
      has_intraday: true,
      has_weekly_and_monthly: true,
      supported_resolutions: ['1', '5', '15', '30', '60', '240', '1D', '1W', '1M'],
      volume_precision: 2,
      data_status: 'streaming',
      has_no_volume: false,
      has_daily: true,
      currency_code: 'USD',
      original_currency_code: 'USD'
    };

    setTimeout(() => {
      onResolve(symbolInfo);
    }, 0);
  }

  /**
   * Get historical bars
   */
  getBars(symbolInfo, resolution, periodParams, onResult, onError) {
    const { from, to, firstDataRequest } = periodParams;
    
    // Map TradingView resolution to backend resolution
    const backendResolution = mapResolution(resolution);
    
    // Extract symbol
    const symbol = symbolInfo.name.includes(':') 
      ? symbolInfo.name.split(':')[1] 
      : symbolInfo.name;

    // Validate inputs
    if (!symbol || !backendResolution) {
      onError(new Error('Invalid symbol or resolution'));
      return;
    }

    // Convert milliseconds to seconds for backend
    const start = Math.floor(from / 1000);
    const end = Math.floor(to / 1000);

    // Validate time range
    if (start >= end || start <= 0) {
      onError(new Error('Invalid time range'));
      return;
    }

    fetchCandles(symbol, backendResolution, start, end)
      .then((bars) => {
        if (bars.length === 0) {
          onResult([], { noData: true });
        } else {
          // Sort bars by time to ensure correct order
          bars.sort((a, b) => a.time - b.time);
          onResult(bars, { noData: false });
        }
      })
      .catch((error) => {
        console.error('getBars error:', error);
        onError(error);
      });
  }

  /**
   * Subscribe to real-time bar updates
   */
  subscribeBars(symbolInfo, resolution, onRealtimeCallback, subscriberUID) {
    // Check if already subscribed
    if (this.subscribers.has(subscriberUID)) {
      console.warn(`Already subscribed with UID: ${subscriberUID}`);
      return;
    }

    // Map TradingView resolution to backend resolution
    const backendResolution = mapResolution(resolution);
    
    // Extract symbol
    const symbol = symbolInfo.name.includes(':') 
      ? symbolInfo.name.split(':')[1] 
      : symbolInfo.name;

    // Validate inputs
    if (!symbol || !backendResolution) {
      console.error('Invalid symbol or resolution for subscription');
      return;
    }

    // Store subscriber info
    const subscriber = {
      symbolInfo,
      resolution: backendResolution,
      symbol,
      callback: onRealtimeCallback,
      lastBar: null,
      isActive: true
    };

    // Poll backend every 1 second
    const pollLatestPrice = async () => {
      // Check if subscription is still active
      if (!subscriber.isActive) {
        return;
      }

      try {
        const latestBar = await fetchLatestCandle(symbol, backendResolution);
        
        if (latestBar) {
          // Only update if we have a new bar or price changed
          if (!subscriber.lastBar || 
              subscriber.lastBar.time !== latestBar.time || 
              subscriber.lastBar.close !== latestBar.close) {
            subscriber.lastBar = latestBar;
            onRealtimeCallback(latestBar);
          }
        }
      } catch (error) {
        console.error('subscribeBars polling error:', error);
        // Continue polling even on error
      }
    };

    // Start polling immediately, then every interval
    pollLatestPrice();
    const intervalId = setInterval(pollLatestPrice, POLLING_INTERVAL);

    subscriber.intervalId = intervalId;
    this.subscribers.set(subscriberUID, subscriber);
  }

  /**
   * Unsubscribe from real-time bar updates
   */
  unsubscribeBars(subscriberUID) {
    const subscriber = this.subscribers.get(subscriberUID);
    
    if (subscriber) {
      if (subscriber.intervalId) {
        clearInterval(subscriber.intervalId);
      }
      subscriber.isActive = false;
      this.subscribers.delete(subscriberUID);
    }
  }
}

// Create default instance for TradingView
const datafeedInstance = new Datafeed();

// ES6 module exports (default export is instance, named export is class)
export default datafeedInstance;
export { Datafeed };

// CommonJS export (for Node.js environments)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = datafeedInstance;
  module.exports.Datafeed = Datafeed;
}

// Global window export (for browser script tags)
if (typeof window !== 'undefined') {
  window.Datafeed = Datafeed;
  window.datafeedInstance = datafeedInstance;
}
