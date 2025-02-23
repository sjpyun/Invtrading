from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import os

databasefile="trading_sim_data.db"
app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Ensure PORT is set properly
port = int(os.environ.get("PORT", 10000))  # If the system does not set 
# a number, set the port to 10000 per Render's documentation



@app.route("/")
def home():
    return "Trading Simulation" #render_template("login_web.html")



# Function to get web_id based on user_id and password
def get_web_id(user_id, password):
    conn = sqlite3.connect(databasefile)  # Connect to the database
    cursor = conn.cursor()
    
    # Query to check login credentials and get web_id
    cursor.execute("SELECT web_id FROM users WHERE user_id = ? AND password = ?", (user_id, password))
    user = cursor.fetchone()
    
    conn.close()  # Close database connection
    return user[0] if user else None  # Return web_id if found

@app.route("/login", methods=["POST"])
def login():
    data = request.json  # Get JSON data from frontend
    user_id = data.get("user_id")  # Student enters this
    password = data.get("password")

    web_id = get_web_id(user_id, password)  # Get web_id using user_id and password
    print("Web ID Retrieved:", web_id)  # Debugging

    if web_id:
        response = jsonify({"success": True, "web_id": web_id})
    else:
        response = jsonify({"success": False, "error": "Invalid credentials"})

    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    return response


@app.route("/get_user_info", methods=["GET"])
def get_user_info():
    web_id = request.args.get("web_id")

    conn = sqlite3.connect(databasefile)
    cursor = conn.cursor()

    # Fetch user_id based on web_id
    cursor.execute("SELECT user_id FROM users WHERE web_id = ?", (web_id,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return jsonify({"user_id": user[0]})
    else:
        return jsonify({"error": "User not found"}), 400

# **New Route: Fetch Stock Prices**
@app.route("/get_stock_prices", methods=["GET"])
def get_stock_prices():
    conn = sqlite3.connect("stock_prices.db")
    cursor = conn.cursor()

    cursor.execute("SELECT symbol, price, last_updated FROM stock_prices")
    stocks = cursor.fetchall()

    conn.close()

    # Convert list of tuples to list of dictionaries
    stock_data = [{"symbol": row[0], "price": row[1], "last_updated": row[2]} for row in stocks]
    return jsonify(stock_data)

    
@app.route("/get_balance", methods=["GET"])
def get_balance():
    web_id = request.args.get("web_id")

    conn = sqlite3.connect(databasefile)
    cursor = conn.cursor()

    # Fetch the balance for the logged-in user
    cursor.execute("SELECT balance FROM accounts WHERE web_id = ?", (web_id,))
    account = cursor.fetchone()
    
    conn.close()

    if account:
        return jsonify({"balance": account[0]})
    else:
        return jsonify({"error": "Account not found"}), 400

 
@app.route("/trade", methods=["POST"])
def place_trade():
    data = request.json
    web_id = data.get("web_id")
    symbol = data.get("symbol").upper()
    order_type = data.get("order_type")  # "buy" or "sell"
    quantity = int(data.get("quantity"))

    conn = sqlite3.connect(databasefile)
    cursor = conn.cursor()

    # Get latest stock price
    cursor.execute("SELECT price FROM stock_prices WHERE symbol = ?", (symbol,))
    stock = cursor.fetchone()
    if not stock:
        conn.close()
        return jsonify({"success": False, "error": "Stock not found"}), 400

    stock_price = stock[0]
    total_cost = stock_price * quantity

    # Get student balance
    cursor.execute("SELECT balance FROM accounts WHERE web_id = ?", (web_id,))
    account = cursor.fetchone()
    if not account:
        conn.close()
        return jsonify({"success": False, "error": "Account not found"}), 400

    balance = account[0]

    if order_type == "buy":
        if total_cost > balance:
            conn.close()
            return jsonify({"success": False, "error": "Insufficient funds"}), 400
        new_balance = balance - total_cost

        # Update holdings: Check if the student already owns this stock
        cursor.execute("SELECT quantity FROM holdings WHERE web_id = ? AND symbol = ?", (web_id, symbol))
        existing_holding = cursor.fetchone()

        if existing_holding:
            new_quantity = existing_holding[0] + quantity
            cursor.execute("UPDATE holdings SET quantity = ? WHERE web_id = ? AND symbol = ?", (new_quantity, web_id, symbol))
        else:
            cursor.execute("INSERT INTO holdings (web_id, symbol, quantity) VALUES (?, ?, ?)", (web_id, symbol, quantity))

    else:  # "sell"
        # Check if the student owns the stock (or is short-selling)
        cursor.execute("SELECT quantity FROM holdings WHERE web_id = ? AND symbol = ?", (web_id, symbol))
        existing_holding = cursor.fetchone()

        if existing_holding:
            new_quantity = existing_holding[0] - quantity
            if new_quantity < 0:
                conn.close()
                return jsonify({"success": False, "error": "Not enough shares to sell"}), 400
            if new_quantity == 0:
                cursor.execute("DELETE FROM holdings WHERE web_id = ? AND symbol = ?", (web_id, symbol))
            else:
                cursor.execute("UPDATE holdings SET quantity = ? WHERE web_id = ? AND symbol = ?", (new_quantity, web_id, symbol))
        else:
            conn.close()
            return jsonify({"success": False, "error": "Not enough shares to sell"}), 400

        new_balance = balance + total_cost

    # Update account balance
    cursor.execute("UPDATE accounts SET balance = ? WHERE web_id = ?", (new_balance, web_id))

    # Record the trade
    cursor.execute("INSERT INTO trades (web_id, symbol, order_type, quantity, price) VALUES (?, ?, ?, ?, ?)",
                   (web_id, symbol, order_type, quantity, stock_price))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "new_balance": new_balance})

@app.route("/get_holdings")
def get_holdings():
    web_id = request.args.get("web_id")

    conn = sqlite3.connect(databasefile)
    cursor = conn.cursor()

    # Aggregate total holdings per stock and their values
    cursor.execute("""
        SELECT t.symbol, 
               SUM(CASE WHEN t.order_type='buy' THEN t.quantity ELSE -t.quantity END) AS net_quantity,
               s.price
        FROM trades t
        JOIN stock_prices s ON t.symbol = s.symbol
        WHERE t.web_id = ?
        GROUP BY t.symbol
        HAVING net_quantity > 0
    """, (web_id,))

    holdings = []
    total_stock_value = 0

    for row in cursor.fetchall():
        symbol, quantity, price = row
        value = quantity * price
        holdings.append({"symbol": symbol, "quantity": quantity, "price": price, "value": value})
        total_stock_value += value  # Calculate total stock value

    conn.close()
    return jsonify({"holdings": holdings, "total_stock_value": total_stock_value})


@app.route("/get_trades")
def get_trades():
    web_id = request.args.get("web_id")

    conn = sqlite3.connect(databasefile)
    cursor = conn.cursor()

    # Fetch trade history
    cursor.execute("""
        SELECT symbol, order_type, quantity, price, timestamp
        FROM trades
        WHERE web_id = ?
        ORDER BY timestamp DESC
    """, (web_id,))

    trades = [{"symbol": row[0], "type": row[1], "quantity": row[2], "price": row[3], "timestamp": row[4]} for row in cursor.fetchall()]

    conn.close()
    return jsonify({"trades": trades})


if __name__ == "__main__": 
    app.run(host="0.0.0.0", port=port)
 

