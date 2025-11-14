from flask import Flask, request, jsonify, render_template_string, session
import google.generativeai as genai
from markdown import markdown
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os, secrets, time, html, smtplib
from email.message import EmailMessage

# ---------------- CONFIG ----------------
genai.configure(api_key="AIzaSyD-te-QqbQK2D69U_qQ1U9P4PfGwaK5j-g")  # TODO: put your Gemini API key here
model = genai.GenerativeModel("models/gemini-flash-latest")

app = Flask(__name__)
app.secret_key = "gurmansingh"

DB_PATH = "users.db"
chat_sessions = {}  # {username: {chat_id: chat_obj}}

# Email (OTP) config via environment variables
EMAIL_USER = os.getenv("premium696910@gmail.com")  # e.g. your Gmail
EMAIL_PASS = os.getenv("GURMANSINGH1221")  # e.g. Gmail App Password


def send_otp_email(to_email: str, username: str, otp: str):
    """Send OTP email if SMTP configured, otherwise just print to console."""
    if not EMAIL_USER or not EMAIL_PASS:
        print(f"[DEBUG] OTP for {username}: {otp} (SMTP not configured)")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = "Your GURMAN AI password reset code"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(
            f"Hi {username},\n\n"
            f"Your GURMAN AI OTP is: {otp}\n"
            f"It will expire in 10 minutes.\n\n"
            f"- GURMAN AI"
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        print(f"[INFO] OTP email sent to {to_email}")
    except Exception as e:
        print("[ERROR] Failed to send OTP email:", e)
        print(f"[DEBUG] OTP for {username}: {otp}")


# ---------------- DB INIT ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            reset_otp TEXT,
            reset_expire INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_key TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_key TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER
        )
        """
    )

    conn.commit()
    conn.close()


init_db()

# ---------------- FRONTEND ----------------
html_code = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>GURMAN AI CHAT BOT</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    * { margin:0; padding:0; box-sizing:border-box; }

    body {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #050509;
        color: #e5e5e5;
        height: 100vh;
        overflow: hidden;
        transition: background 0.3s, color 0.3s;
    }

    body.light {
        background: #f3f4f6;
        color: #111827;
    }

    .app {
        display: flex;
        height: 100vh;
        width: 100vw;
    }

    /* SIDEBAR */
    .sidebar {
        width: 260px;
        background: #0f1014;
        border-right: 1px solid #262730;
        display: flex;
        flex-direction: column;
        padding: 10px;
    }
    body.light .sidebar {
        background: #e5e7eb;
        border-right-color: #d1d5db;
    }

    .sidebar-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
        padding: 4px;
    }

    .logo-text {
        font-size: 16px;
        font-weight: 600;
        color: #f5f5f5;
    }
    body.light .logo-text {
        color: #111827;
    }

    .new-chat-btn {
        width: 100%;
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid #3f3f46;
        background: #111827;
        color: #e5e7eb;
        font-size: 14px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
    }
    body.light .new-chat-btn {
        background: #ffffff;
        color: #111827;
        border-color: #d1d5db;
    }

    .new-chat-btn span.icon {
        background: #22c55e;
        color: #0b1120;
        width: 18px;
        height: 18px;
        border-radius: 999px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
    }

    .chat-list-title {
        font-size: 12px;
        text-transform: uppercase;
        color: #9ca3af;
        margin-bottom: 6px;
        padding: 0 4px;
    }
    body.light .chat-list-title {
        color: #4b5563;
    }

    .chat-list {
        flex: 1;
        overflow-y: auto;
        padding-right: 4px;
    }

    .chat-item {
        padding: 8px 10px;
        border-radius: 8px;
        font-size: 14px;
        color: #e5e7eb;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
        justify-content: space-between;
    }
    body.light .chat-item {
        color: #111827;
    }

    .chat-item .left-part {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
    }

    .chat-item .dot {
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: #6b7280;
        flex-shrink: 0;
    }

    .chat-item .title {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .chat-item.active {
        background: #111827;
        border: 1px solid #3b82f6;
    }
    body.light .chat-item.active {
        background: #dbeafe;
        border-color: #3b82f6;
    }

    .chat-item.active .dot {
        background: #22c55e;
    }

    .chat-item .actions {
        display: none;
        gap: 4px;
        flex-shrink: 0;
    }
    .chat-item:hover .actions {
        display: flex;
    }

    .rename-btn, .delete-btn {
        background: transparent;
        border: none;
        cursor: pointer;
        font-size: 13px;
        opacity: 0.65;
        color: #e5e7eb;
    }
    body.light .rename-btn, body.light .delete-btn {
        color: #111827;
    }
    .rename-btn:hover {
        opacity: 1;
        color: #22c55e;
    }
    .delete-btn:hover {
        opacity: 1;
        color: #ef4444;
    }

    .sidebar-footer {
        font-size: 12px;
        color: #9ca3af;
        border-top: 1px solid #262730;
        padding-top: 8px;
        margin-top: 8px;
    }
    body.light .sidebar-footer {
        color: #4b5563;
        border-top-color: #d1d5db;
    }

    .sidebar-footer button {
        margin-top: 6px;
        padding: 6px 10px;
        border-radius: 6px;
        border: 1px solid #f97373;
        background: transparent;
        color: #f97373;
        font-size: 12px;
        cursor: pointer;
    }

    /* MAIN AREA */
    .main {
        flex: 1;
        display: flex;
        flex-direction: column;
        background: radial-gradient(circle at top, #1f2933 0, #050509 45%);
    }
    body.light .main {
        background: #f9fafb;
    }

    .top-bar {
        height: 50px;
        border-bottom: 1px solid #262730;
        padding: 0 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        backdrop-filter: blur(18px);
        background: linear-gradient(to right, #050509cc, #050509f0);
    }
    body.light .top-bar {
        border-bottom-color: #e5e7eb;
        background: #ffffff;
    }

    .top-bar-title {
        font-size: 14px;
        color: #9ca3af;
    }
    body.light .top-bar-title {
        color: #4b5563;
    }

    .top-bar-right {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 13px;
    }

    .top-bar-user {
        color: #d1d5db;
    }
    body.light .top-bar-user {
        color: #111827;
    }

    .top-bar-user span {
        color: #22c55e;
        font-weight: 600;
    }

    .theme-toggle {
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid #4b5563;
        background: transparent;
        color: #e5e7eb;
        font-size: 12px;
        cursor: pointer;
    }
    body.light .theme-toggle {
        color: #111827;
        border-color: #9ca3af;
    }

    .content {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 12px 16px;
        overflow: hidden;
    }

    .chat-box {
        flex: 1;
        overflow-y: auto;
        padding-right: 4px;
    }

    .msg-row {
        display: flex;
        margin-bottom: 10px;
    }

    .msg-row.user-row {
        justify-content: flex-end;
    }

    .msg-bubble {
        max-width: 70%;
        border-radius: 16px;
        padding: 10px 12px;
        font-size: 14px;
        line-height: 1.4;
        background: #111827;
        color: #e5e7eb;
        box-shadow: 0 1px 2px rgba(0,0,0,0.5);
        white-space: normal;
        word-wrap: break-word;
    }
    body.light .msg-bubble {
        background: #e5e7eb;
        color: #111827;
    }

    .msg-row.user-row .msg-bubble {
        background: #2563eb;
        color: #e5f3ff;
    }
    body.light .msg-row.user-row .msg-bubble {
        background: #3b82f6;
        color: #e5f3ff;
    }

    #typing {
        font-size: 12px;
        color: #9ca3af;
        margin-bottom: 6px;
        display: none;
    }

    /* Input area */
    .input-area {
        border-top: 1px solid #262730;
        padding: 10px 16px 14px;
    }
    body.light .input-area {
        border-top-color: #e5e7eb;
        background: #f9fafb;
    }

    .input-inner {
        max-width: 820px;
        margin: 0 auto;
        display: flex;
        gap: 8px;
        align-items: center;
        background: #050816;
        border-radius: 999px;
        border: 1px solid #374151;
        padding: 6px 8px;
    }
    body.light .input-inner {
        background: #ffffff;
        border-color: #d1d5db;
    }

    #message {
        flex: 1;
        border: none;
        background: transparent;
        outline: none;
        color: inherit;
        font-size: 14px;
        padding: 6px 8px;
    }

    #sendBtn, #micBtn, #regenBtn {
        border-radius: 999px;
        width: 34px;
        height: 34px;
        border: none;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 16px;
    }

    #sendBtn {
        background: #22c55e;
        color: #021114;
    }

    #sendBtn:hover {
        box-shadow: 0 0 10px rgba(34,197,94,0.7);
    }

    #micBtn {
        background: transparent;
        border: 1px solid #4b5563;
        color: #9ca3af;
    }
    body.light #micBtn {
        border-color: #9ca3af;
        color: #4b5563;
    }

    #micBtn.listening {
        background: #22c55e;
        color: #021114;
        border-color: #22c55e;
        box-shadow: 0 0 12px rgba(34,197,94,0.7);
    }

    #regenBtn {
        background: transparent;
        border: 1px solid #4b5563;
        color: #9ca3af;
    }
    body.light #regenBtn {
        border-color: #9ca3af;
        color: #4b5563;
    }
    #regenBtn:hover {
        box-shadow: 0 0 8px rgba(148,163,184,0.7);
    }

    /* Login overlay */
    .login-overlay {
        position: absolute;
        inset: 0;
        background: radial-gradient(circle, #111827ee 0, #020617f7 55%);
        display: flex;
        align-items: center;
        justify-content: center;
    }
    body.light .login-overlay {
        background: rgba(249,250,251,0.95);
    }

    .login-card {
        width: 100%;
        max-width: 380px;
        background: #020617;
        border-radius: 18px;
        border: 1px solid #1f2937;
        padding: 18px 18px 14px;
        box-shadow: 0 25px 60px rgba(0,0,0,0.75);
    }
    body.light .login-card {
        background: #ffffff;
        border-color: #e5e7eb;
    }

    .login-card h2 {
        font-size: 20px;
        margin-bottom: 6px;
        color: #e5e7eb;
    }
    body.light .login-card h2 {
        color: #111827;
    }

    .login-card p {
        font-size: 13px;
        color: #9ca3af;
        margin-bottom: 10px;
    }
    body.light .login-card p {
        color: #6b7280;
    }

    .login-card input {
        width: 100%;
        padding: 9px 10px;
        border-radius: 10px;
        border: 1px solid #374151;
        background: #020617;
        color: #e5e7eb;
        font-size: 13px;
        margin-bottom: 8px;
        outline: none;
    }
    body.light .login-card input {
        background: #f9fafb;
        color: #111827;
        border-color: #d1d5db;
    }

    .login-row-btns {
        display: flex;
        gap: 8px;
        margin-bottom: 4px;
    }

    .login-card button.primary {
        flex: 1;
        padding: 8px;
        border-radius: 999px;
        border: none;
        background: #22c55e;
        color: #02110f;
        font-weight: 600;
        font-size: 13px;
        cursor: pointer;
    }

    .login-card button.secondary {
        flex: 1;
        padding: 8px;
        border-radius: 999px;
        border: 1px solid #4b5563;
        background: transparent;
        color: #e5e7eb;
        font-weight: 500;
        font-size: 13px;
        cursor: pointer;
    }
    body.light .login-card button.secondary {
        border-color: #9ca3af;
        color: #111827;
    }

    .login-card button.link {
        border: none;
        background: transparent;
        color: #60a5fa;
        font-size: 12px;
        cursor: pointer;
        text-decoration: underline;
        margin-bottom: 4px;
    }

    .login-card .error {
        font-size: 12px;
        color: #f97373;
        min-height: 16px;
        margin-top: 4px;
    }

    .login-card .success {
        font-size: 12px;
        color: #22c55e;
        min-height: 16px;
        margin-top: 4px;
    }

    .otp-row {
        margin-top: 6px;
        border-top: 1px solid #111827;
        padding-top: 6px;
    }
    body.light .otp-row {
        border-top-color: #e5e7eb;
    }

    /* Markdown tables (base) */
    table {
        border-collapse: collapse;
        width: 100%;
        margin-top: 6px;
        font-size: 13px;
        background: #020617;
    }
    body.light table {
        background: #ffffff;
    }
    th, td {
        border: 1px solid #1f2933;
        padding: 6px;
    }
    body.light th, body.light td {
        border-color: #d1d5db;
    }
    th {
        background: #111827;
        font-weight: 600;
    }
    body.light th {
        background: #e5e7eb;
    }

    /* IMPROVED MARKDOWN INSIDE CHAT BUBBLES */
    .msg-bubble h1,
    .msg-bubble h2,
    .msg-bubble h3,
    .msg-bubble h4,
    .msg-bubble h5,
    .msg-bubble h6 {
        font-size: 15px;
        font-weight: 600;
        margin: 6px 0;
        color: inherit;
    }

    .msg-bubble p {
        margin: 6px 0;
    }

    .msg-bubble ul,
    .msg-bubble ol {
        margin: 6px 0 6px 18px;
    }

    .msg-bubble li {
        margin: 3px 0;
    }

    .msg-bubble table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 6px;
        background: transparent;
        font-size: 14px;
    }

    .msg-bubble th,
    .msg-bubble td {
        border: 1px solid #444;
        padding: 6px 8px;
    }

    .msg-bubble th {
        background: #1e1e22;
        font-weight: 600;
    }

    body.light .msg-bubble th {
        background: #e5e7eb;
    }

    .msg-bubble code {
        background: #1e1e22;
        padding: 3px 5px;
        border-radius: 4px;
        font-size: 13px;
        font-family: "Consolas", monospace;
    }

    body.light .msg-bubble code {
        background: #d1d5db;
    }

    .msg-bubble pre {
        background: #111827;
        border-radius: 8px;
        padding: 10px;
        overflow-x: auto;
        white-space: pre-wrap;
        margin: 10px 0;
        border: 1px solid #374151;
        font-size: 13px;
        position: relative;
    }

    body.light .msg-bubble pre {
        background: #f3f4f6;
        border-color: #d1d5db;
    }

    .copy-btn {
        position: absolute;
        top: 6px;
        right: 6px;
        font-size: 11px;
        padding: 3px 8px;
        border-radius: 999px;
        border: none;
        background: #374151;
        color: #e5e7eb;
        cursor: pointer;
        opacity: 0.8;
    }
    .copy-btn:hover {
        opacity: 1;
    }
    body.light .copy-btn {
        background: #e5e7eb;
        color: #111827;
    }

    /* RESPONSIVE */
    @media (max-width: 860px) {
        .sidebar {
            display: none;
        }
    }
</style>
</head>
<body>

<div class="app">

    <!-- SIDEBAR -->
    <aside class="sidebar">
        <div class="sidebar-header">
            <div class="logo-text">GURMAN AI</div>
        </div>
        <button class="new-chat-btn" onclick="createNewChat()">
            <span class="icon">+</span>
            <span>New chat</span>
        </button>
        <div class="chat-list-title">Chats</div>
        <div class="chat-list" id="chatList"></div>
        <div class="sidebar-footer">
            <div style="font-size:11px;">User: <span id="sideUserLabel">Guest</span></div>
            <button onclick="logoutUser()">Logout</button>
        </div>
    </aside>

    <!-- MAIN AREA -->
    <main class="main">
        <div class="top-bar">
            <div class="top-bar-title" id="topTitle">New chat</div>
            <div class="top-bar-right">
                <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">Light</button>
                <button class="theme-toggle" id="voiceBtn" onclick="toggleVoiceOutput()">🔊</button>
                <div class="top-bar-user">User: <span id="topUserLabel">Guest</span></div>
            </div>
        </div>

        <div class="content">
            <div class="chat-box" id="chatBox"></div>
            <div id="typing">GURMAN AI is typing...</div>
        </div>

        <div class="input-area">
            <div class="input-inner">
                <button id="micBtn" onclick="toggleVoiceInput()">🎤</button>
                <button id="regenBtn" onclick="regenerate()">↻</button>
                <input id="message" placeholder="Send a message..." onkeypress="checkEnter(event)">
                <button id="sendBtn" onclick="sendMessage()">➤</button>
            </div>
        </div>
    </main>

    <!-- LOGIN OVERLAY -->
    <div class="login-overlay" id="loginOverlay">
        <div class="login-card">
            <h2>Welcome to GURMAN AI</h2>
            <p>Sign in or create an account to start chatting.</p>
            <input id="username" placeholder="Username">
            <input id="email" placeholder="Email (for register)">
            <input id="password" type="password" placeholder="Password">

            <div class="login-row-btns">
                <button class="secondary" onclick="registerUser()">Register</button>
                <button class="primary" onclick="loginUser()">Sign in</button>
            </div>

            <button class="link" onclick="sendOtp()">Forgot password? Send OTP</button>

            <div class="otp-row">
                <input id="otpInput" placeholder="Enter OTP">
                <input id="newPassword" type="password" placeholder="New password">
                <button class="secondary" style="margin-top:4px;" onclick="resetPassword()">Reset password</button>
            </div>

            <div id="loginMessage" class="error"></div>
        </div>
    </div>

</div>

<script>
let recognition = null;
let recognizing = false;
let currentUser = null;
let currentChatId = null;
let chats = []; // {chat_id,title,messages:[{role,html}]}
let voiceEnabled = true;

/* ---------- THEME ---------- */
function initTheme() {
    const saved = localStorage.getItem("gurman_theme") || "dark";
    if (saved === "light") {
        document.body.classList.add("light");
        document.getElementById("themeBtn").innerText = "Dark";
    } else {
        document.body.classList.remove("light");
        document.getElementById("themeBtn").innerText = "Light";
    }
}
function toggleTheme() {
    document.body.classList.toggle("light");
    const light = document.body.classList.contains("light");
    localStorage.setItem("gurman_theme", light ? "light" : "dark");
    document.getElementById("themeBtn").innerText = light ? "Dark" : "Light";
}

/* ---------- VOICE OUTPUT ---------- */
function toggleVoiceOutput() {
    voiceEnabled = !voiceEnabled;
    const btn = document.getElementById("voiceBtn");
    btn.textContent = voiceEnabled ? "🔊" : "🔇";
    if (!voiceEnabled && window.speechSynthesis) {
        speechSynthesis.cancel();
    }
}
function stripHtml(htmlStr) {
    const tmp = document.createElement("div");
    tmp.innerHTML = htmlStr;
    return tmp.textContent || tmp.innerText || "";
}
function speakText(text) {
    if (!voiceEnabled) return;
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1;
    utter.pitch = 1;
    speechSynthesis.speak(utter);
}

/* ---------- CHATS (DB-SYNCED) ---------- */
function renderChatList() {
    const box = document.getElementById("chatList");
    box.innerHTML = "";
    chats.forEach(c => {
        const div = document.createElement("div");
        div.className = "chat-item" + (c.chat_id === currentChatId ? " active" : "");
        div.dataset.id = c.chat_id;

        const left = document.createElement("div");
        left.className = "left-part";
        const dot = document.createElement("span");
        dot.className = "dot";
        const title = document.createElement("span");
        title.className = "title";
        title.innerText = c.title || "New chat";
        left.appendChild(dot);
        left.appendChild(title);

        const actions = document.createElement("div");
        actions.className = "actions";
        const rn = document.createElement("button");
        rn.className = "rename-btn";
        rn.innerText = "✏";
        rn.onclick = (e)=>renameChat(e, c.chat_id);
        const del = document.createElement("button");
        del.className = "delete-btn";
        del.innerText = "🗑";
        del.onclick = (e)=>deleteChat(e, c.chat_id);
        actions.appendChild(rn);
        actions.appendChild(del);

        div.appendChild(left);
        div.appendChild(actions);
        div.onclick = ()=>selectChat(c.chat_id);

        box.appendChild(div);
    });
}

function selectChat(id) {
    currentChatId = id;
    const chat = chats.find(c => c.chat_id === id);
    renderChatList();
    renderMessages(chat ? chat.messages : []);
    document.getElementById("topTitle").innerText = chat ? chat.title : "New chat";
}

function renderMessages(msgs) {
    const box = document.getElementById("chatBox");
    box.innerHTML = "";
    msgs.forEach(m => {
        appendMessageToUI(m.role, m.html, false);
    });
    box.scrollTop = box.scrollHeight;
}

function createNewChat() {
    if (!currentUser) {
        alert("Please sign in first.");
        return;
    }
    const tempId = Date.now().toString();
    fetch("/chats/create", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({chat_id: tempId, title: "New chat"})
    })
    .then(r=>r.json())
    .then(d=>{
        if (!d.success) return;
        chats.unshift({chat_id: tempId, title:"New chat", messages:[]});
        currentChatId = tempId;
        renderChatList();
        renderMessages([]);
        document.getElementById("topTitle").innerText = "New chat";
    });
}

function renameChat(event, id) {
    event.stopPropagation();
    const idx = chats.findIndex(c => c.chat_id === id);
    if (idx === -1) return;
    const currentTitle = chats[idx].title || "New chat";
    const newTitle = prompt("Rename chat:", currentTitle);
    if (!newTitle) return;
    const finalTitle = newTitle.slice(0, 60);

    fetch("/chats/rename", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({chat_id:id, title:finalTitle})
    })
    .then(r=>r.json())
    .then(d=>{
        if (!d.success) return;
        chats[idx].title = finalTitle;
        renderChatList();
        if (currentChatId === id) {
            document.getElementById("topTitle").innerText = finalTitle;
        }
    });
}

function deleteChat(event, id) {
    event.stopPropagation();
    if (!confirm("Delete this chat permanently?")) return;

    fetch("/chats/delete", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({chat_id:id})
    })
    .then(r=>r.json())
    .then(d=>{
        if (!d.success) return;
        chats = chats.filter(c => c.chat_id !== id);
        if (chats.length === 0) {
            currentChatId = null;
            document.getElementById("chatBox").innerHTML = "";
            document.getElementById("topTitle").innerText = "New chat";
        } else {
            currentChatId = chats[0].chat_id;
        }
        renderChatList();
        const active = chats.find(c => c.chat_id === currentChatId);
        renderMessages(active ? active.messages : []);
    });
}

function syncChatsFromServer() {
    fetch("/chats-sync")
    .then(r=>{
        if (r.status === 401) return null;
        return r.json();
    })
    .then(data=>{
        if (!data) return;
        chats = data.chats || [];
        if (chats.length > 0) {
            currentChatId = chats[0].chat_id;
            renderChatList();
            renderMessages(chats[0].messages);
            document.getElementById("topTitle").innerText = chats[0].title || "New chat";
        } else {
            currentChatId = null;
            document.getElementById("chatBox").innerHTML = "";
            document.getElementById("topTitle").innerText = "New chat";
        }
    });
}

/* ---------- AUTH ---------- */
function registerUser() {
    const u = username.value.trim();
    const e = email.value.trim();
    const p = password.value;
    const msg = document.getElementById("loginMessage");
    msg.className = "error";
    msg.innerText = "";

    if (!u || !e || !p) {
        msg.innerText = "Fill username, email and password.";
        return;
    }

    fetch("/register", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({username:u,email:e,password:p})
    })
    .then(r=>r.json())
    .then(d=>{
        if (d.success) {
            msg.className = "success";
            msg.innerText = d.message;
        } else {
            msg.className = "error";
            msg.innerText = d.message;
        }
    });
}

function loginUser() {
    const u = username.value.trim();
    const p = password.value;
    const msg = document.getElementById("loginMessage");
    msg.className = "error";
    msg.innerText = "";

    if (!u || !p) {
        msg.innerText = "Enter username and password.";
        return;
    }

    fetch("/login", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({username:u,password:p})
    })
    .then(r=>r.json())
    .then(d=>{
        if (d.success) {
            currentUser = u;
            document.getElementById("sideUserLabel").innerText = u;
            document.getElementById("topUserLabel").innerText = u;
            document.getElementById("loginOverlay").style.display = "none";
            syncChatsFromServer();
        } else {
            msg.className = "error";
            msg.innerText = d.message;
        }
    });
}

function logoutUser() {
    fetch("/logout", {method:"POST"})
    .then(()=>{
        currentUser = null;
        chats = [];
        currentChatId = null;
        document.getElementById("chatBox").innerHTML = "";
        document.getElementById("chatList").innerHTML = "";
        document.getElementById("loginOverlay").style.display = "flex";
        document.getElementById("sideUserLabel").innerText = "Guest";
        document.getElementById("topUserLabel").innerText = "Guest";
        document.getElementById("topTitle").innerText = "New chat";
    });
}

/* Forgot password */
function sendOtp() {
    const u = username.value.trim();
    const msg = document.getElementById("loginMessage");
    msg.className = "error";
    msg.innerText = "";
    if (!u) {
        msg.innerText = "Enter username to send OTP.";
        return;
    }
    fetch("/forgot-request", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({username:u})
    })
    .then(r=>r.json())
    .then(d=>{
        if (d.success) {
            msg.className = "success";
            msg.innerText = d.message + " (check email / server console)";
        } else {
            msg.className = "error";
            msg.innerText = d.message;
        }
    });
}

function resetPassword() {
    const u = username.value.trim();
    const otp = otpInput.value.trim();
    const np = newPassword.value;
    const msg = document.getElementById("loginMessage");
    msg.className = "error";
    msg.innerText = "";

    if (!u || !otp || !np) {
        msg.innerText = "Enter username, OTP and new password.";
        return;
    }
    fetch("/forgot-reset", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({username:u,otp:otp,new_password:np})
    })
    .then(r=>r.json())
    .then(d=>{
        if (d.success) {
            msg.className = "success";
            msg.innerText = d.message;
        } else {
            msg.className = "error";
            msg.innerText = d.message;
        }
    });
}

/* ---------- Chat / AI ---------- */
function checkEnter(e) {
    if (e.key === "Enter") sendMessage();
}

function appendMessageToUI(role, html, scroll=true) {
    const box = document.getElementById("chatBox");
    const row = document.createElement("div");
    row.className = "msg-row " + (role === "user" ? "user-row" : "bot-row");
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.innerHTML = html;
    row.appendChild(bubble);
    box.appendChild(row);
    if (scroll) box.scrollTop = box.scrollHeight;
    if (role === "bot") enhanceCodeBlocks(bubble);
}

function streamBotMessage(botHtml) {
    const box = document.getElementById("chatBox");
    const row = document.createElement("div");
    row.className = "msg-row bot-row";
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    row.appendChild(bubble);
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;

    const plain = stripHtml(botHtml);
    let i = 0;
    const speed = 15;

    const interval = setInterval(()=>{
        bubble.textContent = plain.slice(0, i);
        box.scrollTop = box.scrollHeight;
        i++;
        if (i > plain.length) {
            clearInterval(interval);
            bubble.innerHTML = botHtml;
            enhanceCodeBlocks(bubble);
            speakText(plain);
        }
    }, speed);
}

function sendMessage() {
    if (!currentUser) {
        alert("Please sign in first.");
        return;
    }
    if (!currentChatId) {
        createNewChat();
        if (!currentChatId) return;
    }

    const input = document.getElementById("message");
    const msg = input.value.trim();
    if (!msg) return;

    const safe = msg.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    appendMessageToUI("user", safe);
    const chat = chats.find(c => c.chat_id === currentChatId);
    if (chat) {
        chat.messages.push({role:"user", html:safe});
    }

    if (chat && (!chat.title || chat.title === "New chat")) {
        const newTitle = msg.length > 30 ? msg.slice(0,27)+"..." : msg;
        chat.title = newTitle;
        fetch("/chats/rename", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({chat_id:currentChatId, title:newTitle})
        });
        renderChatList();
        document.getElementById("topTitle").innerText = newTitle;
    }

    input.value = "";
    document.getElementById("typing").style.display = "block";

    fetch("/ask", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({message:msg, chat_id:currentChatId})
    })
    .then(res=>{
        if (res.status === 401) {
            alert("Session expired. Please login again.");
            logoutUser();
            return null;
        }
        return res.json();
    })
    .then(data=>{
        if (!data) return;
        document.getElementById("typing").style.display = "none";
        const botHtml = data.reply;
        streamBotMessage(botHtml);
        const chat2 = chats.find(c => c.chat_id === currentChatId);
        if (chat2) {
            chat2.messages.push({role:"bot", html:botHtml});
        }
    });
}

/* ---------- Regenerate Last Answer ---------- */
function regenerate() {
    if (!currentUser || !currentChatId) {
        alert("No chat to regenerate.");
        return;
    }
    const chat = chats.find(c => c.chat_id === currentChatId);
    if (!chat || !chat.messages.length) {
        alert("No messages to regenerate.");
        return;
    }
    document.getElementById("typing").style.display = "block";

    fetch("/regenerate", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({chat_id:currentChatId})
    })
    .then(res=>{
        if (res.status === 401) {
            alert("Session expired. Please login again.");
            logoutUser();
            return null;
        }
        return res.json();
    })
    .then(data=>{
        if (!data) return;
        document.getElementById("typing").style.display = "none";
        const botHtml = data.reply;
        streamBotMessage(botHtml);
        const chat2 = chats.find(c => c.chat_id === currentChatId);
        if (chat2) {
            chat2.messages.push({role:"bot", html:botHtml});
        }
    });
}

/* ---------- Enhance code blocks with copy button ---------- */
function enhanceCodeBlocks(container) {
    const pres = container.querySelectorAll("pre");
    pres.forEach(pre => {
        if (pre.dataset.enhanced === "1") return;
        pre.dataset.enhanced = "1";

        const btn = document.createElement("button");
        btn.className = "copy-btn";
        btn.textContent = "Copy";
        btn.onclick = () => {
            const text = pre.innerText;
            navigator.clipboard.writeText(text).then(()=>{
                btn.textContent = "Copied!";
                setTimeout(()=>btn.textContent="Copy", 1000);
            });
        };
        pre.appendChild(btn);
    });
}

/* ---------- Voice Input ---------- */
function toggleVoiceInput() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        alert("Voice recognition not supported in this browser.");
        return;
    }
    if (!recognition) {
        recognition = new SR();
        recognition.lang = "en-US";
        recognition.onresult = (e)=>{
            const text = e.results[0][0].transcript;
            document.getElementById("message").value = text;
            sendMessage();
        };
        recognition.onend = ()=>{
            recognizing = false;
            document.getElementById("micBtn").classList.remove("listening");
        };
    }
    if (!recognizing) {
        recognizing = true;
        document.getElementById("micBtn").classList.add("listening");
        recognition.start();
    } else {
        recognizing = false;
        document.getElementById("micBtn").classList.remove("listening");
        recognition.stop();
    }
}

window.onload = initTheme;
</script>

</body>
</html>
"""

