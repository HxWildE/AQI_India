const http = require("http");
const fs = require("fs");
const path = require("path");
const url = require("url");

const PORT = process.env.PORT || 3000;

// -------------------------------------------------------------
// SSE SERVER STATE & EVENT RING BUFFER
// -------------------------------------------------------------
let nextEventId = 1;
const BUFFER_CAPACITY = 200;
const eventBuffer = []; // Sliding window of recent events for Last-Event-ID replay
const clients = new Map(); // clientId -> { id, res, connectedAt, remoteAddress }

// Multi-asset simulation state
const marketData = {
    BTC: { symbol: "BTC", name: "Bitcoin", price: 67420.0, base: 67420.0, high: 68100.0, low: 66900.0, change24h: 2.15, volume: 38240 },
    ETH: { symbol: "ETH", name: "Ethereum", price: 3480.5, base: 3480.5, high: 3520.0, low: 3410.0, change24h: -0.84, volume: 194120 },
    SOL: { symbol: "SOL", name: "Solana", price: 178.25, base: 178.25, high: 182.0, low: 173.5, change24h: 5.42, volume: 840500 },
    NVDA: { symbol: "NVDA", name: "Nvidia", price: 134.8, base: 134.8, high: 137.2, low: 132.1, change24h: 3.12, volume: 1540200 }
};

// -------------------------------------------------------------
// SSE FORMATTER UTILITY
// Formats compliant SSE wire chunks:
// : comment
// id: <id>
// event: <event-name>
// retry: <milliseconds>
// data: <payload>
// \n
// -------------------------------------------------------------
function formatSSE({ id, event, data, retry, comment }) {
    let payload = "";
    if (comment) {
        payload += `: ${comment}\n`;
    }
    if (retry !== undefined) {
        payload += `retry: ${retry}\n`;
    }
    if (id !== undefined) {
        payload += `id: ${id}\n`;
    }
    if (event) {
        payload += `event: ${event}\n`;
    }
    if (data !== undefined) {
        const str = typeof data === "string" ? data : JSON.stringify(data);
        const lines = str.split("\n");
        for (const line of lines) {
            payload += `data: ${line}\n`;
        }
    }
    payload += "\n";
    return payload;
}

// Broadcasts an event to all connected clients and stores it in the ring buffer
function broadcast(eventType, dataObj, options = {}) {
    const id = nextEventId++;
    const timestamp = new Date().toISOString();
    const packet = {
        id,
        event: eventType,
        data: { ...dataObj, _eventId: id, _serverTime: timestamp },
        retry: options.retry || 2500
    };

    // Store in ring buffer for Last-Event-ID reconnection recovery
    eventBuffer.push(packet);
    if (eventBuffer.length > BUFFER_CAPACITY) {
        eventBuffer.shift();
    }

    const rawChunk = formatSSE(packet);

    for (const [clientId, client] of clients.entries()) {
        try {
            client.res.write(rawChunk);
        } catch (err) {
            console.error(`[SSE] Write error to client ${clientId}:`, err.message);
        }
    }

    return { id, chunk: rawChunk };
}

// -------------------------------------------------------------
// BACKGROUND EVENT SIMULATORS
// -------------------------------------------------------------

// 1. Ticker Price Generator (Random walk with mean-reversion)
setInterval(() => {
    const symbols = Object.keys(marketData);
    const chosen = symbols[Math.floor(Math.random() * symbols.length)];
    const asset = marketData[chosen];

    // Percentage delta between -0.4% and +0.4% with subtle gravity to base
    const pctChange = (Math.random() - 0.495) * 0.008;
    const oldPrice = asset.price;
    asset.price = Math.max(1, Number((asset.price * (1 + pctChange)).toFixed(2)));
    asset.high = Math.max(asset.high, asset.price);
    asset.low = Math.min(asset.low, asset.price);
    asset.change24h = Number((((asset.price - asset.base) / asset.base) * 100).toFixed(2));
    asset.volume += Math.floor(Math.random() * 15) + 1;

    broadcast("ticker", {
        symbol: asset.symbol,
        name: asset.name,
        price: asset.price,
        previousPrice: oldPrice,
        delta: Number((asset.price - oldPrice).toFixed(2)),
        change24h: asset.change24h,
        high: asset.high,
        low: asset.low,
        volume: asset.volume
    });
}, 1000);

