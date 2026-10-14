# ⚡ Raw SSE Hub v2.0 (Server-Sent Events)

An enterprise-grade, zero-dependency demonstration of **Server-Sent Events (SSE)** using vanilla Node.js and client-side JavaScript. 

Features a real-time multi-asset financial ticker, live SVG/Canvas chart station, server telemetry HUD, interactive protocol inspector, and automatic reconnection recovery using the **`Last-Event-ID`** ring-buffer replay mechanism.

---

## 🌟 What's New in v2.0

- 🔀 **Multi-Channel SSE Event Streams (`event: <type>`)**:
  - `event: ticker` — Real-time price quotes for multiple assets (BTC, ETH, SOL, NVDA) with delta, 24h change %, and volume.
  - `event: telemetry` — Server health metrics (active client count, uptime, heap memory, events pushed).
  - `event: alert` — Market volatility triggers, resistance milestones, and whale transaction warnings.
  - `event: broadcast` — Real-time client-to-client broadcasts pushed across all active SSE subscribers.
  - `event: connected` — Handshake packet providing client ID and server snapshot upon initial connection.
- 🔁 **`Last-Event-ID` Reconnection Recovery**:
  - In-memory event ring-buffer stores recent packets.
  - If a client's connection drops, the browser sends its `Last-Event-ID` header upon reconnect, and the server automatically replays all missed events without data loss.
  - Includes an interactive **"Simulate Reconnect & Replay"** button in the UI.
- 🎛️ **Dual SSE Transport Modes**:
  - **Native `EventSource` Mode**: Standard W3C `EventSource` with typed event listeners (`addEventListener('ticker', ...)`).
  - **Raw `fetch()` Stream Reader Mode**: Low-level stream reader using `ReadableStreamDefaultReader` + `TextDecoder` to demonstrate manual chunk buffer parsing and line separation.
- 📡 **Live Wire Protocol Inspector**:
  - Real-time syntax-colored terminal displaying actual HTTP chunk frames arriving over the wire (`id:`, `event:`, `retry:`, `data:`, `: heartbeat`).
- 📈 **Dynamic Retina Canvas Chart**:
  - Smooth Bezier curves, neon gradient area fill, live price beacon, customizable window (30/60/100 ticks).
- 💓 **Proxy Keep-Alive Heartbeats**:
  - Periodic comment frames (`: keep-alive <timestamp>\n\n`) to prevent connection timeouts from proxies and firewalls.
- 🚀 **Zero External Dependencies**:
  - Built purely with standard Node.js built-ins (`http`, `fs`, `url`, `path`). No `express`, `socket.io`, or `npm install` needed.

---

## 🏗️ Architecture & How It Works

```
                        ┌────────────────────────────────────────────────────────┐
                        │                   Node.js Server                       │
                        │                 (Zero Dependencies)                    │
                        │                                                        │
                        │   ┌────────────────────────────────────────────────┐   │
                        │   │         Sliding Ring Buffer (200 pkts)         │   │
                        │   │  [id:1] [id:2] ... [id:41] [id:42] ... [id:N]  │   │
                        │   └────────────────────────────────────────────────┘   │
                        │                           │                            │
                        └───────────────────────────┼────────────────────────────┘
                                                    │
                                     HTTP GET /events
                         Content-Type: text/event-stream; charset=utf-8
                         Cache-Control: no-cache, no-transform
                         Connection: keep-alive
                                                    │
                   ┌────────────────────────────────┼────────────────────────────────┐
                   ▼                                                                 ▼
      ┌─────────────────────────┐                                       ┌─────────────────────────┐
      │   Client A (Browser)    │                                       │   Client B (Browser)    │
      │   Native EventSource    │                                       │   Raw fetch() Stream    │
      │                         │                                       │                         │
      │ • Auto-reconnect        │                                       │ • ReadableStream reader │
      │ • Last-Event-ID header  │                                       │ • Manual \n\n parser    │
      │ • Typed listeners       │                                       │ • Wire protocol viewer  │
      └─────────────────────────┘                                       └─────────────────────────┘
```

---

## ⚡ The SSE Wire Protocol Format

SSE streams are simple plaintext messages delimited by double newlines (`\n\n`). Each packet can contain any combination of:

| Field | Purpose | Example |
| :--- | :--- | :--- |
| `data: <payload>` | The payload data. Multi-line data lines are joined with newlines. | `data: {"symbol":"BTC","price":67420}` |
| `id: <uniqueId>` | Monotonic event identifier. Stored by the client as `Last-Event-ID`. | `id: 104` |
| `event: <name>` | Custom event type for client-side event dispatching. | `event: ticker` |
| `retry: <ms>` | Reconnection delay in milliseconds if the stream is interrupted. | `retry: 2500` |
| `: <comment>` | Lines starting with a colon are comments, used for keep-alive pings. | `: keep-alive 2026-10-15T00:00:00Z` |

---

## 🆚 SSE vs WebSockets vs HTTP Polling

| Feature | Server-Sent Events (SSE) | WebSockets | HTTP Polling |
| :--- | :--- | :--- | :--- |
| **Direction** | Unidirectional (Server → Client) | Full-Duplex (Bidirectional) | Client pulls updates |
| **Protocol** | Standard HTTP / HTTP/2 | `ws://` / `wss://` (TCP upgrade) | Standard HTTP |
| **Automatic Reconnect** | Built-in native browser support | Must be manually implemented | Handled per request |
| **Resumption on Drop** | Built-in via `Last-Event-ID` | Custom application protocol | None (must pass timestamp) |
| **Firewall & Proxy** | Works seamlessly through proxies | May require custom proxy config | Works everywhere |
| **Transport Overhead** | Very low (simple text frames) | Low framing overhead | Very high (repeated HTTP headers)|
| **Complexity** | Minimal (Standard HTTP endpoint) | Moderate to High | Low initially, bad at scale |

---

## 🚀 Quick Start Guide

### Prerequisites
- [Node.js](https://nodejs.org/) (v16 or newer).

### Running the Application

1. **Clone & Navigate:**
   ```bash
   git clone https://github.com/HxWildE/SSE.git
   cd SSE
   ```

2. **Start the server:**
   ```bash
   node index.js
   # or with npm
   npm start
   ```

3. **Open in Browser:**
   Visit [`http://localhost:3000`](http://localhost:3000)

---

## 🧪 Interactive Features to Try

1. **Simulate Network Drop & Replay:**
   - Click the **"Simulate Reconnect & Replay"** button in the header.
   - The client disconnects for 3 seconds while the server keeps ticking.
   - Upon reconnecting, the client presents its `Last-Event-ID` and the server replays all missed events from the buffer.
2. **Switch Transport Modes:**
   - Click between **"EventSource API"** and **"Fetch Stream Reader"** to inspect how both browser APIs interact with the raw SSE stream.
3. **Trigger Market Shocks:**
   - Click **"Spike +5.5%"** or **"Drop -5.5%"** to dispatch an instant reactive surge and priority alert across all connected subscribers.
4. **Push Live Broadcasts:**
   - Type a message in the console and hit **"Send"** (`POST /api/broadcast`) to see it instantly pop up on all connected screens via `event: broadcast`.
5. **Inspect Raw Wire Protocol:**
   - Watch the raw wire stream box to see exact chunk frames arriving over HTTP in real time.

---

## 📜 License

MIT License. Free to use, modify, and distribute for personal or commercial projects.
