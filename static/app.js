'use strict';

// ── Chart.js global defaults ──────────────────────────────
const C = { blue: '#58a6ff', green: '#3fb950', red: '#f85149', orange: '#d29922', purple: '#bc8cff', teal: '#39d353', muted: '#8b949e', surf: '#161b22', border: '#30363d' };
const PAL = [C.blue, C.green, C.purple, C.orange, C.teal, C.red];
const GRID_OPT = { color: 'rgba(48,54,61,0.6)' };
Chart.defaults.color = '#8b949e';
Chart.defaults.font.family = "'Inter',sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.labels.boxWidth = 12;
Chart.defaults.plugins.legend.labels.padding = 14;

// ── State ─────────────────────────────────────────────────
let charts = {};
let refreshTimer = null;

// ── Utilities ─────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fmt = n => n == null ? '—' : n >= 1e6 ? '$' + (n / 1e6).toFixed(2) + 'M' : n >= 1e3 ? '$' + (n / 1e3).toFixed(1) + 'K' : '$' + Number(n).toLocaleString();
const fmtN = n => n == null ? '—' : Number(n).toLocaleString();

function toast(msg, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3800);
}

function renderMarkdown(text) {
    return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

// ── KPI Cards ─────────────────────────────────────────────
async function fetchKPIs() {
    try {
        const data = await fetch('/api/kpis').then(r => r.json());
        $('kpi-revenue').textContent = fmt(data.total_revenue);
        $('kpi-profit').textContent = fmt(data.total_profit);
        $('kpi-margin').textContent = (data.profit_margin ?? 0).toFixed(1) + '%';
        $('kpi-aov').textContent = fmt(data.aov);
        $('kpi-orders').textContent = fmtN(data.total_orders);
        $('kpi-customers').textContent = fmtN(data.unique_customers);
        $('kpi-repeat').textContent = (data.repeat_rate ?? 0) + '%';
        $('kpi-region').textContent = data.top_region ?? '—';
        $('nav-count').innerHTML = `<span>${fmtN(data.total_orders)}</span> orders`;

        const yoyEl = $('kpi-yoy-sub');
        if (data.yoy_growth != null) {
            const up = data.yoy_growth >= 0;
            yoyEl.textContent = (up ? '▲ ' : '▼ ') + Math.abs(data.yoy_growth) + '% YoY';
            yoyEl.className = 'kpi-sub ' + (up ? 'up' : 'down');
        }
    } catch (e) { console.error('KPI fetch failed', e); }
}

// ── Insights ──────────────────────────────────────────────
function renderInsights(insights, fresh = false) {
    const list = $('insights-list');
    list.innerHTML = insights.map(i =>
        `<div class="insight-item ${fresh ? 'fresh' : ''}">${renderMarkdown(i)}</div>`
    ).join('');
}

async function fetchInsights() {
    const data = await fetch('/api/insights').then(r => r.json());
    renderInsights(data);
}

// ── Charts ────────────────────────────────────────────────
function destroyChart(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }

async function fetchCharts() {
    const [monthly, products, regions, cats] = await Promise.all([
        fetch('/api/chart/monthly').then(r => r.json()),
        fetch('/api/chart/products').then(r => r.json()),
        fetch('/api/chart/regions').then(r => r.json()),
        fetch('/api/chart/categories').then(r => r.json()),
    ]);

    // Monthly trend
    destroyChart('chartMonthly');
    charts['chartMonthly'] = new Chart($('chartMonthly'), {
        type: 'line',
        data: {
            labels: monthly.map(d => d.month),
            datasets: [
                { label: 'Revenue', data: monthly.map(d => d.revenue), borderColor: C.blue, backgroundColor: 'rgba(88,166,255,.08)', fill: true, tension: .4, pointRadius: 3, pointBackgroundColor: C.blue },
                { label: 'Profit', data: monthly.map(d => d.profit), borderColor: C.green, backgroundColor: 'rgba(63,185,80,.08)', fill: true, tension: .4, pointRadius: 3, pointBackgroundColor: C.green },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'top' } },
            scales: {
                x: { grid: GRID_OPT, ticks: { maxTicksLimit: 12, maxRotation: 45 } },
                y: { grid: GRID_OPT, ticks: { callback: v => fmt(v) } }
            }
        }
    });

    // Top 10 products (horizontal bar)
    destroyChart('chartProducts');
    charts['chartProducts'] = new Chart($('chartProducts'), {
        type: 'bar',
        data: {
            labels: products.map(p => p.Product.length > 20 ? p.Product.slice(0, 20) + '…' : p.Product),
            datasets: [
                { label: 'Revenue', data: products.map(p => p.revenue), backgroundColor: C.blue, borderRadius: 4 },
                { label: 'Profit', data: products.map(p => p.profit), backgroundColor: C.green, borderRadius: 4 },
            ]
        },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { x: { grid: GRID_OPT, ticks: { callback: v => fmt(v) } }, y: { grid: { display: false } } }
        }
    });

    // Regions doughnut
    destroyChart('chartRegions');
    charts['chartRegions'] = new Chart($('chartRegions'), {
        type: 'doughnut',
        data: {
            labels: regions.map(r => r.Region),
            datasets: [{ data: regions.map(r => r.revenue), backgroundColor: PAL, borderColor: C.surf, borderWidth: 2, hoverOffset: 6 }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '60%',
            plugins: {
                legend: { position: 'right' },
                tooltip: { callbacks: { label: ctx => `${ctx.label}: ${fmt(ctx.raw)} | Margin: ${regions[ctx.dataIndex]?.margin}%` } }
            }
        }
    });

    // Categories bar
    destroyChart('chartCats');
    charts['chartCats'] = new Chart($('chartCats'), {
        type: 'bar',
        data: {
            labels: cats.map(c => c.Category),
            datasets: [
                { label: 'Revenue', data: cats.map(c => c.revenue), backgroundColor: cats.map((_, i) => PAL[i]), borderRadius: 6 },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { grid: { display: false } }, y: { grid: GRID_OPT, ticks: { callback: v => fmt(v) } } }
        }
    });
}

