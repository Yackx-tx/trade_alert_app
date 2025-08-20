import yfinance as yf
import requests
import time
from datetime import datetime
from flask import Flask, request, jsonify
import threading

from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/webhook/*": {"origins": "*"}})  # Allow all for testing

bot_token = "8435434203:AAFh0LTspLznj4zpkFc2h93nASAgp3tU5Os"
channel_id = "-1002707403736"
url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

def get_options_chain():
    try:
        spy = yf.Ticker("SPY")
        expiry = spy.options[0]
        opt_chain = spy.option_chain(expiry)

        spy_price = spy.history(period="1d")["Close"].iloc[-1]

        calls = opt_chain.calls
        price_range = spy_price * 0.02
        filtered_calls = calls[
            (calls['strike'] >= spy_price - price_range) &
            (calls['strike'] <= spy_price + price_range)
        ].head(3)

        if filtered_calls.empty:
            filtered_calls = calls.head(1)

        options = []
        for _, row in filtered_calls.iterrows():
            strike = row["strike"]
            option_price = row["ask"]
            target_points = strike - spy_price
            target_percent = round((target_points / spy_price) * 100, 2)

            options.append({
                "symbol": "SPY",
                "type": "CALL",
                "strike": strike,
                "expiry": expiry,
                "price": option_price,
                "target": f"{target_percent}%"
            })
        return spy_price, options
    except Exception as e:
        print("Error fetching options:", e)
        return None, None


def format_message(spy_price, options):
    """Format the message in the target format"""
    message_lines = [
        f"📊 SPY Options Chain (SPY Price: {round(spy_price, 2)})",
        ""
    ]

    for opt in options:
        formatted_line = (
            f"{opt['symbol']} {opt['type']} "
            f"Strike: {opt['strike']} "
            f"Expiry: {opt['expiry']} "
            f"Price: {opt['price']} "
            f"Target: {opt['target']}"
        )
        message_lines.append(formatted_line)

    return "\n".join(message_lines)


def send_to_telegram(message):
    """Send message to Telegram"""
    try:
        response = requests.post(url, data={"chat_id": channel_id, "text": message})
        return response.status_code == 200
    except Exception as e:
        print("Error sending to Telegram:", e)
        return False


def process_options_data():
    """Fetch and process options data"""
    spy_price, options = get_options_chain()
    if not options:
        return None, "Error: Could not fetch SPY options data"

    message = format_message(spy_price, options)
    return options[0], message

@app.route('/webhook/trigger-scrape', methods=['POST', 'GET'])
def trigger_scrape():
    """Webhook endpoint to trigger scraping and send to Telegram"""
    try:
        option_data, message = process_options_data()

        if option_data is None:
            return jsonify({"error": message}), 500

        if send_to_telegram(message):
            print("Sent:", message)
            print("-" * 50)
            return jsonify({
                "success": True,
                "message": "Data sent to Telegram",
                "option_data": option_data,
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({"error": "Failed to send to Telegram"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/check-conditions', methods=['POST'])
def check_conditions():
    """Webhook to check conditions before triggering scrape"""
    try:
        spy_price, options = get_options_chain()

        if not options:
            return jsonify({"error": "Could not fetch data"}), 500

        option = options[0]

        conditions = {
            "market_hours": 9 <= datetime.now().hour <= 16,
            "price_change": abs(float(option['target'].replace('%', ''))) > 0.5,
            "option_price": option['price'] > 0.1
        }

        should_trigger = all(conditions.values())

        return jsonify({
            "should_trigger": should_trigger,
            "conditions": conditions,
            "current_data": {
                "spy_price": round(spy_price, 2),
                "option": option
            },
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/manual-send', methods=['POST'])
def manual_send():
    """Manual trigger endpoint - just get data and return it"""
    try:
        option_data, message = process_options_data()

        if option_data is None:
            return jsonify({"error": message}), 500

        return jsonify({
            "success": True,
            "message": message,
            "option_data": option_data,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


if __name__ == "__main__":
    print("Starting SPY Options Webhook Server...")
    print("Available endpoints:")
    print("- POST /webhook/trigger-scrape - Trigger scraping and send to Telegram")
    print("- POST /webhook/check-conditions - Check if conditions are met for triggering")
    print("- POST /webhook/manual-send - Get data without sending to Telegram")
    print("- GET /health - Health check")

    # Send Telegram alert on startup (when the server starts)
    try:
        option_data, message = process_options_data()
        if option_data is not None:
            sent = send_to_telegram(message)
            if sent:
                print("Startup alert sent to Telegram.")
            else:
                print("Failed to send startup alert to Telegram.")
        else:
            print("No data to send on startup.")
    except Exception as e:
        print(f"Error sending startup alert: {e}")

    try:
        app.run(host='127.0.0.1', port=8000, debug=True, threaded=True, use_reloader=False)
    except OSError as e:
        print(f"Socket error: {e}")
        print("Trying alternative configuration...")
        app.run(host='localhost', port=8001, debug=False, threaded=True)
