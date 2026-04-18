
from flask import Flask, render_template, request, redirect, session, jsonify
import uuid

app = Flask(__name__)
app.secret_key = "secret"

users = {"陳韋廷": {"password":"1234","blacklisted":False}}
admin = "陳韋廷"

inventory = []
warehouse = {}

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["user"]
        p = request.form["pass"]
        if u in users and users[u]["password"] == p:
            if users[u]["blacklisted"]:
                return "帳號已被停用"
            session["user"]=u
            return redirect("/home")
    return render_template("login.html")

@app.route("/home")
def home():
    return render_template("home.html", user=session.get("user"))

@app.route("/inventory", methods=["GET","POST"])
def inv():
    if request.method == "POST":
        items = request.form["batch"].split("\n")
        for i in items:
            if i.strip():
                inventory.append(i.strip())
    return render_template("inventory.html", data=inventory)

@app.route("/warehouse")
def wh():
    return render_template("warehouse.html", warehouse=warehouse, data=inventory)

@app.route("/place", methods=["POST"])
def place():
    warehouse[request.form["slot"]] = request.form["item"]
    return "ok"

@app.route("/move", methods=["POST"])
def move():
    src = request.form["src"]
    dst = request.form["dst"]
    if src in warehouse:
        warehouse[dst] = warehouse.pop(src)
    return "ok"

@app.route("/search")
def search():
    q = request.args.get("q","")
    result = {k:v for k,v in warehouse.items() if q in v}
    return jsonify(result)

@app.route("/admin")
def admin_page():
    if session.get("user")!=admin:
        return "no permission"
    return render_template("admin.html", users=users)

@app.route("/block/<name>")
def block(name):
    users[name]["blacklisted"]=True
    return redirect("/admin")

@app.route("/unblock/<name>")
def unblock(name):
    users[name]["blacklisted"]=False
    return redirect("/admin")

app.run(host="0.0.0.0", port=5000)