# ---------------- BACKEND ROUTES ----------------
@app.route("/")
def home():
    return render_template_string(html_code)


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not username or not email or not password:
        return jsonify(success=False, message="All fields are required.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify(success=False, message="Username already exists.")

    pw_hash = generate_password_hash(password)
    cur.execute(
        "INSERT INTO users (username,email,password_hash) VALUES (?,?,?)",
        (username, email, pw_hash),
    )
    conn.commit()
    conn.close()
    return jsonify(success=True, message="Registered successfully. Please sign in.")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify(success=False, message="User not found.")
    user_id, pw_hash = row
    if not check_password_hash(pw_hash, password):
        return jsonify(success=False, message="Incorrect password.")

    session["user"] = username
    session["user_id"] = user_id
    chat_sessions[username] = {}
    return jsonify(success=True, message="Login successful.")


@app.route("/logout", methods=["POST"])
def logout():
    user = session.pop("user", None)
    session.pop("user_id", None)
    if user and user in chat_sessions:
        del chat_sessions[user]
    return jsonify(success=True)


@app.route("/forgot-request", methods=["POST"])
def forgot_request():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()

    if not username:
        return jsonify(success=False, message="Username required.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT email FROM users WHERE username=?", (username,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify(success=False, message="User not found.")

    email = row[0]
    otp = f"{secrets.randbelow(1000000):06d}"
    expire = int(time.time()) + 600  # 10 min
    cur.execute(
        "UPDATE users SET reset_otp=?, reset_expire=? WHERE username=?",
        (otp, expire, username),
    )
    conn.commit()
    conn.close()

    send_otp_email(email, username, otp)

    return jsonify(success=True, message="OTP sent. (Check email or console in dev.)")


@app.route("/forgot-reset", methods=["POST"])
def forgot_reset():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    otp = (data.get("otp") or "").strip()
    new_password = data.get("new_password") or ""

    if not username or not otp or not new_password:
        return jsonify(success=False, message="All fields required.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT reset_otp, reset_expire FROM users WHERE username=?",
        (username,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return jsonify(success=False, message="No OTP set. Request again.")

    saved_otp, expire = row
    now = int(time.time())
    if now > (expire or 0):
        conn.close()
        return jsonify(success=False, message="OTP expired. Request a new one.")

    if otp != saved_otp:
        conn.close()
        return jsonify(success=False, message="Invalid OTP.")

    pw_hash = generate_password_hash(new_password)
    cur.execute(
        "UPDATE users SET password_hash=?, reset_otp=NULL, reset_expire=NULL WHERE username=?",
        (pw_hash, username),
    )
    conn.commit()
    conn.close()
    return jsonify(success=True, message="Password reset successfully. Please sign in.")


@app.route("/chats-sync", methods=["GET"])
def chats_sync():
    if "user" not in session or "user_id" not in session:
        return jsonify(error="Not logged in"), 401
    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chat_key, title FROM chats WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    result = []
    for chat_key, title in rows:
        cur.execute(
            "SELECT role, content FROM messages WHERE user_id=? AND chat_key=? ORDER BY created_at ASC, id ASC",
            (user_id, chat_key),
        )
        msgs = []
        for role, content in cur.fetchall():
            if role == "bot":
                html_content = markdown(content)
            else:
                html_content = html.escape(content)
            msgs.append({"role": role, "html": html_content})
        result.append({"chat_id": chat_key, "title": title, "messages": msgs})
    conn.close()
    return jsonify(chats=result)


@app.route("/chats/create", methods=["POST"])
def chats_create():
    if "user" not in session or "user_id" not in session:
        return jsonify(success=False, message="Not logged in"), 401
    data = request.get_json() or {}
    chat_id = data.get("chat_id")
    title = data.get("title") or "New chat"
    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chats (user_id, chat_key, title, created_at) VALUES (?,?,?,?)",
        (user_id, chat_id, title, int(time.time())),
    )
    conn.commit()
    conn.close()
    return jsonify(success=True)


@app.route("/chats/rename", methods=["POST"])
def chats_rename():
    if "user" not in session or "user_id" not in session:
        return jsonify(success=False, message="Not logged in"), 401
    data = request.get_json() or {}
    chat_id = data.get("chat_id")
    title = (data.get("title") or "New chat").strip()
    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE chats SET title=? WHERE user_id=? AND chat_key=?",
        (title, user_id, chat_id),
    )
    conn.commit()
    conn.close()
    return jsonify(success=True)


@app.route("/chats/delete", methods=["POST"])
def chats_delete():
    if "user" not in session or "user_id" not in session:
        return jsonify(success=False, message="Not logged in"), 401
    data = request.get_json() or {}
    chat_id = data.get("chat_id")
    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE user_id=? AND chat_key=?", (user_id, chat_id))
    cur.execute("DELETE FROM chats WHERE user_id=? AND chat_key=?", (user_id, chat_id))
    conn.commit()
    conn.close()
    username = session["user"]
    if username in chat_sessions and chat_id in chat_sessions[username]:
        del chat_sessions[username][chat_id]
    return jsonify(success=True)


@app.route("/ask", methods=["POST"])
def ask():
    if "user" not in session or "user_id" not in session:
        return jsonify(error="Not logged in"), 401
    data = request.get_json() or {}
    user_msg = data.get("message", "")
    chat_id = data.get("chat_id", "default")
    username = session["user"]
    user_id = session["user_id"]

    user_chats = chat_sessions.setdefault(username, {})
    chat = user_chats.get(chat_id)
    if chat is None:
        chat = model.start_chat(history=[])
        user_chats[chat_id] = chat

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (user_id, chat_key, role, content, created_at) VALUES (?,?,?,?,?)",
        (user_id, chat_id, "user", user_msg, int(time.time())),
    )
    conn.commit()

    response = chat.send_message(user_msg)
    bot_text = response.text

    cur.execute(
        "INSERT INTO messages (user_id, chat_key, role, content, created_at) VALUES (?,?,?,?,?)",
        (user_id, chat_id, "bot", bot_text, int(time.time())),
    )
    conn.commit()
    conn.close()

    html_resp = markdown(bot_text)
    return jsonify(reply=html_resp)


@app.route("/regenerate", methods=["POST"])
def regenerate():
    if "user" not in session or "user_id" not in session:
        return jsonify(error="Not logged in"), 401
    data = request.get_json() or {}
    chat_id = data.get("chat_id", "default")
    username = session["user"]
    user_id = session["user_id"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM messages WHERE user_id=? AND chat_key=? ORDER BY created_at ASC, id ASC",
        (user_id, chat_id),
    )
    rows = cur.fetchall()
    if not rows:
        conn.close()
        return jsonify(error="No messages found"), 400

    last_user_index = -1
    for i, (role, _) in enumerate(rows):
        if role == "user":
            last_user_index = i
    if last_user_index == -1:
        conn.close()
        return jsonify(error="No user message to regenerate"), 400

    history = []
    for i in range(last_user_index):
        role, content = rows[i]
        if role == "user":
            hist_role = "user"
        else:
            hist_role = "model"
        history.append({"role": hist_role, "parts": [content]})
    last_user_msg = rows[last_user_index][1]

    chat = model.start_chat(history=history)
    user_chats = chat_sessions.setdefault(username, {})
    user_chats[chat_id] = chat

    response = chat.send_message(last_user_msg)
    bot_text = response.text

    cur.execute(
        "INSERT INTO messages (user_id, chat_key, role, content, created_at) VALUES (?,?,?,?,?)",
        (user_id, chat_id, "bot", bot_text, int(time.time())),
    )
    conn.commit()
    conn.close()

    html_resp = markdown(bot_text)
    return jsonify(reply=html_resp)


if __name__ == "__main__":
    print("\\n🔥 GURMAN AI READY → http://127.0.0.1:5000\\n")
    app.run(debug=True)
