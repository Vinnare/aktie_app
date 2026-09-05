import concurrent.futures
from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
import os

app = Flask(__name__, static_folder='.', template_folder='.')

# Minskad lista för stabilare drift på gratis-servrar
ASSETS = {
    'stocks': [
        'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD',
        'NFLX', 'INTC', 'CRM', 'PYPL', 'ADBE', 'DIS', 'KO',
        'BAC', 'JPM', 'WMT', 'COST', 'XOM', 'JNJ', 'VOLV-B.ST'
    ],
    'crypto': [
        'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'XRP-USD', 'ADA-USD', 'DOGE-USD'
    ],
    'index': [
        '^GSPC', '^DJI', '^IXIC', '^STOXX50E'
    ],
    'metals': [
        'GC=F', 'SI=F'
    ],
    'forex': [
        'EURUSD=X', 'USDSEK=X', 'EURSEK=X'
    ]
}

def map_period(period):
    mapping = {
        '1w': '5d', '1m': '1mo', '1d': '1d', '1mo': '1mo',
        '3mo': '3mo', '6mo': '6mo', '1y': '1y', 'max': 'max'
    }
    return mapping.get(str(period).lower(), '1d')

def get_asset_category(symbol):
    for cat, symbols in ASSETS.items():
        if symbol in symbols:
            return cat
    return 'stocks'

def fetch_single_ticker(symbol, category, raw_period='1d'):
    try:
        yf_period = map_period(raw_period)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='5d' if yf_period == '1d' else yf_period)
        
        if hist.empty or len(hist) < 2:
            return None

        current_price = hist['Close'].iloc[-1]
        
        if raw_period == '1w' and len(hist) >= 5:
            prev_price = hist['Close'].iloc[-5]
        elif raw_period == '1m':
            prev_price = hist['Close'].iloc[0]
        elif raw_period == '1y':
            prev_price = hist['Close'].iloc[0]
        else:
            prev_price = hist['Close'].iloc[-2]

        change_pct = ((current_price - prev_price) / prev_price) * 100
        display_symbol = symbol.replace('-USD', '').replace('=X', '').replace('=F', '').replace('^', '')

        return {
            'symbol': display_symbol,
            'raw_symbol': symbol,
            'name': ticker.info.get('shortName', display_symbol) if hasattr(ticker, 'info') else display_symbol,
            'price': round(float(current_price), 2),
            'changePercent': round(float(change_pct), 2),
            'category': category
        }
    except Exception:
        return None

@app.route('/')
def index():
    if not os.path.exists('index.html'):
        return "index.html saknas", 404
    return send_from_directory('.', 'index.html')

@app.route('/api/market-data')
def get_market_data():
    period = request.args.get('period', '1d')
    category_filter = request.args.get('category') or 'all'
    
    all_results = []
    tasks = []
    
    # Sänkt max_workers till 5 för att förhindra att Yahoo blockerar förfrågningarna
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for cat, symbols in ASSETS.items():
            if category_filter not in ['all', 'gainers', 'losers', 'favorites', 'portfolio'] and category_filter != cat:
                continue
            for sym in symbols:
                tasks.append(executor.submit(fetch_single_ticker, sym, cat, period))
                
        for future in concurrent.futures.as_completed(tasks):
            try:
                res = future.result()
                if res:
                    all_results.append(res)
            except Exception:
                continue

    return jsonify(all_results)

@app.route('/api/stock/<path:symbol>')
def get_stock_detail(symbol):
    try:
        raw_period = request.args.get('period', '1mo')
        yf_period = map_period(raw_period)

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=yf_period if yf_period != '1d' else '1mo')

        if hist.empty:
            return jsonify({'error': 'Ingen data hittades.'}), 404

        chart_data = []
        for index_date, row in hist.iterrows():
            chart_data.append({
                'time': index_date.strftime('%Y-%m-%d'),
                'value': round(float(row['Close']), 2)
            })

        return jsonify({
            'symbol': symbol,
            'shortName': symbol,
            'currentPrice': round(float(hist['Close'].iloc[-1]), 2),
            'peRatio': 'N/A',
            'dividendYield': 0,
            'category': get_asset_category(symbol),
            'chartData': chart_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)