// 2. Server Telemetry (CPU/RAM & Connection Stats)
setInterval(() => {
    const mem = process.memoryUsage();
    broadcast("telemetry", {
        activeClients: clients.size,
        totalEventsSent: nextEventId - 1,
        bufferSize: eventBuffer.length,
        uptimeSeconds: Math.floor(process.uptime()),
        rssMB: (mem.rss / 1024 / 1024).toFixed(1),
        heapUsedMB: (mem.heapUsed / 1024 / 1024).toFixed(1),
        nodeVersion: process.version
    });
}, 2000);

// 3. Periodic Market Alerts
const MOCK_ALERTS = [
    { title: "Whale Transaction Detected", desc: "1,250 BTC transferred from Binance to cold storage wallet.", severity: "info" },
    { title: "Network Volume Surge", desc: "Solana DEX volume spiked by 18% in the last 15 minutes.", severity: "success" },
    { title: "Liquidity Wall Alert", desc: "Ethereum buy orders accumulating heavily around $3,400 support.", severity: "warning" },
    { title: "Macro Indicator Update", desc: "Tech earnings reports beat Wall Street consensus estimates.", severity: "info" }
];

let alertIndex = 0;
setInterval(() => {
    if (clients.size === 0) return;
    const alert = MOCK_ALERTS[alertIndex % MOCK_ALERTS.length];
    alertIndex++;

    broadcast("alert", {
        title: alert.title,
        message: alert.desc,
        severity: alert.severity,
        timestamp: new Date().toLocaleTimeString()
    });
}, 14000);

// 4. SSE Heartbeat Keep-Alive (every 15 seconds)
setInterval(() => {
    if (clients.size === 0) return;
    const heartbeatComment = `: keep-alive ${new Date().toISOString()}\n\n`;
    for (const client of clients.values()) {
        try {
            client.res.write(heartbeatComment);
        } catch (_) {}
    }
}, 15000);

