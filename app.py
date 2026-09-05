import concurrent.futures
from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
import os

# Konfigurera Flask att leta efter statiska filer och templates i rotmappen
app = Flask(__name__, static_folder='.', template_folder='.')

# Listor med tillgångar per kategori
ASSETS = {
    'stocks': [
        'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'BRK-B', 'LLY', 'AMD',
        'NFLX', 'INTC', 'CRM', 'PYPL', 'ADBE', 'NKE', 'DIS', 'PEP', 'KO',
        'BAC', 'JPM', 'WMT', 'COST', 'T', 'VZ', 'CSCO', 'ORCL', 'CMCSA', 'XOM',
        'CVX', 'PFE', 'MRK', 'ABBV', 'JNJ', 'UNH', 'HD', 'LOW', 'CAT', 'BA', 'VOLV-B.ST'
    ],
    'crypto': [
        'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'XRP-USD', 'ADA-USD', 'DOGE-USD',
        'AVAX-USD', 'DOT-USD', 'LINK-USD', 'SHIB-USD', 'LTC-USD', 'NEAR-USD',
        'POL-USD', 'ICP-USD', 'XLM-USD', 'ATOM-USD', 'ETC-USD', 'FIL-USD', 
        'HBAR-USD', 'ALGO-USD', 'VET-USD'
    ],
    'index': [
        '^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX', '^FTSE', '^GDAXI', '^FCHI',
        '^STOXX50E', '^N225', '^HSI', '000001.SS', '^BSESN', '^AXJO'
    ],
    'metals': [
        'GC=F', 'SI=F', 'PL=F', 'PA=F', 'HG=F'
    ],
    'forex': [
        'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDSEK=X', 'EURSEK=X', 'AUDUSD=X',
        'USDCAD=X', 'USDCHF=X', 'NZDUSD=X'
    ]
}

def map_period(period):
    """Omvandlar ogiltiga frontend-perioder till yfinance-kompatibla format."""
    mapping = {
        '1w': '5d',
        '1m': '1mo',
        '1d': '1d',
        '1mo': '1mo',
        '3mo': '3mo',
        '6mo': '6mo',
        '1y': '1y',
        '2y': '2y',
        '5y': '5y',
        '10y': '10y',
        'ytd': 'ytd',
        'max': 'max'
    }
    return mapping.get(str(period).lower(), '1d')

def get_asset_category(symbol):
    """Hittar vilken kategori en symbol tillhör."""
    for cat, symbols in ASSETS.items():
        if symbol in symbols:
            return cat
    return 'stocks'

def fetch_single_ticker(symbol, category, raw_period='1d'):
    """Hämtar historik och grunddata för en enskild symbol."""
    try:
        yf_period = map_period(raw_period)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='5d' if yf_period == '1d' else yf_period)
        
        if hist.empty or len(hist) < 2:
            return None

        current_price = hist['Close'].iloc[-1]
        
        # Beräkna förändring baserat på tidsperiod
        if raw_period == '1w' and len(hist) >= 5:
            prev_price = hist['Close'].iloc[-5]
        elif raw_period == '1m':
            hist_m = ticker.history(period='1mo')
            prev_price = hist_m['Close'].iloc[0] if not hist_m.empty else hist['Close'].iloc[0]
        elif raw_period == '1y':
            hist_y = ticker.history(period='1y')
            prev_price = hist_y['Close'].iloc[0] if not hist_y.empty else hist['Close'].iloc[0]
        else:
            prev_price = hist['Close'].iloc[-2]

        change_pct = ((current_price - prev_price) / prev_price) * 100

        display_symbol = symbol.replace('-USD', '').replace('=X', '').replace('=F', '').replace('^', '')

        return {
            'symbol': display_symbol,
            'raw_symbol': symbol,
            'name': ticker.info.get('shortName', display_symbol),
            'price': round(float(current_price), 2),
            'changePercent': round(float(change_pct), 2),
            'category': category
        }
    except Exception:
        return None

@app.route('/')
def index():
    """Serverar index.html direkt från projektets rotmapp."""
    if not os.path.exists('index.html'):
        return "FELETS ORSAK: index.html saknas i mappen C:\\Users\\armin\\OneDrive\\Skrivbord\\aktie_app", 404
    return send_from_directory('.', 'index.html')

@app.route('/api/market-data')
def get_market_data():
    period = request.args.get('period', '1d')
    category_filter = request.args.get('category', 'all')
    
    all_results = []
    tasks = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for cat, symbols in ASSETS.items():
            if category_filter not in ['all', 'gainers', 'losers', 'favorites', 'portfolio'] and category_filter != cat:
                continue
            for sym in symbols:
                tasks.append(executor.submit(fetch_single_ticker, sym, cat, period))
                
        for future in concurrent.futures.as_completed(tasks):
            res = future.result()
            if res:
                all_results.append(res)

    return jsonify(all_results)

@app.route('/api/stock/<path:symbol>')
def get_stock_detail(symbol):
    try:
        raw_period = request.args.get('period', '1mo')
        yf_period = map_period(raw_period)

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=yf_period if yf_period != '1d' else '1mo')
        info = ticker.info

        if hist.empty:
            return jsonify({'error': 'Ingen data hittades för symbolen.'}), 404

        chart_data = []
        for index_date, row in hist.iterrows():
            chart_data.append({
                'time': index_date.strftime('%Y-%m-%d'),
                'value': round(float(row['Close']), 2)
            })

        category = get_asset_category(symbol)

        return jsonify({
            'symbol': symbol,
            'shortName': info.get('shortName', symbol),
            'currentPrice': round(float(hist['Close'].iloc[-1]), 2),
            'peRatio': info.get('trailingPE', 'N/A'),
            'dividendYield': round(info.get('dividendYield', 0) * 100, 2) if info.get('dividendYield') else 0,
            'category': category,
            'chartData': chart_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Startar servern på http://127.0.0.1:5000")
    app.run(debug=True, port=5000)