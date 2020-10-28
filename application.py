import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    userStocks = db.execute("SELECT * FROM stocks WHERE user_id = :user", user=session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])[0]['cash']

    total = cash
    stocks = []
    for user in userStocks:
        stock = lookup(user['symbol'])
        L = [stock['symbol'], stock['name'], user['shares'], stock['price'], round(stock['price'] * user['shares'], 2)]
        stocks.append(L)
        total += round(stock['price'] * user['shares'], 2)

    return render_template("index.html", stocks=stocks, cash=round(cash, 2), total=round(total, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("must provide a symbol and number of shares", 403)

        elif not lookup(request.form.get("symbol").upper()):
            return apology("wrong symbol", 400)

        else:
            stock = lookup(request.form.get("symbol").upper());
            shares=int(request.form.get("shares"))
            cash = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])[0]['cash']

            if stock["price"]*shares > cash:
                return apology("No enough money for you to purchase")

            purchase = db.execute("SELECT shares FROM stocks WHERE user_id = :user AND symbol = :symbol", user=session["user_id"], symbol=stock["symbol"])

            if not purchase:
                db.execute("INSERT INTO stocks(user_id, symbol, shares) VALUES (:user, :symbol, :shares)", user=session["user_id"],
                symbol=stock["symbol"], shares=shares)

            else:
                db.execute("UPDATE stocks SET shares = :shares WHERE user_id = :user AND symbol = :symbol",user=session["user_id"],
                                symbol=stock["symbol"], shares=shares+purchase[0]["shares"])

            db.execute("UPDATE users SET cash = :cash WHERE id = :user",
                            cash=cash - stock["price"]*shares, user=session["user_id"])
            db.execute("INSERT INTO history(user_id, symbol, shares, Price) VALUES (:user, :symbol, :shares, :Price)",
                            user=session["user_id"], symbol=stock["symbol"], shares=shares, Price=round(stock["price"]*shares, 2))

            return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    history = db.execute("SELECT * FROM history WHERE user_id = :user", user=session["user_id"])
    transactions = []
    for trans in history:
        stock = lookup(trans['symbol'])
        L = [stock['symbol'], trans['shares'], trans['Price'], trans['date']]
        transactions.append(L)

    return render_template("history.html", transactions=transactions)


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        if not request.form.get("symbol").upper():
            return apology("must provide symbol", 403)

        elif not lookup(request.form.get("symbol").upper()):
            return apology("wrong symbol", 400)

        else:
            symbol = lookup(request.form.get("symbol").upper());
            return render_template("quote.html", symbol=symbol)
    else:
        return render_template("quote.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        if not lookup(request.form.get("symbol").upper()):
            return apology("wrong symbol", 400)

        else:
            stock = lookup(request.form.get("symbol").upper());
            shares=int(request.form.get("shares"))
            cash = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])[0]['cash']
            s = db.execute("SELECT shares FROM stocks WHERE user_id = :user AND symbol = :symbol", user=session["user_id"], symbol=stock["symbol"])[0]['shares']

            if shares > s:
                return apology("too many shares", 400)

            elif shares == s:
                db.execute("DELETE FROM stocks WHERE user_id = :user AND symbol = :symbol",
                                symbol=stock["symbol"], user=session["user_id"])

            else:
                db.execute("UPDATE stocks SET shares = :shares WHERE user_id = :user AND symbol = :symbol",user=session["user_id"],
                                symbol=stock["symbol"], shares= s - shares)

            db.execute("UPDATE users SET cash = :cash WHERE id = :user",
                            cash=cash + stock["price"]*shares, user=session["user_id"])
            db.execute("INSERT INTO history(user_id, symbol, shares, Price) VALUES (:user, :symbol, :shares, :Price)",
                            user=session["user_id"], symbol=stock["symbol"], shares=-shares, Price=round(stock["price"]*shares, 2))

        return redirect("/")

    else:
        symbols = db.execute("SELECT symbol FROM stocks WHERE user_id = :user", user=session["user_id"])
        s = []
        for symbol in symbols:
            s.append(symbol['symbol'])

        return render_template("sell.html",symbols=s)


@app.route("/register", methods=["GET", "POST"])
def register():
    session.clear()
    if request.method == "POST":
        if not request.form.get("username") or not request.form.get("password"):
            return apology("must provide username and/or password", 403)

        elif request.form.get("password") != request.form.get("cpassword"):
            return apology("The passwords don't match", 403)

        elif db.execute("SELECT * FROM users WHERE username = :username",username=request.form.get("username")):
            return apology("Username already taken", 403)

        db.execute("INSERT INTO users(username, hash) VALUES (:username, :hashPass)",
            username=request.form.get("username"), hashPass=generate_password_hash(request.form.get("password")))

        user = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        session["user_id"] = user[0]["id"]

        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