// ── Orders table ──────────────────────────────────────────
async function fetchOrders() {
    const orders = await fetch('/api/orders').then(r => r.json());
    const tbody = $('orders-tbody');
    if (!orders.length) { tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:24px">No orders yet. Add your first order!</td></tr>'; return; }

    tbody.innerHTML = orders.map(o => {
        const reg = o.Region?.toLowerCase() ?? 'north';
        const profit = o.Profit ?? 0;
        const col = profit >= 0 ? C.green : C.red;
        return `<tr>
          <td style="font-weight:600">${o.Order_ID}</td>
          <td>${o.Order_Date}</td>
          <td>${o.Customer_Name || o.Customer_ID}</td>
          <td><span class="tag tag-${reg}">${o.Region}</span></td>
          <td>${o.Product}</td>
          <td style="text-align:center">${o.Quantity}</td>
          <td>${fmt(o.Sales_Amount)}</td>
          <td style="color:${col};font-weight:600">${fmt(o.Profit)}</td>
          <td>${((o.Discount ?? 0) * 100).toFixed(0)}%</td>
          <td>${o.Category}</td>
          <td><button class="btn btn-danger" onclick="deleteOrder(${o.id})">✕</button></td>
        </tr>`;
    }).join('');
}

async function deleteOrder(id) {
    if (!confirm('Delete this order?')) return;
    await fetch(`/api/orders/${id}`, { method: 'DELETE' });
    toast('Order deleted');
    refreshAll();
}

// ── Full refresh ──────────────────────────────────────────
async function refreshAll(newInsights = null) {
    await Promise.all([fetchKPIs(), fetchCharts(), fetchOrders()]);
    if (newInsights) renderInsights(newInsights, true);
    else fetchInsights();
}

// ── Modal ─────────────────────────────────────────────────
function openModal() {
    $('modal-overlay').classList.add('open');
    switchTab('tab-prev');
    loadPrevOrders();
}
function closeModal() { $('modal-overlay').classList.remove('open'); }

function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    $(tabId).classList.add('active');
}

