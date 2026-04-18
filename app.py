
from flask import Flask, request, session, redirect, render_template, jsonify
from flask_socketio import SocketIO
import os

app = Flask(__name__)
app.secret_key = "secret"
socketio = SocketIO(app, cors_allowed_origins="*")

users = {"陳韋廷":{"password":"1234","blacklisted":False}}

inventory = []
warehouse = {}

@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form["user"]
        p=request.form["pass"]
        if u in users and users[u]["password"]==p:
            if users[u]["blacklisted"]:
                return "帳號已被停用"
            session["user"]=u
            return redirect("/home")
    return render_template("login.html")

@app.route("/home")
def home():
    if "user" not in session:
        return redirect("/")
    return render_template("home.html", inventory=inventory, warehouse=warehouse, user=session["user"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/inventory", methods=["POST"])
def add_inventory():
    if "user" not in session:
        return "no login"
    items=request.form.get("batch","").split("\n")
    for i in items:
        if i.strip():
            inventory.append(i.strip())
    socketio.emit("update")
    return "ok"

@app.route("/place", methods=["POST"])
def place():
    slot=request.form["slot"]
    item=request.form["item"]
    warehouse[slot]=item
    socketio.emit("update")
    return "ok"

@app.route("/move", methods=["POST"])
def move():
    src=request.form["src"]
    dst=request.form["dst"]
    if src in warehouse:
        warehouse[dst]=warehouse.pop(src)
    socketio.emit("update")
    return "ok"

@app.route("/search")
def search():
    q=request.args.get("q","")
    return jsonify({k:v for k,v in warehouse.items() if q in v})

@app.route("/admin")
def admin():
    if session.get("user")!="陳韋廷":
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

if __name__ == "__main__":
    port=int(os.environ.get("PORT",10000))
    socketio.run(app,host="0.0.0.0",port=port)
