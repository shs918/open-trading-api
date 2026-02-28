/**
 * KIS 자동매매 대시보드 — 매뉴얼 매매 기능.
 */

// ─── 종목 시세 조회 ────────────────────────────────────────────

async function lookupPrice() {
    const ticker = document.getElementById('trade-ticker').value.trim();
    if (!ticker) {
        alert('종목코드를 입력해주세요.');
        return;
    }

    const infoDiv = document.getElementById('price-info');
    infoDiv.style.display = 'block';
    infoDiv.textContent = '조회 중...';

    try {
        const res = await fetch(`/api/market/${ticker}`);
        if (!res.ok) {
            const err = await res.json();
            infoDiv.textContent = '조회 실패: ' + (err.detail || res.statusText);
            return;
        }
        const data = await res.json();

        const name = data.hts_kor_isnm || data.rprs_mrkt_kor_name || ticker;
        const price = Number(data.stck_prpr || 0);
        const change = Number(data.prdy_ctrt || 0);
        const changeClass = change >= 0 ? 'positive' : 'negative';
        const sign = change >= 0 ? '+' : '';

        infoDiv.innerHTML = `
            <strong>${name}</strong> (${ticker})<br>
            현재가: <span class="${changeClass}">${price.toLocaleString()}원</span>
            (${sign}${change.toFixed(2)}%)
        `;

        // 가격 필드 자동 설정
        document.getElementById('trade-price').value = price;
    } catch (e) {
        infoDiv.textContent = '조회 오류: ' + e.message;
    }
}

// ─── 매수 ──────────────────────────────────────────────────────

async function manualBuy() {
    const params = getTradeParams();
    if (!params) return;

    if (!confirm(`매수 주문\n${params.ticker} ${params.quantity}주\n${params.price === 0 ? '시장가' : params.price.toLocaleString() + '원'}\n\n진행하시겠습니까?`)) {
        return;
    }

    try {
        const res = await fetch('/api/trade/buy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
        const data = await res.json();

        if (!res.ok) {
            alert('매수 실패: ' + (data.detail || data.message));
            return;
        }

        alert(`매수 주문 완료\n주문번호: ${data.order_no || '-'}\n상태: ${data.status}`);
        clearTradeForm();

        // 주문 내역 새로고침
        const orders = await fetchJson('/api/orders');
        updateOrders(orders);
    } catch (e) {
        alert('매수 오류: ' + e.message);
    }
}

// ─── 매도 ──────────────────────────────────────────────────────

async function manualSell() {
    const params = getTradeParams();
    if (!params) return;

    if (!confirm(`매도 주문\n${params.ticker} ${params.quantity}주\n${params.price === 0 ? '시장가' : params.price.toLocaleString() + '원'}\n\n진행하시겠습니까?`)) {
        return;
    }

    try {
        const res = await fetch('/api/trade/sell', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
        const data = await res.json();

        if (!res.ok) {
            alert('매도 실패: ' + (data.detail || data.message));
            return;
        }

        alert(`매도 주문 완료\n주문번호: ${data.order_no || '-'}\n상태: ${data.status}`);
        clearTradeForm();

        const orders = await fetchJson('/api/orders');
        updateOrders(orders);
    } catch (e) {
        alert('매도 오류: ' + e.message);
    }
}

// ─── 포지션에서 직접 매도 ──────────────────────────────────────

async function sellPosition(ticker, quantity) {
    if (!confirm(`${ticker} 전량 매도 (${quantity}주, 시장가)\n진행하시겠습니까?`)) {
        return;
    }

    try {
        const res = await fetch('/api/trade/sell', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker,
                quantity: quantity,
                price: 0,
                market: 'KRX',
            }),
        });
        const data = await res.json();

        if (!res.ok) {
            alert('매도 실패: ' + (data.detail || data.message));
            return;
        }

        alert(`매도 주문 완료: ${ticker}\n주문번호: ${data.order_no || '-'}`);

        // 포트폴리오 새로고침
        const portfolio = await fetchJson('/api/portfolio');
        updatePortfolio(portfolio);
    } catch (e) {
        alert('매도 오류: ' + e.message);
    }
}

// ─── 헬퍼 ──────────────────────────────────────────────────────

function getTradeParams() {
    const ticker = document.getElementById('trade-ticker').value.trim();
    const quantity = parseInt(document.getElementById('trade-qty').value, 10);
    const price = parseInt(document.getElementById('trade-price').value, 10) || 0;
    const market = document.getElementById('trade-market').value;

    if (!ticker) {
        alert('종목코드를 입력해주세요.');
        return null;
    }
    if (!quantity || quantity <= 0) {
        alert('수량을 입력해주세요.');
        return null;
    }

    return {
        ticker: ticker,
        quantity: quantity,
        price: price,
        order_type: price === 0 ? 'market' : 'limit',
        market: market,
    };
}

function clearTradeForm() {
    document.getElementById('trade-ticker').value = '';
    document.getElementById('trade-qty').value = '';
    document.getElementById('trade-price').value = '';
    document.getElementById('price-info').style.display = 'none';
}
