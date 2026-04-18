let priceChart = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchTrades();
    loadChart('SPY');

    // Refresh data every 10 seconds
    setInterval(() => {
        fetchStatus();
        fetchTrades();
    }, 10000);

    // Symbol selector
    document.getElementById('chart-symbol').addEventListener('change', (e) => {
        loadChart(e.target.value);
    });

    // Start Engine button (Manually trigger a bot cycle)
    document.getElementById('btn-start-engine').addEventListener('click', async () => {
        const btn = document.getElementById('btn-start-engine');
        btn.textContent = 'Scanning Market...';
        btn.disabled = true;

        try {
            const res = await fetch('/api/cron');
            const data = await res.json();
            if (data.status === "success") {
                btn.textContent = '✓ Scan Complete';
                btn.classList.add('btn-success');
                fetchTrades(); // Refresh table
                setTimeout(() => { btn.textContent = 'Manual Scan'; btn.classList.remove('btn-success'); btn.disabled = false; }, 4000);
            } else {
                btn.textContent = 'Error';
                setTimeout(() => { btn.textContent = 'Manual Scan'; btn.disabled = false; }, 3000);
            }
        } catch (err) {
            console.error('Failed to run bot cycle', err);
            btn.textContent = 'Manual Scan';
            btn.disabled = false;
        }
    });
});

// ── Status ──────────────────────────────────────────────────

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const balEl = document.getElementById('balance-value');
        if (typeof data.paper_balance === 'number') {
            balEl.textContent = '$' + data.paper_balance.toLocaleString('en-US', {minimumFractionDigits: 2});
        } else {
            balEl.textContent = data.paper_balance;
        }
        
        const pnlEl = document.getElementById('pnl-value');
        if (typeof data.daily_profit === 'number') {
            const sign = data.daily_profit >= 0 ? '+' : '';
            pnlEl.textContent = sign + '$' + data.daily_profit.toLocaleString('en-US', {minimumFractionDigits: 2});
            pnlEl.className = data.daily_profit >= 0 ? 'profit' : 'loss';
        } else {
            pnlEl.textContent = data.daily_profit;
            pnlEl.className = '';
        }

        document.getElementById('winrate-value').textContent = data.win_rate;
        document.getElementById('status-value').textContent = data.bot_status;

        // Update connection badge
        const badge = document.getElementById('connection-badge');
        const connText = document.getElementById('connection-text');
        if (data.bot_status && data.bot_status.includes('Connected')) {
            badge.classList.add('connected');
            connText.textContent = 'API Connected';
        } else if (data.bot_status && data.bot_status.includes('Running')) {
            badge.classList.add('connected');
            connText.textContent = 'Bot Running';
        } else {
            badge.classList.remove('connected');
            connText.textContent = 'Disconnected';
        }
        
    } catch (err) {
        console.error("Error fetching status", err);
    }
}

// ── Trades ──────────────────────────────────────────────────

async function fetchTrades() {
    try {
        const response = await fetch('/api/trades');
        const data = await response.json();
        
        const tbody = document.getElementById('trades-body');
        tbody.innerHTML = '';
        
        data.forEach(trade => {
            const tr = document.createElement('tr');

            const isNum = (v) => typeof v === 'number' && !isNaN(v);
            const fmt = (v) => isNum(v) ? '$' + Math.abs(v).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '–';
            
            const pnlNum   = isNum(trade.pnl) ? trade.pnl : 0;
            const pnlClass = trade.profit === false ? 'loss' : (trade.profit === true ? 'profit' : '');
            const pnlSign  = pnlNum >= 0 ? '+' : '-';
            const badgeClass = trade.type === 'BUY' ? 'badge-buy' : trade.type === 'SELL' ? 'badge-sell' : '';
            
            tr.innerHTML = `
                <td><strong>${trade.symbol}</strong></td>
                <td><span class="badge ${badgeClass}">${trade.type}</span></td>
                <td>${fmt(trade.entry)}</td>
                <td>${fmt(trade.exit)}</td>
                <td class="${pnlClass}">${isNum(trade.pnl) ? pnlSign + fmt(trade.pnl) : '–'}</td>
            `;
            tbody.appendChild(tr);
        });
        
    } catch (err) {
        console.error("Error fetching trades", err);
    }
}

// ── Candlestick Chart ───────────────────────────────────────

async function loadChart(symbol) {
    document.getElementById('chart-title').textContent = `Price History — ${symbol}`;

    try {
        const res = await fetch(`/api/chart/${symbol}`);
        const data = await res.json();

        if (data.error) {
            console.error('Chart error:', data.error);
            return;
        }

        const ctx = document.getElementById('price-chart').getContext('2d');

        if (priceChart) {
            priceChart.destroy();
        }

        // Transform API data into candlestick format
        const candleData = data.candles.map(c => ({
            x: new Date(c.x).getTime(),
            o: c.o,
            h: c.h,
            l: c.l,
            c: c.c,
        }));

        priceChart = new Chart(ctx, {
            type: 'candlestick',
            data: {
                datasets: [{
                    label: data.symbol,
                    data: candleData,
                    color: {
                        up: '#3fb950',
                        down: '#f85149',
                        unchanged: '#8b949e',
                    },
                    borderColor: {
                        up: '#3fb950',
                        down: '#f85149',
                        unchanged: '#8b949e',
                    },
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(22, 27, 34, 0.95)',
                        titleColor: '#f0f6fc',
                        bodyColor: '#8b949e',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: (ctx) => {
                                const d = ctx.raw;
                                return [
                                    `Open:  $${d.o.toFixed(2)}`,
                                    `High:  $${d.h.toFixed(2)}`,
                                    `Low:   $${d.l.toFixed(2)}`,
                                    `Close: $${d.c.toFixed(2)}`,
                                ];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'week',
                            displayFormats: { week: 'MMM dd' },
                        },
                        ticks: { color: '#8b949e', maxTicksLimit: 10 },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    },
                    y: {
                        ticks: {
                            color: '#8b949e',
                            callback: (v) => '$' + v.toFixed(0),
                        },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    }
                }
            }
        });

    } catch (err) {
        console.error('Chart fetch failed', err);
    }
}
