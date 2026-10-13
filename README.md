# Raw SSE (Server-Sent Events) Demo

This project is a simple demonstration of Server-Sent Events (SSE) using vanilla JavaScript and Node.js. It features a live price tracker that updates a graph in real-time without the need for WebSockets or continuous polling.

## What are Server-Sent Events (SSE)?

Server-Sent Events (SSE) is a server push technology enabling a client to receive automatic updates from a server via a persistent HTTP connection. It's ideal for one-way communication where the server needs to frequently send data to the client, such as live stock prices, news feeds, or social media updates.

**Key characteristics of SSE:**
- **Unidirectional:** Data flows from server to client only.
- **Text-based:** Uses the `text/event-stream` content type.
- **Built on HTTP:** Works over standard HTTP/HTTPS connections.
- **Lightweight:** Easier to implement than WebSockets for one-way data flow.

## Project Structure

- `index.js`: A lightweight Node.js HTTP server that serves the frontend and handles the SSE endpoint (`/events`).
- `index.html`: The frontend client that connects to the SSE stream, parses the incoming data, and renders a live line chart and log.

## Prerequisites

- [Node.js](https://nodejs.org/) installed on your machine.

## Setup and Run Guide

1. **Open your terminal** and navigate to the project directory:
   ```bash
   cd path/to/SSE
   ```

2. **Run the server** using Node.js. (Note: There are no external dependencies like `express` to install, as it uses the built-in `http` module).
   ```bash
   node index.js
   ```

3. **Open your browser** and visit:
   ```text
   http://localhost:3000
   ```

## How it Works in this Project

### Server-side (`index.js`)
When a client requests `/events`, the server responds with specific headers to establish the SSE connection and keep it open:
```javascript
res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive"
});
```
It then uses `setInterval` to push a new JSON string formatted with the `data: ` prefix and ending with `\n\n` (the SSE standard format) every second.

### Client-side (`index.html`)
The frontend uses the `fetch` API and a `TextDecoder` to read the raw chunked data stream instead of the standard `EventSource` API, giving a closer look at how the protocol works under the hood:
```javascript
const response = await fetch("/events");
const reader = response.body.getReader();
// ... loop to read chunks, parse the buffer by \n\n, and extract JSON
```
This parsed data is then used to update the DOM elements and draw the dynamic `<canvas>` line chart.

## SSE vs WebSockets vs Polling

| Feature | Server-Sent Events (SSE) | WebSockets | Polling / Long Polling |
| :--- | :--- | :--- | :--- |
| **Communication** | Unidirectional (Server → Client) | Full-duplex / Bidirectional | Unidirectional (Client pulls) |
| **Protocol** | Standard HTTP / HTTP/2 | `ws://` / `wss://` (TCP handshake) | Standard HTTP |
| **Data Format** | UTF-8 Text / JSON | Binary & Text | Any HTTP payload |
| **Reconnection** | Built-in automatic reconnection | Must be manually implemented | Handled by interval / request |
| **Complexity** | Very low (simple HTTP endpoint) | Moderate / High (socket state) | Low (inefficient over time) |
| **Firewall & Proxy**| Works out of the box with proxies | May require special proxy configs | Standard HTTP |

## SSE Protocol Specification

SSE streams communicate through simple plaintext blocks separated by a pair of newlines (`\n\n`). Each event can contain the following fields:

- `data: <content>` — Payload for the event. Multiple consecutive `data:` lines are concatenated with newlines.
- `id: <id>` — Unique identifier for the event. The browser stores this as `Last-Event-ID` and sends it back in headers on reconnect.
- `event: <name>` — Custom event type (allows client-side dispatching like `addEventListener('my-event', ...)`).
- `retry: <milliseconds>` — Suggested reconnect timeout for the client if the connection drops.
- `: <comment>` — Lines starting with a colon are ignored by parsers and can be used for keep-alive heartbeats.