// -------------------------------------------------------------
// HTTP REQUEST ROUTER
// -------------------------------------------------------------
const server = http.createServer((req, res) => {
    const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    const pathname = parsedUrl.pathname;

    // CORS Headers for API flexibility
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID");

    if (req.method === "OPTIONS") {
        res.writeHead(204);
        res.end();
        return;
    }

    // 1. Serve Frontend UI
    if (pathname === "/" || pathname === "/index.html") {
        const filePath = path.join(__dirname, "index.html");
        fs.readFile(filePath, "utf8", (err, data) => {
            if (err) {
                res.writeHead(500, { "Content-Type": "text/plain" });
                res.end("Internal Server Error loading index.html");
                return;
            }
            res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
            res.end(data);
        });
        return;
    }

    // 2. Server-Sent Events Endpoint: /events
    if (pathname === "/events") {
        res.writeHead(200, {
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        });

        const clientId = "client_" + Math.random().toString(36).substring(2, 9);
        clients.set(clientId, {
            id: clientId,
            res,
            connectedAt: Date.now(),
            remoteAddress: req.socket.remoteAddress
        });

        console.log(`[SSE] Client connected: ${clientId} (Total active: ${clients.size})`);

        // Check for Last-Event-ID header (or fallback to query parameter)
        const lastEventIdHeader = req.headers["last-event-id"] || parsedUrl.searchParams.get("lastEventId");
        let replayedCount = 0;

        if (lastEventIdHeader) {
            const parsedLastId = parseInt(lastEventIdHeader, 10);
            if (!isNaN(parsedLastId)) {
                // Find all missed events in the ring buffer
                const missed = eventBuffer.filter(e => e.id > parsedLastId);
                if (missed.length > 0) {
                    console.log(`[SSE] Replaying ${missed.length} missed events for ${clientId} (since ID ${parsedLastId})`);
                    for (const item of missed) {
                        res.write(formatSSE(item));
                    }
                    replayedCount = missed.length;
                }
            }
        }

        // Send initial handshake / welcome event
        const handshake = formatSSE({
            id: nextEventId++,
            event: "connected",
            retry: 2500,
            data: {
                clientId,
                message: "SSE connection established successfully",
                replayedEvents: replayedCount,
                lastSeenEventId: lastEventIdHeader || null,
                marketSnapshot: marketData,
                serverTime: new Date().toISOString(),
                protocolInfo: {
                    features: ["Named Events", "Event IDs", "Last-Event-ID Replay", "Heartbeats", "Custom Retry"]
                }
            }
        });
        res.write(handshake);

        // Handle client disconnection
        req.on("close", () => {
            clients.delete(clientId);
            console.log(`[SSE] Client disconnected: ${clientId} (Remaining active: ${clients.size})`);
        });

        return;
    }

    // 3. POST /api/broadcast - Trigger a broadcast notification to all SSE clients
    if (pathname === "/api/broadcast" && req.method === "POST") {
        let body = "";
        req.on("data", chunk => { body += chunk; });
        req.on("end", () => {
            try {
                const parsed = JSON.parse(body || "{}");
                const sender = parsed.user || "Anonymous";
                const message = parsed.message || "Broadcast message from user";

                const broadcastResult = broadcast("broadcast", {
                    sender,
                    message,
                    timestamp: new Date().toLocaleTimeString()
                });

                res.writeHead(200, { "Content-Type": "application/json" });
                res.end(JSON.stringify({
                    success: true,
                    eventId: broadcastResult.id,
                    recipientCount: clients.size
                }));
            } catch (e) {
                res.writeHead(400, { "Content-Type": "application/json" });
                res.end(JSON.stringify({ error: "Invalid JSON body" }));
            }
        });
        return;
    }

    // 4. POST /api/spike - Trigger an instant simulated price shock to demo reactive push
    if (pathname === "/api/spike" && req.method === "POST") {
        let body = "";
        req.on("data", chunk => { body += chunk; });
        req.on("end", () => {
            try {
                const parsed = JSON.parse(body || "{}");
                const symbol = parsed.symbol || "BTC";
                const direction = parsed.direction || (Math.random() > 0.5 ? "up" : "down");
                const asset = marketData[symbol] || marketData.BTC;

                const multiplier = direction === "up" ? 1.055 : 0.945;
                const oldPrice = asset.price;
                asset.price = Number((asset.price * multiplier).toFixed(2));
                asset.high = Math.max(asset.high, asset.price);
                asset.low = Math.min(asset.low, asset.price);
                asset.change24h = Number((((asset.price - asset.base) / asset.base) * 100).toFixed(2));

                // Send immediate ticker tick
                broadcast("ticker", {
                    symbol: asset.symbol,
                    name: asset.name,
                    price: asset.price,
                    previousPrice: oldPrice,
                    delta: Number((asset.price - oldPrice).toFixed(2)),
                    change24h: asset.change24h,
                    high: asset.high,
                    low: asset.low,
                    volume: asset.volume + 500,
                    isSpike: true
                });

                // Send immediate high-priority alert
                broadcast("alert", {
                    title: `Simulated Shock: ${asset.symbol} ${direction === "up" ? "Surge" : "Flash Drop"}!`,
                    message: `${asset.symbol} shifted from $${oldPrice} to $${asset.price} (${direction === "up" ? "+" : ""}${((multiplier - 1) * 100).toFixed(1)}%).`,
                    severity: direction === "up" ? "success" : "warning",
                    timestamp: new Date().toLocaleTimeString()
                });

                res.writeHead(200, { "Content-Type": "application/json" });
                res.end(JSON.stringify({ success: true, newPrice: asset.price }));
            } catch (err) {
                res.writeHead(400, { "Content-Type": "application/json" });
                res.end(JSON.stringify({ error: "Failed to trigger spike" }));
            }
        });
        return;
    }

    // 5. GET /api/stats - JSON stats endpoint
    if (pathname === "/api/stats" && req.method === "GET") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({
            activeClients: clients.size,
            totalEvents: nextEventId - 1,
            ringBufferCount: eventBuffer.length,
            uptime: Math.floor(process.uptime()),
            marketData
        }));
        return;
    }

    // 404 Fallback
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("404 Not Found");
});

server.listen(PORT, () => {
    console.log(`\n======================================================`);
    console.log(`⚡ Raw SSE Hub v2.0 is live!`);
    console.log(`📡 URL: http://localhost:${PORT}`);
    console.log(`📊 SSE Stream: http://localhost:${PORT}/events`);
    console.log(`======================================================\n`);
});