async function loadPrevOrders() {
    const orders = await fetch('/api/orders').then(r => r.json());
    const container = $('prev-orders-list');
    if (!orders.length) {
        container.innerHTML = '<p style="color:var(--muted);font-size:13px;padding:16px 0">No orders yet — be the first to add one!</p>';
        return;
    }
    container.innerHTML = orders.slice(0, 20).map(o => {
        const reg = o.Region?.toLowerCase() ?? 'north';
        const profit = o.Profit ?? 0;
        const pCol = profit >= 0 ? C.green : C.red;
        return `<div class="prev-order-row">
          <div class="prev-info">
            <div class="prev-id">${o.Order_ID} · <span class="tag tag-${reg}">${o.Region}</span></div>
            <div class="prev-meta">${o.Product} · ${o.Customer_Name || o.Customer_ID} · ${o.Order_Date}</div>
          </div>
          <div style="text-align:right">
            <div class="prev-amt">${fmt(o.Sales_Amount)}</div>
            <div class="prev-pft" style="color:${pCol}">${profit >= 0 ? '▲' : '▼'} ${fmt(Math.abs(profit))} profit</div>
          </div>
        </div>`;
    }).join('');
}

// ── Live revenue/profit preview ───────────────────────────
function updatePreview() {
    const qty = parseFloat($('f-qty').value) || 0;
    const up = parseFloat($('f-price').value) || 0;
    const cp = parseFloat($('f-cost').value) || 0;
    const disc = (parseFloat($('f-disc').value) || 0) / 100;
    const rev = qty * up * (1 - disc);
    const pft = rev - qty * cp;
    $('prev-rev').textContent = rev > 0 ? fmt(rev) : '—';
    $('prev-pft').textContent = pft !== 0 ? fmt(pft) : '—';
    const pftEl = $('prev-pft-item');
    pftEl.className = 'preview-item ' + (pft >= 0 ? 'profit-pos' : 'profit-neg');
}
['f-qty', 'f-price', 'f-cost', 'f-disc'].forEach(id => {
    const el = $(id);
    if (el) el.addEventListener('input', updatePreview);
});

// ── Submit new order ──────────────────────────────────────
async function submitOrder(e) {
    e.preventDefault();
    const btn = $('submit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Saving...';

    const body = {
        Order_Date: $('f-date').value,
        Customer_Name: $('f-customer').value,
        Region: $('f-region').value,
        Product: $('f-product').value,
        Category: $('f-category').value,
        Quantity: $('f-qty').value,
        Unit_Price: $('f-price').value,
        Cost_Price: $('f-cost').value,
        Discount: $('f-disc').value,
    };

    try {
        const res = await fetch('/api/orders', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const data = await res.json();

        if (!res.ok) { toast('❌ ' + (data.error ?? 'Error saving order'), 'error'); return; }

        // Show warnings
        const warnBox = $('form-warnings');
        if (data.warnings?.length) {
            warnBox.innerHTML = data.warnings.map(w => `<div class="warning-item">⚠ ${w}</div>`).join('');
            warnBox.style.display = 'block';
        } else {
            warnBox.style.display = 'none';
        }

        toast('✅ Order saved — insights updated!');
        $('order-form').reset();
        updatePreview();
        closeModal();
        await refreshAll(data.insights);

    } catch (err) {
        toast('❌ Network error', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Order';
    }
}

// ── CSV Import ────────────────────────────────────────────
function triggerFileInput() { $('csv-input').click(); }

$('csv-input')?.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const label = $('file-drop-label');
    const originalText = label.textContent;
    label.textContent = `⏳ Importing ${file.name}...`;

    const isClear = $('clear-data-chk').checked;
    const form = new FormData();
    form.append('file', file);
    form.append('clear', isClear);

    try {
        const res = await fetch('/api/import', { method: 'POST', body: form });
        const data = await res.json();

        if (!res.ok) { toast('❌ Import failed: ' + (data.error ?? ''), 'error'); return; }

        toast(`✅ Imported ${data.inserted} rows (${data.skipped} skipped)`);
        closeModal();
        await refreshAll(data.insights);

    } catch (err) {
        toast('❌ Import error', 'error');
    } finally {
        label.textContent = originalText;
        e.target.value = ''; // Reset so the same file can be selected again
    }
});

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Set today's date as default
    const today = new Date().toISOString().split('T')[0];
    const dateField = $('f-date');
    if (dateField) dateField.value = today;

    await refreshAll();

    // Auto-refresh every 30s
    refreshTimer = setInterval(() => refreshAll(), 30_000);

    // Close modal on overlay click
    $('modal-overlay').addEventListener('click', e => {
        if (e.target === $('modal-overlay')) closeModal();
    });
});
