import sqlite3
import datetime
import json
from flask import g, Flask, render_template, flash, redirect, request, session, jsonify
from flask_session import Session
from helpers import login_required
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

DATABASE = "flashcards.db"

def get_db():
    db = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db



def init_db():
    
    with get_db() as db:

        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            username TEXT NOT NULL,
            hash TEXT NOT NULL,
            registration_date DATE NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            cards TEXT,
            folders TEXT,
            keywords TEXT,
            path TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            creation_date DATE NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            creation_date DATE NOT NULL
        )""")


@app.context_processor       
def inject_user():
    if "user_id" in session:
        user = {}
        with get_db() as db:
            user = db.execute("SELECT username FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        return dict(username=user["username"])
    return dict(username=None)

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def before_request():
    init_db()

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"]) 
@login_required
def index():
    """Get Home page"""

    user_id = session["user_id"]

    if request.method == "POST":
        return redirect("/")

    else:
        folders = []

        with get_db() as db:
            folders = db.execute("SELECT * FROM folders WHERE user_id = (?)", (user_id,)).fetchall()        
    
        return render_template("index.html", folders=folders,) 



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""


    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if not username:
            flash("You must enter your username", "danger")
            return redirect("/login")
        elif not password:
            flash("You must enter your password", "danger")
            return redirect("/login")

        with get_db() as db:
            rows = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchall()

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            flash("Invalid username and/or password", "danger")
            return redirect("/login")

        # Forget any user id
        session.clear()
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    """Log user out"""

    session.clear()

    flash("Logged out !", "primary")
    
    return redirect("/login")
    


@app.route("/register", methods=["GET", "POST"])
def register():
    """Allow user to register"""

    registration_date = datetime.datetime.now()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            flash("You must provide a username", "danger")
            return redirect("/register")
        elif not password:
            flash("You must provide a password", "danger")
            return redirect("/register")
        elif not confirmation:
            flash("You must confirm password", "danger")
            return redirect("/register")
        elif password != confirmation:
            flash("Passwords don't match", "danger")
            return redirect("/register")

        hash_password = generate_password_hash(password, method="pbkdf2:sha256")

        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO users (username, hash, registration_date) VALUES (?, ?, ?)",
                    (username, hash_password, registration_date),
                )
        except sqlite3.IntegrityError:
            flash("Username already exists", "danger")
            return redirect("/register")

        # Fetch new user ID
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

        session["user_id"] = row["id"]
        flash("Registered successfully!", "success")

        return redirect("/")

    return render_template("register.html")


@app.route("/create_list", methods=["GET", "POST"])
@login_required
def create_list():
    user_id = session["user_id"]

    creation_date = datetime.datetime.now()

    if request.method == "POST":
        list_title = request.form.get("title")
        list_description = request.form.get("description")
        cards_number = request.form.get("cards-number")

        cards = []

        for i in range(int(cards_number)):
            index = i + 1
            card_term = request.form.get(f"term_card_{index}")
            card_definition = request.form.get(f"definition_card_{index}")

            cards.append({
                "id": index,
                "term": card_term,
                "definition": card_definition
            })
        
        # Ensure the user has at least create two cards 
        if int(cards_number) <= 2 and (cards[0]["term"] == "" and cards[0]["definition"] == "") or (cards[1]["term"] == "" and cards[1]["definition"] == ""):
            flash("You need at least two cards to create a list", "danger")
            return redirect("/create_list")

        cards_json = json.dumps(cards)

        with get_db() as db:

            lists_number = db.execute("SELECT COUNT(*) FROM lists").fetchone()

            lists_last_id = int(lists_number["COUNT(*)"])

            path = str.lower(str(list_title)) + "_" + str(lists_last_id + 1)

            db.execute(
                "INSERT INTO lists (title, description, cards, path, user_id, creation_date) VALUES (?, ?, ?, ?, ?, ?)",
                (list_title, list_description, cards_json, path, user_id, creation_date)
            )

        flash("List created successfully!", "success")
        return redirect("/")

    return render_template("create_list.html")

@app.route("/create_folder", methods=["POST"])
@login_required
def create_folder():

    user_id = session["user_id"]

    creation_date = datetime.datetime.now()

    name = request.form.get("name")

    if not name:
        flash("You must choose a folder name", "danger")
        return redirect("/")


    with get_db() as db:
        folders = db.execute("SELECT COUNT(*) FROM folders WHERE user_id = (?)", (user_id,)).fetchone()

        folders_last_id = int(folders["COUNT(*)"])

        path = str(str.lower((name))) + "_" + str(folders_last_id + 1)

        db.execute("INSERT INTO folders (name, path, user_id, creation_date) VALUES (?, ?, ?, ?)", (name, path, user_id, creation_date))


    return redirect("/")



@app.route("/user/<username>/folders/<folder_path>")
def show_folder(username, folder_path):

    user_id = session["user_id"]
    folder = []
    lists = []
    formatted_lists = []
    lists_in_folder = []
    folder_id = ""

    with get_db() as db:
        folder = db.execute("SELECT * FROM folders WHERE path = (?)", (folder_path,)).fetchone()

        lists = db.execute("SELECT * FROM lists WHERE user_id = (?)", (user_id,)).fetchall()

        if folder:
            folder_id = folder["id"]

        
    for list in lists:
        cards = json.loads(list["cards"])

        folders = ""

        keywords = []

        if list["folders"]:
            folders = json.loads(list["folders"])

        if list["keywords"]:
            keywords = json.loads(list["keywords"])

        formatted_lists.append({
            "id": list["id"],
            "title": list["title"],
            "description": list["description"],
            "cards": cards,
            "folders": folders,
            "keywords": keywords,
            "path": list["path"],
            "creation_date": list["creation_date"]
            }
            )
    
    for list in formatted_lists:

        if str(folder_id) in list["folders"] and not list in lists_in_folder:
            lists_in_folder.append(list)

    return render_template("folder.html", folder=folder, folder_path=folder_path, folder_lists=lists_in_folder, all_lists=formatted_lists)


@app.route("/user/<username>/lists/<list_path>")
def show_list(username, list_path):

    user_id = session["user_id"]
    folders_list = []
    list = []

    formatted_list = {}

    with get_db() as db:

        folders_list = db.execute("SELECT * FROM folders").fetchall()
        list = db.execute("SELECT * FROM lists WHERE path = (?)", (list_path,)).fetchone()

        folders = []

        keywords = []

        if list and list["folders"]:
            folders = json.loads(list["folders"])

        if list and list["keywords"]:
            keywords = json.loads(list["keywords"])

        formatted_list = {
            "id": list["id"],
            "title": list["title"],
            "description": list["description"],
            "cards": json.loads(list["cards"]),
            "folders": folders,
            "path": list["path"],
            "keywords": keywords,
            "creation_date": list["creation_date"]
            }
            
        list = formatted_list

    return render_template("list.html", list=formatted_list, list_path=list_path, folders_list=folders_list)



@app.route("/add_to_folder", methods=["POST"])
@login_required
def add_to_folder():

    user_id = session["user_id"]

    folder_id = request.form.get("folder_id")

    list_id = request.form.get("list_id")

    row = []

    with get_db() as db:

        row = db.execute("SELECT folders FROM lists WHERE id = (?) AND user_id = (?)", (list_id, user_id,)).fetchone()


    folders = []
    if row and row["folders"]:
        folders = json.loads(row["folders"])  
    
    if folder_id not in folders: 
        folders.append(folder_id)

    folders_json = json.dumps(folders)

    with get_db() as db:
        db.execute("UPDATE lists SET folders = (?) WHERE id = (?) AND user_id = (?)", (folders_json, list_id, user_id))


    return redirect("/")


@app.route("/remove_from_folder", methods=["POST"])
@login_required
def remove_from_folder():

    user_id = session["user_id"]

    folder_id = request.form.get("folder_id")

    list_id = request.form.get("list_id")

    row = []

    with get_db() as db:

        row = db.execute("SELECT folders FROM lists WHERE id = (?) AND user_id = (?)", (list_id, user_id,)).fetchone()


    folders = []
    if row and row["folders"]:
        folders = json.loads(row["folders"])  
    
    if folder_id in folders: 
        folders.remove(folder_id)

    folders_json = json.dumps(folders)

    with get_db() as db:
        db.execute("UPDATE lists SET folders = (?) WHERE id = (?) AND user_id = (?)", (folders_json, list_id, user_id))


    return redirect("/")


@app.route("/create_keyword", methods=["POST"])
@login_required
def create_keyword():
    
    user_id = session["user_id"]

    keywordName = request.form.get("keyword")

    listId = request.form.get("list_id")

    if not keywordName:
        flash("You must enter a keyword", "danger")

    row = []

    with get_db() as db:
        row = db.execute("SELECT keywords FROM lists WHERE id = (?) AND user_id = (?)", (listId, user_id,)).fetchone()

        list_keywords = []

        if row["keywords"]:
            list_keywords = json.loads(row["keywords"])

        keyword = {
            "id": (len(list_keywords) + 1),
            "keyword": keywordName,
            "active": True
        }
        list_keywords.append(keyword)

        json_keywords = json.dumps(list_keywords)

        db.execute("UPDATE lists SET keywords = (?) WHERE id = (?) AND user_id = (?)", (json_keywords, listId, user_id))

    
    return redirect("/")


@app.route("/update_keyword_status", methods=["POST"])
@login_required
def update_keyword_status():
    
    user_id = session["user_id"]
    data = request.get_json()
    list_id = data.get("list_id")
    keyword_id = data.get("keyword_id")
    active = True if data.get("active") else False


    with get_db() as db:
        keywords = db.execute("SELECT keywords FROM lists WHERE id = (?) AND user_id = (?)", (list_id, user_id,)).fetchone()

        keywords = json.loads(keywords["keywords"])

        for keyword in keywords:
            if int(keyword["id"]) == int(keyword_id):
                keyword["active"] = active

        jsonKeywords = json.dumps(keywords)
        
        db.execute("""
            UPDATE lists
            SET keywords = (?)
            WHERE id = (?) AND user_id = ?
        """, (jsonKeywords, list_id, user_id))

    return jsonify(success=True)


@app.route("/update_card", methods=["POST"])
@login_required
def update_card():

    user_id = session["user_id"]

    username = request.form.get("username")
    list_path = request.form.get("list_path")

    list_id = request.form.get("list_id")
    card_id = request.form.get("card_id")

    new_term = request.form.get("new_term")
    new_definition = request.form.get("new_definition")

    path = "/user/" + str(username) + "/lists/" + str(list_path)

    print(path)
    print(list_path)

    if new_term == "" and new_definition == "":
        return redirect(path)
    
    with get_db() as db:
        cards = db.execute("SELECT cards FROM lists WHERE id = (?) AND user_id = (?)", (list_id, user_id,)).fetchone()

        cards = json.loads(cards["cards"])

        for card in cards:
            if card["id"] == int(card_id):
                card["term"] = new_term
                card["definition"] = new_definition


        jsonCards = json.dumps(cards)

        db.execute("UPDATE lists SET cards = (?) WHERE id = (?) AND user_id = (?)", (jsonCards, list_id, user_id))

    return redirect(path)