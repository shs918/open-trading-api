/**
 * KIS 자동매매 대시보드 — 메인 로직.
 *
 * WebSocket으로 실시간 데이터를 수신하고 UI를 갱신한다.
 */

let ws = null;
let isPaused = false;

// ─── 초기화 ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    fetchInitialData();
});

// ─── WebSocket ─────────────────────────────────────────────────

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws/dashboard`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        console.log('WebSocket 연결됨');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'dashboard_update') {
            updateDashboard(data);
        } else if (data.type === 'notification') {
            addNotification(data);
        }
    };

    ws.onclose = () => {
        console.log('WebSocket 연결 해제, 5초 후 재연결');
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket 오류:', err);
    };
}

// ─── 초기 데이터 로드 ──────────────────────────────────────────

async function fetchInitialData() {
    try {
        const [status, portfolio, orders, regime, notifications] = await Promise.all([
            fetchJson('/api/status'),
            fetchJson('/api/portfolio'),
            fetchJson('/api/orders'),
            fetchJson('/api/regime'),
            fetchJson('/api/notifications'),
        ]);

        updateStatus(status);
        updatePortfolio(portfolio);
        updateOrders(orders);
        updateRegime(regime);
        updateNotifications(notifications);
    } catch (e) {
        console.error('초기 데이터 로드 실패:', e);
    }
}

async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

// ─── UI 업데이트 ───────────────────────────────────────────────

function updateDashboard(data) {
    if (data.status) updateStatus(data.status);
    if (data.portfolio) updatePortfolioSummary(data.portfolio);
    if (data.orders) updateOrderSummary(data.orders);
    if (data.notifications) updateNotificationsFromWs(data.notifications);
}

function updateStatus(status) {
    const modeBadge = document.getElementById('mode-badge');
    modeBadge.textContent = status.mode ? status.mode.toUpperCase() : 'PAPER';
    modeBadge.dataset.mode = status.mode || 'paper';

    const regimeBadge = document.getElementById('regime-badge');
    regimeBadge.textContent = status.regime || '분석 전';

    const marketState = document.getElementById('market-state');
    const stateMap = {
        'before_market': '장 시작 전',
        'nxt_pre_market': 'NXT 프리마켓',
        'regular_open': '정규장 운영 중',
        'after_hours': '시간외',
        'market_closed': '장 종료',
    };
    marketState.textContent = '장 상태: ' + (stateMap[status.market_state] || '-');
    marketState.dataset.state = status.market_state || '';

    document.getElementById('uptime').textContent = '가동: ' + (status.uptime || '-');

    isPaused = status.paused || false;
    const btn = document.getElementById('btn-pause');
    btn.textContent = isPaused ? '재개' : '일시정지';
    btn.className = isPaused ? 'btn btn-buy' : 'btn btn-warning';
}

function updatePortfolio(portfolio) {
    updatePortfolioSummary(portfolio);

    const tbody = document.getElementById('positions-body');
    const positions = portfolio.positions || [];
    document.getElementById('position-count').textContent = positions.length;

    if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">보유 종목 없음</td></tr>';
        return;
    }

    tbody.innerHTML = positions.map(p => {
        const profitClass = p.profit_rate >= 0 ? 'positive' : 'negative';
        return `<tr>
            <td>${p.name || p.ticker}<br><small>${p.ticker}</small></td>
            <td>${p.quantity.toLocaleString()}</td>
            <td>${Math.round(p.avg_price).toLocaleString()}</td>
            <td>${Math.round(p.current_price).toLocaleString()}</td>
            <td class="${profitClass}">${p.profit_rate.toFixed(2)}%</td>
            <td><button class="btn-cancel" onclick="sellPosition('${p.ticker}', ${p.quantity})">매도</button></td>
        </tr>`;
    }).join('');
}

function updatePortfolioSummary(p) {
    const totalEval = p.total_eval || 0;
    const pnl = p.total_profit_loss || 0;
    const rate = p.total_profit_rate || 0;
    const cashRatio = p.cash_ratio || 0;

    document.getElementById('total-eval').textContent = formatKRW(totalEval);

    const pnlEl = document.getElementById('daily-pnl');
    pnlEl.textContent = formatKRW(pnl);
    pnlEl.className = 'card-value ' + (pnl >= 0 ? 'positive' : 'negative');

    const rateEl = document.getElementById('total-return');
    rateEl.textContent = rate.toFixed(2) + '%';
    rateEl.className = 'card-value ' + (rate >= 0 ? 'positive' : 'negative');

    document.getElementById('cash-ratio').textContent = cashRatio.toFixed(1) + '%';
}

function updateOrders(orders) {
    const tbody = document.getElementById('orders-body');
    document.getElementById('order-count').textContent = Array.isArray(orders) ? orders.length : 0;

    if (!Array.isArray(orders) || orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">주문 내역 없음</td></tr>';
        return;
    }

    tbody.innerHTML = orders.map(o => {
        const time = o.timestamp ? new Date(o.timestamp).toLocaleTimeString('ko-KR') : '-';
        const sideText = o.side === 'buy' ? '매수' : '매도';
        const sideClass = o.side === 'buy' ? 'positive' : 'negative';
        return `<tr>
            <td>${time}</td>
            <td>${o.ticker}</td>
            <td class="${sideClass}">${sideText}</td>
            <td>${o.quantity.toLocaleString()}</td>
            <td>${o.status}</td>
        </tr>`;
    }).join('');
}

function updateOrderSummary(summary) {
    document.getElementById('order-count').textContent = summary.total || 0;
}

function updateRegime(regime) {
    const label = document.getElementById('regime-label');
    label.textContent = regime.regime_kr || regime.regime || '-';

    const badge = document.getElementById('regime-badge');
    badge.textContent = regime.regime_kr || '분석 전';
    badge.dataset.regime = regime.regime || '';

    document.getElementById('regime-confidence').textContent =
        '신뢰도: ' + (regime.confidence ? regime.confidence.toFixed(1) + '%' : '-');

    // 점수 바
    const scoresDiv = document.getElementById('regime-scores');
    const scores = regime.scores || {};
    const labels = {
        kospi_trend: 'KOSPI 추세',
        momentum: '모멘텀',
        foreign_flow: '외국인',
        institution_flow: '기관',
        volume: '거래량',
        new_highlow: '신고가/저가',
        short_selling: '공매도',
        disparity: '이격도',
        volatility: '변동성',
    };

    scoresDiv.innerHTML = Object.entries(scores).map(([key, value]) => {
        const scoreLabel = labels[key] || key;
        const numVal = Number(value) || 0;
        const pct = Math.min(Math.abs(numVal) / 2 * 100, 100);
        const cls = numVal > 0 ? 'positive' : numVal < 0 ? 'negative' : 'neutral';
        return `<div class="score-row">
            <span class="score-label">${scoreLabel}</span>
            <div class="score-bar"><div class="score-fill ${cls}" style="width:${pct}%"></div></div>
            <span class="score-value">${numVal.toFixed(1)}</span>
        </div>`;
    }).join('');
}

function updateNotifications(notifications) {
    const div = document.getElementById('notifications');
    if (!Array.isArray(notifications) || notifications.length === 0) {
        div.innerHTML = '<div class="notification-item">알림 없음</div>';
        return;
    }
    div.innerHTML = notifications.slice(-20).reverse().map(n => {
        const time = n.timestamp ? new Date(n.timestamp).toLocaleTimeString('ko-KR') : '';
        const cls = n.level || 'info';
        return `<div class="notification-item ${cls}">
            <span class="time">${time}</span>${n.message}
        </div>`;
    }).join('');
}

function updateNotificationsFromWs(notifications) {
    if (Array.isArray(notifications) && notifications.length > 0) {
        updateNotifications(notifications);
    }
}

function addNotification(data) {
    const div = document.getElementById('notifications');
    const time = new Date().toLocaleTimeString('ko-KR');
    const cls = data.level || 'info';
    const el = document.createElement('div');
    el.className = `notification-item ${cls}`;
    el.innerHTML = `<span class="time">${time}</span>${data.message || ''}`;
    div.prepend(el);
    // 최대 20건 유지
    while (div.children.length > 20) {
        div.removeChild(div.lastChild);
    }
}

// ─── 시스템 제어 ───────────────────────────────────────────────

async function togglePause() {
    const url = isPaused ? '/api/control/resume' : '/api/control/pause';
    try {
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        isPaused = data.paused;
        const btn = document.getElementById('btn-pause');
        btn.textContent = isPaused ? '재개' : '일시정지';
        btn.className = isPaused ? 'btn btn-buy' : 'btn btn-warning';
    } catch (e) {
        alert('제어 실패: ' + e.message);
    }
}

// ─── 유틸리티 ──────────────────────────────────────────────────

function formatKRW(amount) {
    if (amount >= 100000000) {
        return (amount / 100000000).toFixed(2) + '억';
    } else if (amount >= 10000) {
        return (amount / 10000).toFixed(0) + '만';
    }
    return Math.round(amount).toLocaleString() + '원';
}

// 5초마다 REST로 데이터 새로고침 (WS 백업)
setInterval(async () => {
    try {
        const [portfolio, orders] = await Promise.all([
            fetchJson('/api/portfolio'),
            fetchJson('/api/orders'),
        ]);
        updatePortfolio(portfolio);
        updateOrders(orders);
    } catch (e) {
        // silent fail
    }
}, 5000);
