import streamlit as st
import psycopg2
from psycopg2 import IntegrityError
import hashlib
import smtplib
import math
import cloudinary
import cloudinary.uploader
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, date

# --- CONFIGURATION & SECRETS ---
st.set_page_config(page_title="UniUyo Academic Hub", page_icon="🎓", layout="wide")

# PUT YOUR REAL EMAIL AND 16-LETTER GOOGLE APP PASSWORD HERE
SENDER_EMAIL = "capzi01c@gmail.com"
EMAIL_PASS = st.secrets["EMAIL_PASS"]
ADMIN_USERNAME = "caleb"

DB_URL = st.secrets["DB_URL"]

cloudinary.config(
    cloud_name="dycllasey",
    api_key="582982192356838",
    api_secret="qReAT87xhDkf9OLvvTT6CgDcRgk",
    secure=True
)


# --- DATABASE SETUP ---
def get_connection():
    return psycopg2.connect(DB_URL)


@st.cache_resource
def initialize_db_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT, department TEXT, usage_count INTEGER DEFAULT 0, profile_pic_url TEXT, points INTEGER DEFAULT 0)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS discussions (id SERIAL PRIMARY KEY, author TEXT, author_dept TEXT, visibility TEXT, content TEXT, is_anonymous INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, voice_note_url TEXT)''')

    try:
        c.execute('ALTER TABLE discussions ADD COLUMN IF NOT EXISTS voice_note_url TEXT')
        conn.commit()
    except Exception:
        conn.rollback()

    try:
        c.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0')
        conn.commit()
    except Exception:
        conn.rollback()

    c.execute(
        '''CREATE TABLE IF NOT EXISTS announcements (id SERIAL PRIMARY KEY, author TEXT, visibility TEXT, target_dept TEXT, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS likes (id SERIAL PRIMARY KEY, post_type TEXT, post_id INTEGER, username TEXT, UNIQUE(post_type, post_id, username))''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS replies (id SERIAL PRIMARY KEY, post_type TEXT, post_id INTEGER, author TEXT, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, username TEXT, email TEXT, description TEXT, deadline TIMESTAMP, reminded_2d INTEGER DEFAULT 0, reminded_1d INTEGER DEFAULT 0, reminded_0d INTEGER DEFAULT 0)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS course_grades (id SERIAL PRIMARY KEY, username TEXT, course_code TEXT, grade TEXT, credit INTEGER)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS study_resources (id SERIAL PRIMARY KEY, uploader TEXT, uploader_dept TEXT, title TEXT, file_name TEXT, file_url TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS study_groups (id SERIAL PRIMARY KEY, creator TEXT, department TEXT, group_name TEXT, description TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS group_members (id SERIAL PRIMARY KEY, group_id INTEGER, username TEXT, UNIQUE(group_id, username))''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS exams (id SERIAL PRIMARY KEY, username TEXT, course_code TEXT, exam_date DATE)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS opportunities (id SERIAL PRIMARY KEY, title TEXT, category TEXT, description TEXT, link TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS brain_games (id SERIAL PRIMARY KEY, title TEXT, category TEXT, question TEXT, correct_answer TEXT, points INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute(
        '''CREATE TABLE IF NOT EXISTS game_submissions (id SERIAL PRIMARY KEY, game_id INTEGER, username TEXT, is_correct INTEGER, UNIQUE(game_id, username))''')

    # NEW: Study Group Workspace Chat & File Sharing Table
    c.execute(
        '''CREATE TABLE IF NOT EXISTS group_messages (id SERIAL PRIMARY KEY, group_id INTEGER, author TEXT, content TEXT, file_url TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    conn.commit()
    conn.close()
    return True


# --- HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def truncate_gpa(value):
    return math.floor(value * 100) / 100.0


def calculate_points(grade, credit):
    grade_map = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1, 'F': 0}
    return grade_map.get(grade.upper(), 0) * credit


def get_class_of_degree(cgpa):
    if cgpa >= 4.50:
        return "First Class", "🥇", "success"
    elif cgpa >= 3.50:
        return "Second Class Upper", "🥈", "success"
    elif cgpa >= 2.40:
        return "Second Class Lower", "🥉", "info"
    elif cgpa >= 1.50:
        return "Third Class", "📜", "warning"
    else:
        return "Pass / Probation", "⚠️", "error"


def get_profile_img_src(url):
    if url: return url
    return "data:image/jpeg;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


# --- EMAIL & NOTIFICATIONS LOGIC ---
def send_uni_email(receiver_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = f"UniUyo Academic Hub <{SENDER_EMAIL}>"
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email failed: Ensure SENDER_EMAIL and SENDER_PASSWORD (16-char App Password) are correct. Error: {e}")
        return False


def get_target_emails(visibility, department=None):
    conn = get_connection()
    c = conn.cursor()
    if visibility == "General":
        c.execute('SELECT email FROM users')
    else:
        c.execute('SELECT email FROM users WHERE department = %s', (department,))
    emails = [row[0] for row in c.fetchall()]
    conn.close()
    return emails


def notify_mass_audience(visibility, department, subject, body):
    emails = get_target_emails(visibility, department)
    for email in emails: send_uni_email(email, subject, body)


@st.cache_data(ttl=300)
def check_task_reminders(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        'SELECT id, email, description, deadline, reminded_2d, reminded_1d, reminded_0d FROM tasks WHERE username = %s',
        (username,))
    tasks = c.fetchall()
    now = datetime.now()
    for task in tasks:
        task_id, email, desc, deadline, r_2d, r_1d, r_0d = task
        time_left = deadline - now
        if timedelta(days=1) < time_left <= timedelta(days=2) and not r_2d:
            send_uni_email(email, "Task Reminder: 2 Days Left!", f"Reminder: '{desc}' is due in 2 days on {deadline}.")
            c.execute('UPDATE tasks SET reminded_2d = 1 WHERE id = %s', (task_id,))
        elif timedelta(hours=0) < time_left <= timedelta(days=1) and not r_1d:
            send_uni_email(email, "Task Reminder: 1 Day Left!", f"Urgent: '{desc}' is due tomorrow at {deadline}.")
            c.execute('UPDATE tasks SET reminded_1d = 1 WHERE id = %s', (task_id,))
        elif time_left <= timedelta(hours=0) and not r_0d:
            send_uni_email(email, "Task Deadline Reached!",
                           f"Alert: The deadline for '{desc}' is right now ({deadline}).")
            c.execute('UPDATE tasks SET reminded_0d = 1 WHERE id = %s', (task_id,))
    conn.commit()
    conn.close()


# --- DATABASE OPERATIONS ---
def get_user_cgpa(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT grade, credit FROM course_grades WHERE username = %s', (username,))
    courses = c.fetchall()
    conn.close()
    if not courses: return 0.00
    total_points = sum(calculate_points(g, c) for g, c in courses)
    total_credits = sum(c for g, c in courses)
    if total_credits == 0: return 0.00
    return truncate_gpa(total_points / total_credits)


def get_user_pic_url(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT profile_pic_url FROM users WHERE username = %s', (username,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None


# --- PREMIUM CSS STYLING ---
def local_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        .stApp { background: linear-gradient(135deg, #11151c 0%, #1e2532 100%); color: #f1f5f9; }
        [data-testid="stSidebar"] { background-color: rgba(15, 23, 42, 0.95); border-right: 1px solid rgba(255, 255, 255, 0.05); }
        h1, h2, h3, h4, h5, h6, p, label, span { color: #f1f5f9 !important; }

        .stButton>button, .stDownloadButton>button {
            border-radius: 6px !important; background-color: #1ABC9C !important; color: #ffffff !important;
            border: none !important; font-weight: 600 !important; padding: 0.5rem 1rem !important; transition: all 0.2s ease-in-out !important;
        }
        .stButton>button:hover, .stDownloadButton>button:hover { background-color: #16a085 !important; transform: translateY(-2px); }

        .stTextInput>div>div>input, .stSelectbox>div>div>div, .stTextArea>div>div>textarea, .stNumberInput>div>div>input {
            background-color: rgba(255, 255, 255, 0.05) !important; color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important; border-radius: 6px !important;
        }
        .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus { border-color: #1ABC9C !important; box-shadow: 0 0 0 1px #1ABC9C !important; }

        .post-box, [data-testid="stForm"], .opp-box {
            background-color: rgba(30, 41, 59, 0.7) !important; backdrop-filter: blur(12px); padding: 20px;
            border-radius: 12px; margin-bottom: 20px; border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .opp-box { border-left: 5px solid #1ABC9C !important; }

        .profile-img { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; vertical-align: middle; margin-right: 15px; border: 2px solid #1ABC9C; }
        .post-header { display: flex; align-items: center; margin-bottom: 15px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); padding-bottom: 10px; }
        .timestamp { font-size: 0.85em; color: #94a3b8 !important; }

        .tag-badge { background-color: rgba(26, 188, 156, 0.15); color: #1ABC9C !important; padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; margin-left: 10px; border: 1px solid rgba(26, 188, 156, 0.3); }
        .medal-badge { font-size: 1.5em; vertical-align: middle; margin-right: 10px; }

        .stAlert { background-color: rgba(30, 41, 59, 0.8) !important; border: 1px solid rgba(255, 255, 255, 0.08) !important; color: #f1f5f9 !important; }
        .streamlit-expanderHeader { background-color: rgba(255, 255, 255, 0.03) !important; border-radius: 8px !important; color: #f1f5f9 !important; }

        /* Safe Anti-Dimming Hack */
        [data-testid="stAppViewContainer"],
        .stApp {
            filter: blur(0px) !important;
            opacity: 1 !important;
            transition: none !important;
        }
        </style>
    """, unsafe_allow_html=True)


# --- APP INITIALIZATION ---
try:
    initialize_db_tables()
except Exception as e:
    st.error(f"Database connection failed. Please check your DB_URL. Error: {e}")

local_css()
DEPTS_LIST = [
    "Accounting",
    "Actuarial Science",
    "Agriculture",
    "Agricultural Economics And Extension",
    "Agricultural Engineering",
    "Agricultural Education",
    "Agronomy",
    "Agro Forestry",
    "Animal Science",
    "Animal and Environmental Biology",
    "Anatomy",
    "Architecture",
    "Banking And Finance",
    "Biochemistry",
    "Biology",
    "Botany And Ecological Studies",
    "Brewing Science And Technology",
    "Building",
    "Business Administration",
    "Business Management",
    "Business Education",
    "Chemical Engineering",
    "Chemistry",
    "Civil Engineering",
    "Communication Arts",
    "Computer Engineering",
    "Computer Science",
    "Computer Education",
    "Crop Science",
    "Curriculum Studies Educational Mgt. And Planning",
    "Dentistry And Dental Surgery",
    "Early Childhood And Special Education",
    "Economics",
    "Educational Foundation",
    "Educational Technology",
    "Electrical/Electronics Engineering",
    "English",
    "Environmental Health Management",
    "Environmental Management",
    "Environmental Management And Conservation",
    "Estate Management",
    "Fine And Industrial Arts",
    "Fisheries And Aquaculture",
    "Fisheries And Aquatic Environment Management",
    "Food Engineering",
    "Food Science And Technology",
    "Foreign Languages",
    "Forestry And Wildlife",
    "French",
    "Geography And Regional Planning",
    "Geoinformatics And Surveying",
    "Geology",
    "Geophysics",
    "Guidance and Counseling",
    "Health Education",
    "History And International Studies",
    "Home Economics",
    "Human Anatomy",
    "Human Nutrition and Dietetics",
    "Industrial Technology Education",
    "Insurance",
    "Institute Of Education",
    "Land Surveying And Geo-Informatics",
    "Law",
    "Library Science",
    "Linguistics And Nigerian Languages",
    "Efik-Ibibio",
    "Marketing",
    "Mass Communication",
    "Mathematics",
    "Mechanical Engineering",
    "Medical Laboratory Science",
    "Medical Microbiology And Parasitology",
    "Medicine And Surgery",
    "Microbiology",
    "Music",
    "Nursing / Nursing Science",
    "Petroleum Engineering",
    "Pharmacognosy And Natural Medicine",
    "Pharmacology And Toxicology",
    "Pharmacy",
    "Doctor of Pharmacy",
    "Philosophy",
    "Physical Education",
    "Physics",
    "Physiology",
    "Physiotherapy",
    "Political Science",
    "Psychology",
    "Quantity Surveying",
    "Radiography And Radiation Science",
    "Religious Cultural Studies",
    "Sociology And Anthropology",
    "Soil Science",
    "Special Education",
    "Statistics",
    "Technical Education",
    "Teacher Education Science",
    "Theatre Arts",
    "Urban And Regional Planning",
    "Vocational Education",
    "Waste Management Studies",
    "Zoology",
    "Education (Biology)",
    "Education (Chemistry)",
    "Education (Economics)",
    "Education (Efik / Ibibio)",
    "Education (English)",
    "Education (French)",
    "Education (Geography)",
    "Education (History)",
    "Education (Integrated Science)",
    "Education (Mathematics)",
    "Education (Music)",
    "Education (Physics)",
    "Education (Political Science)",
    "Education (Religious Studies)",
    "Education (Science)",
    "Education (Social Science)",
    "Education (Social Studies)",
    "Education (Fine Art)",
    "Pre-Primary and Primary Education",
    "Software Engineering"
]

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

# --- AUTHENTICATION UI ---
if not st.session_state['logged_in']:
    st.markdown(
        "<h1 style='text-align: center; color: #1ABC9C; font-weight: 800;'>🎓 UniUyo Academic Support System</h1>",
        unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8;'>Your all-in-one digital campus ecosystem.</p>",
                unsafe_allow_html=True)
    st.write("---")
    auth_mode = st.tabs(["🔐 Login", "📝 Sign Up"])

    with auth_mode[0]:
        with st.form("login_form"):
            st.subheader("Welcome Back")
            login_user = st.text_input("Username").strip()
            login_pw = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Access Dashboard", use_container_width=True)

            if submit_login:
                with st.spinner("Authenticating securely and fetching your profile..."):
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('SELECT * FROM users WHERE username = %s AND password = %s',
                              (login_user, hash_password(login_pw)))
                    user_data = c.fetchone()
                    if user_data:
                        c.execute('UPDATE users SET usage_count = usage_count + 1 WHERE username = %s', (login_user,))
                        conn.commit()
                        st.session_state['logged_in'] = True
                        st.session_state['user_info'] = user_data
                        st.success(f"Welcome back, {login_user}!")
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password. Did you create an account on the new database?")
                    conn.close()

    with auth_mode[1]:
        with st.form("signup_form"):
            st.subheader("Create New Account")
            new_user = st.text_input("Choose Username").strip()
            new_email = st.text_input("University Email").strip()
            new_dept = st.selectbox("Select Your Department", DEPTS_LIST)
            pic_upload = st.file_uploader("Upload Profile Picture (Optional)", type=['png', 'jpg', 'jpeg'])
            new_pw = st.text_input("Create Password", type="password")
            confirm_pw = st.text_input("Confirm Password", type="password")
            submit_signup = st.form_submit_button("Register & Join", use_container_width=True)

            if submit_signup:
                if new_pw != confirm_pw:
                    st.warning("Passwords do not match")
                elif not new_user or not new_email:
                    st.warning("Please fill in all fields")
                else:
                    with st.spinner("Creating your secure cloud account... Please wait."):
                        pic_url = None
                        if pic_upload:
                            try:
                                res = cloudinary.uploader.upload(pic_upload.read(), folder="uniuyo_hub/profiles")
                                pic_url = res['secure_url']
                            except Exception as e:
                                st.warning("Profile picture upload failed. Proceeding without picture...")

                        conn = get_connection()
                        try:
                            conn.cursor().execute(
                                'INSERT INTO users(username, email, password, department, usage_count, profile_pic_url) VALUES (%s,%s,%s,%s,%s,%s)',
                                (new_user, new_email, hash_password(new_pw), new_dept, 1, pic_url))
                            conn.commit()
                            st.success("Account created! You can now switch to the Login tab to access your dashboard.")
                            send_uni_email(new_email, "Welcome to UniUyo Academic Hub!",
                                           f"Hello {new_user},\n\nWelcome to the platform! We are thrilled to support your academic journey.")
                        except IntegrityError:
                            st.error("Username or Email already exists in the database.")
                        finally:
                            conn.close()

# --- MAIN APP (LOGGED IN) ---
else:
    user = st.session_state['user_info']
    username, user_email, user_dept = user[1], user[2], user[4]

    check_task_reminders(username)
    cgpa = get_user_cgpa(username)

    st.sidebar.title(f"Welcome, {username}")
    st.sidebar.write(f"📍 {user_dept}")

    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT points FROM users WHERE username = %s', (username,))
    my_points = c.fetchone()[0] or 0
    conn.close()

    st.sidebar.markdown(f"<span class='tag-badge'>🌟 {my_points} Brain Points</span>", unsafe_allow_html=True)
    st.sidebar.write("---")

    menu = ["Dashboard", "GPA/CGPA Tracker", "Brain Games 🧠", "Study Resources", "Discussions", "Announcements",
            "Exam Countdown", "Scholarships & Alerts", "Study Groups", "Task Manager", "About Me"]
    choice = st.sidebar.radio("Navigation Menu", menu)

    st.sidebar.write("---")
    if st.sidebar.button("Logout", use_container_width=True):
        with st.spinner("Logging out safely..."):
            st.session_state['logged_in'] = False
            st.rerun()

    if choice == "Dashboard":
        st.title("📊 Academic Dashboard")
        st.write("Overview of your academic progress and campus activity.")
        col1, col2, col3 = st.columns(3)
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM tasks WHERE username = %s AND reminded_0d = 0", (username,))
        pending_tasks = c.fetchone()[0]
        c.execute("SELECT usage_count FROM users WHERE username = %s", (username,))
        current_usage = c.fetchone()[0]

        deg_class, icon, _ = get_class_of_degree(cgpa)
        col1.metric("My App Usages", current_usage)
        col2.metric("Current CGPA", f"{cgpa:.2f}")
        col3.metric("Tasks Pending", pending_tasks)
        st.info(f"**Current Academic Standing:** {icon} {deg_class}")

        if username == ADMIN_USERNAME:
            st.write("---")
            st.subheader("👑 Admin Control Panel Statistics")
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT SUM(usage_count) FROM users")
            total_app_usages = c.fetchone()[0] or 0
            admin_col1, admin_col2 = st.columns(2)
            admin_col1.metric("Total Registered Students", total_users)
            admin_col2.metric("Total Platform Usages", total_app_usages)
        conn.close()

    elif choice == "Brain Games 🧠":
        st.title("🧠 Daily Brain Games & Leaderboard")
        st.write(
            "Race to solve daily logic puzzles, coding challenges, and math problems. Only the first 4 correct answers get points!")

        tab1, tab2 = st.tabs(["🎮 Play & Earn Points", "🏆 Global Leaderboard"])

        with tab1:
            if username == ADMIN_USERNAME:
                with st.expander("🛠️ Admin: Post New Brain Game"):
                    g_title = st.text_input("Game Title")
                    g_cat = st.selectbox("Category",
                                         ["Logic Puzzle", "Coding Challenge", "Math Problem", "Brain Teaser"])
                    g_q = st.text_area("Question Text")
                    g_ans = st.text_input("Exact Correct Answer (Case-insensitive)")
                    g_pts = st.number_input("Points Awarded", min_value=10, max_value=500, value=50)
                    if st.button("Post Game"):
                        if g_title and g_q and g_ans:
                            with st.spinner("Posting game and notifying campus..."):
                                conn = get_connection()
                                conn.cursor().execute(
                                    'INSERT INTO brain_games (title, category, question, correct_answer, points) VALUES (%s,%s,%s,%s,%s)',
                                    (g_title, g_cat, g_q, g_ans, g_pts))
                                conn.commit()
                                conn.close()
                                notify_mass_audience("General", None, f"🧠 New Brain Game: {g_title}",
                                                     f"A new {g_cat} worth {g_pts} points has just been posted!\n\nLog into UniUyo Hub now to solve it. Hurry, only the first 4 correct answers will earn points!")
                                st.success("Game posted and emails sent!")
                                st.rerun()
                        else:
                            st.error("Please fill all required fields.")

            st.subheader("Active Challenges")
            conn = get_connection()
            c = conn.cursor()
            c.execute(
                'SELECT id, title, category, question, points, correct_answer, timestamp FROM brain_games ORDER BY timestamp DESC')
            games = c.fetchall()

            if not games: st.info("No active games right now. The Admin will post one soon!")

            for g in games:
                g_id, g_title, g_cat, g_q, g_pts, g_ans, g_ts = g
                ts_formatted = g_ts.strftime("%Y-%m-%d") if isinstance(g_ts, datetime) else g_ts

                c.execute('SELECT COUNT(*) FROM game_submissions WHERE game_id = %s AND is_correct = 1', (g_id,))
                winners_count = c.fetchone()[0]

                c.execute('SELECT is_correct FROM game_submissions WHERE game_id = %s AND username = %s',
                          (g_id, username))
                sub = c.fetchone()

                status_badge = f"<span class='tag-badge' style='background: rgba(241, 196, 15, 0.2); color: #f1c40f; border-color: #f1c40f;'>⭐ {g_pts} Pts ({winners_count}/4 Winners)</span>"
                if winners_count >= 4:
                    status_badge = f"<span class='tag-badge' style='background: rgba(231, 76, 60, 0.2); color: #e74c3c; border-color: #e74c3c;'>⏳ Expired (4/4 Winners)</span>"

                st.markdown(
                    f"<div class='post-box'><h3 style='color: #1ABC9C; margin-bottom: 5px;'>{g_title} <span class='tag-badge'>{g_cat}</span> {status_badge}</h3><p style='font-size: 1.1em;'>{g_q}</p><small style='color: #94a3b8;'>Posted: {ts_formatted}</small></div>",
                    unsafe_allow_html=True)

                if not sub:
                    with st.expander(f"Submit Answer for {g_title}"):
                        user_ans = st.text_input(f"Your Answer", key=f"ans_{g_id}")
                        if st.button("Submit Final Answer", key=f"btn_{g_id}"):
                            if user_ans:
                                with st.spinner("Checking your answer securely..."):
                                    is_correct = 1 if user_ans.strip().lower() == g_ans.strip().lower() else 0
                                    try:
                                        c.execute(
                                            'INSERT INTO game_submissions (game_id, username, is_correct) VALUES (%s,%s,%s)',
                                            (g_id, username, is_correct))
                                        if is_correct:
                                            if winners_count < 4:
                                                c.execute('UPDATE users SET points = points + %s WHERE username = %s',
                                                          (g_pts, username))
                                                st.balloons()
                                                st.success(
                                                    f"🎉 Correct! You were winner #{winners_count + 1}! You just earned {g_pts} points!")
                                            else:
                                                st.info(
                                                    "✅ Your answer is correct! However, the quiz has expired for today because the first four have already answered correctly, so no points are awarded. Better luck tomorrow!")
                                        else:
                                            st.error("❌ Incorrect answer! Better luck on the next game.")

                                        conn.commit()
                                        st.rerun()
                                    except IntegrityError:
                                        st.toast("You already submitted an answer.")
                else:
                    if sub[0] == 1:
                        st.success("✅ You correctly solved this game!")
                    else:
                        st.error("❌ You attempted this game and got it wrong.")
                st.write("---")
            conn.close()

        with tab2:
            st.markdown(
                "<div class='opp-box' style='text-align: center; border-left: none; background: rgba(26, 188, 156, 0.1);'><h2 style='color: #1ABC9C;'>🎁 Monthly Prize Pool</h2><p>At the end of the month, the <b>Top 2</b> students on the leaderboard will receive a special prize from the Admin!</p></div>",
                unsafe_allow_html=True)
            st.subheader("🏆 Top Contributors")

            conn = get_connection()
            c = conn.cursor()
            c.execute('SELECT username, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 15')
            leaders = c.fetchall()
            conn.close()

            if not leaders: st.info("No points awarded yet. Be the first to solve a game!")

            for i, (l_user, l_pts) in enumerate(leaders):
                if i == 0:
                    medal = "<span class='medal-badge'>🥇</span>"
                elif i == 1:
                    medal = "<span class='medal-badge'>🥈</span>"
                elif i == 2:
                    medal = "<span class='medal-badge'>🥉</span>"
                else:
                    medal = f"<span class='medal-badge' style='font-size: 1.2em; color: #94a3b8;'>#{i + 1}</span>"

                bg_color = "rgba(26, 188, 156, 0.15)" if l_user == username else "rgba(255, 255, 255, 0.03)"
                border_style = "border-left: 4px solid #1ABC9C;" if l_user == username else "border-left: 4px solid transparent;"

                st.markdown(
                    f"<div style='background: {bg_color}; padding: 15px; border-radius: 8px; margin-bottom: 8px; {border_style} display: flex; justify-content: space-between; align-items: center;'><div>{medal} <strong>{l_user}</strong></div><div style='font-weight: 800; color: #1ABC9C;'>{l_pts} pts</div></div>",
                    unsafe_allow_html=True)

    elif choice == "Discussions":
        st.title("💬 Student Discussions")
        with st.expander("➕ Start a new discussion"):
            visibility = st.radio("Who can see this?", ["General", "My Department Only"])
            is_anon = st.checkbox("Post Anonymously")
            content = st.text_area("What's on your mind? (Required)")

            st.write("🎤 Add a Voice Note (Optional)")
            vn_bytes = None
            if hasattr(st, "audio_input"):
                vn_upload = st.audio_input("Record directly from device")
                if vn_upload: vn_bytes = vn_upload.read()
            else:
                st.warning("Update Streamlit to unlock direct mic recording. Upload an audio file instead.")

            vn_file = st.file_uploader("Or upload an audio file", type=['wav', 'mp3', 'm4a', 'ogg'])
            if vn_file and not vn_bytes: vn_bytes = vn_file.read()

            if st.button("Post Discussion"):
                if content:
                    with st.spinner("Publishing your post to the campus network..."):
                        vn_url = None
                        if vn_bytes:
                            try:
                                res = cloudinary.uploader.upload(vn_bytes, resource_type="video",
                                                                 folder="uniuyo_hub/voicenotes", format="wav")
                                vn_url = res['secure_url']
                            except Exception:
                                st.warning("Audio upload failed due to cloud settings, posting text only.")

                        conn = get_connection()
                        conn.cursor().execute(
                            'INSERT INTO discussions (author, author_dept, visibility, content, is_anonymous, voice_note_url) VALUES (%s,%s,%s,%s,%s,%s)',
                            (username, user_dept, visibility, content, 1 if is_anon else 0, vn_url))
                        conn.commit()
                        conn.close()
                        st.success("Discussion posted!")
                        author_name = "Anonymous" if is_anon else username
                        notify_mass_audience(visibility, user_dept, "New Discussion Posted on UniUyo Hub",
                                             f"A new discussion was posted in {visibility} by {author_name}.\n\nLog in to check it out!")
                        st.rerun()
                else:
                    st.error("Text content is required to post.")

        conn = get_connection()
        c = conn.cursor()
        c.execute(
            '''SELECT id, author, visibility, content, is_anonymous, timestamp, voice_note_url FROM discussions WHERE visibility = 'General' OR (visibility = 'My Department Only' AND author_dept = %s) ORDER BY timestamp DESC''',
            (user_dept,))
        for post in c.fetchall():
            post_id, author, vis, content, anon, ts, v_note_url = post
            tag = "🌍 General" if vis == "General" else "🏫 Department"
            display_name = "Anonymous" if anon else author
            img_src = "data:image/jpeg;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=" if anon else get_profile_img_src(
                get_user_pic_url(author))

            c.execute('SELECT COUNT(*) FROM likes WHERE post_type=%s AND post_id=%s', ("discussion", post_id))
            ts_formatted = ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime) else ts

            st.markdown(
                f"<div class='post-box'><div class='post-header'><img src='{img_src}' class='profile-img'><div><strong style='color: #1ABC9C;'>{display_name}</strong> <span class='tag-badge'>{tag}</span><br><span class='timestamp'>{ts_formatted}</span></div></div><p style='font-size: 1.1em;'>{content}</p>",
                unsafe_allow_html=True)

            if v_note_url: st.audio(v_note_url, format="audio/wav")
            st.markdown("</div>", unsafe_allow_html=True)

            col1, col2 = st.columns([1, 5])
            if col1.button(f"👍 Like ({c.fetchone()[0]})", key=f"d_like_{post_id}"):
                try:
                    c.execute('INSERT INTO likes (post_type, post_id, username) VALUES (%s,%s,%s)',
                              ("discussion", post_id, username))
                    conn.commit()
                    st.rerun()
                except IntegrityError:
                    st.toast("Already liked!")

            with st.expander("💬 Replies"):
                with st.form(f"reply_form_{post_id}"):
                    rep_input = st.text_input("Reply...")
                    if st.form_submit_button("Send Reply") and rep_input:
                        with st.spinner("Sending reply..."):
                            c.execute('INSERT INTO replies (post_type, post_id, author, content) VALUES (%s,%s,%s,%s)',
                                      ("discussion", post_id, username, rep_input))
                            conn.commit()
                            st.success("Reply sent!")
                            if author != username and not anon:
                                c.execute('SELECT email FROM users WHERE username = %s', (author,))
                                author_email_row = c.fetchone()
                                if author_email_row:
                                    send_uni_email(author_email_row[0], "New Reply to your Discussion",
                                                   f"Hello {author},\n\n{username} just replied to your discussion on UniUyo Hub!\n\nLog in to view their response.")
                            st.rerun()

                c.execute(
                    'SELECT author, content, timestamp FROM replies WHERE post_type=%s AND post_id=%s ORDER BY timestamp ASC',
                    ("discussion", post_id))
                for r in c.fetchall():
                    r_ts = r[2].strftime("%Y-%m-%d %H:%M") if isinstance(r[2], datetime) else r[2]
                    st.markdown(
                        f"<div style='background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; margin-bottom: 5px; border: 1px solid rgba(255,255,255,0.05);'><small><b>{r[0]}</b>: {r[1]} <span style='color:#94a3b8; float: right;'>{r_ts}</span></small></div>",
                        unsafe_allow_html=True)
            st.write("---")
        conn.close()

    elif choice == "Announcements":
        st.title("📢 Campus Announcements")
        if username == ADMIN_USERNAME:
            with st.expander("🛠️ Admin Post"):
                ann_type = st.radio("Audience", ["General", "Specific Department"])
                t_dept = st.selectbox("Department", DEPTS_LIST) if ann_type == "Specific Department" else ""
                ann_content = st.text_area("Message")
                if st.button("Broadcast Announcement") and ann_content:
                    with st.spinner("Broadcasting to all targeted students..."):
                        conn = get_connection()
                        conn.cursor().execute(
                            'INSERT INTO announcements (author, visibility, target_dept, content) VALUES (%s,%s,%s,%s)',
                            (username, ann_type, t_dept, ann_content))
                        conn.commit()
                        conn.close()
                        st.success("Announcement Broadcasted!")
                        notify_mass_audience(ann_type, t_dept, "New Official Announcement",
                                             f"An official announcement was posted by the Admin.\n\nMessage: {ann_content}\n\nLog in to the hub to interact with this post.")
                        st.rerun()

        conn = get_connection()
        c = conn.cursor()
        c.execute(
            '''SELECT id, author, visibility, target_dept, content, timestamp FROM announcements WHERE visibility = 'General' OR (visibility = 'Specific Department' AND target_dept = %s) ORDER BY timestamp DESC''',
            (user_dept,))
        for ann in c.fetchall():
            ann_id, author, vis, t_dept, content, ts = ann
            tag = "🌍 General" if vis == "General" else f"🏫 {t_dept}"
            ts_formatted = ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime) else ts

            c.execute('SELECT COUNT(*) FROM likes WHERE post_type=%s AND post_id=%s', ("announcement", ann_id))
            st.markdown(
                f"<div class='post-box' style='border-left: 6px solid #e74c3c;'><strong style='color: #e74c3c;'>{author} 🛡️ (Admin)</strong> <span class='tag-badge'>{tag}</span><br><p style='font-size: 1.1em; margin-top: 10px;'>{content}</p><span class='timestamp'>{ts_formatted}</span></div>",
                unsafe_allow_html=True)
            if st.button(f"👍 Like ({c.fetchone()[0]})", key=f"a_like_{ann_id}"):
                try:
                    c.execute('INSERT INTO likes (post_type, post_id, username) VALUES (%s,%s,%s)',
                              ("announcement", ann_id, username))
                    conn.commit()
                    st.rerun()
                except IntegrityError:
                    st.toast("Already liked!")
        conn.close()

    elif choice == "Study Resources":
        st.title("📚 Study Resource Center")
        st.write(f"Share and download past questions, notes, and PDFs.")

        with st.expander("📤 Upload a Material"):
            res_title = st.text_input("Document Title")

            if username == ADMIN_USERNAME:
                target_audience = st.radio("Target Audience", ["General (Everyone)", "Specific Department"])
                res_dept = st.selectbox("Select Department",
                                        DEPTS_LIST) if target_audience == "Specific Department" else "General"
            else:
                res_dept = user_dept

            res_file = st.file_uploader("Choose file")
            if st.button("Upload Resource") and res_title and res_file:
                with st.spinner("Uploading file to secure cloud storage..."):
                    try:
                        res = cloudinary.uploader.upload(res_file.read(), resource_type="raw",
                                                         folder="uniuyo_hub/resources", public_id=res_file.name)
                        file_url = res['secure_url']

                        conn = get_connection()
                        conn.cursor().execute(
                            'INSERT INTO study_resources (uploader, uploader_dept, title, file_name, file_url) VALUES (%s,%s,%s,%s,%s)',
                            (username, res_dept, res_title, res_file.name, file_url))
                        conn.commit()
                        conn.close()
                        st.success("Material Uploaded Successfully!")

                        if username == ADMIN_USERNAME:
                            vis = "General" if res_dept == "General" else "Specific Department"
                            notify_mass_audience(vis, res_dept if res_dept != "General" else None,
                                                 f"📚 New Study Material: {res_title}",
                                                 f"Hello,\n\nThe Admin just uploaded a new study material: '{res_title}'.\n\nLog in to the UniUyo Academic Hub to download it and prepare for your exams!\n\nBest,\nUniUyo Hub Admin")
                        st.rerun()
                    except Exception:
                        st.error("Upload failed. Ensure Cloudinary API keys are correct.")

        st.subheader("📥 Available Materials")
        conn = get_connection()
        c = conn.cursor()
        c.execute('''SELECT id, uploader, title, file_name, file_url, timestamp, uploader_dept
                     FROM study_resources
                     WHERE uploader_dept = %s OR uploader_dept = 'General'
                     ORDER BY timestamp DESC''', (user_dept,))

        for res in c.fetchall():
            res_tag = "🌍 General Material" if res[6] == "General" else f"🏫 {res[6]}"
            ts_formatted = res[5].strftime("%Y-%m-%d %H:%M") if isinstance(res[5], datetime) else res[5]

            st.markdown(
                f"<div class='post-box'>📄 <strong>{res[2]}</strong> <span class='tag-badge'>{res_tag}</span><br><small style='color: #94a3b8;'>Uploaded by {res[1]} on {ts_formatted}</small></div>",
                unsafe_allow_html=True)
            st.link_button("⬇️ Download File", res[4])
            st.write("---")
        conn.close()

    elif choice == "GPA/CGPA Tracker":
        st.title("📊 Result & Performance Tracker")
        tab1, tab2 = st.tabs(["Quick Semester GPA", "My Course Performance (CGPA)"])

        with tab1:
            st.subheader("Calculate Semester GPA")
            num_courses = st.number_input("Number of Courses", 1, 15, 5)
            grades, credits = [], []
            cols = st.columns(2)
            for i in range(num_courses):
                with cols[0]: grades.append(
                    st.selectbox(f"Course {i + 1} Grade", ['A', 'B', 'C', 'D', 'E', 'F'], key=f"g_{i}"))
                with cols[1]: credits.append(st.number_input(f"Course {i + 1} Credits", 1, 6, 3, key=f"c_{i}"))

            if st.button("Calculate My GPA", use_container_width=True):
                with st.spinner("Processing results..."):
                    st.balloons()
                    total_pts = sum(calculate_points(g, c) for g, c in zip(grades, credits))
                    total_cr = sum(credits)
                    res = truncate_gpa(total_pts / total_cr) if total_cr > 0 else 0.00
                    deg_class, icon, msg_type = get_class_of_degree(res)

                    if msg_type == "success":
                        st.success(f"**Calculated GPA: {res:.2f}** | {icon} {deg_class}")
                    elif msg_type == "info":
                        st.info(f"**Calculated GPA: {res:.2f}** | {icon} {deg_class}")
                    else:
                        st.warning(f"**Calculated GPA: {res:.2f}** | {icon} {deg_class}")

        with tab2:
            st.subheader("Save Courses to Build CGPA")
            with st.form("add_course"):
                c_code = st.text_input("Course Code (e.g., MTH111)")
                c1, c2 = st.columns(2)
                c_grade = c1.selectbox("Grade", ['A', 'B', 'C', 'D', 'E', 'F'])
                c_credit = c2.number_input("Credit Unit", 1, 6, 3)
                if st.form_submit_button("Save Course", use_container_width=True) and c_code:
                    with st.spinner("Saving course to secure academic ledger..."):
                        conn = get_connection()
                        conn.cursor().execute(
                            'INSERT INTO course_grades (username, course_code, grade, credit) VALUES (%s,%s,%s,%s)',
                            (username, c_code, c_grade, c_credit))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.success("Course saved successfully!")
                        st.rerun()

            conn = get_connection()
            c = conn.cursor()
            c.execute('SELECT course_code, grade, credit FROM course_grades WHERE username = %s', (username,))
            saved = c.fetchall()
            conn.close()

            if saved:
                st.write("### Saved Courses")
                for crs in saved:
                    st.markdown(
                        f"<div style='background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; margin-bottom: 5px; border: 1px solid rgba(255,255,255,0.1);'>📖 <b>{crs[0]}</b> | Grade: <b>{crs[1]}</b> | Credits: <b>{crs[2]}</b></div>",
                        unsafe_allow_html=True)
                deg_class, icon, _ = get_class_of_degree(cgpa)
                st.markdown(
                    f"<div class='opp-box' style='margin-top: 20px;'><h3 style='color: #1ABC9C;'>Your Cumulative GPA (CGPA): {cgpa:.2f}</h3><h4 style='color: #f1f5f9;'>Class of Degree: {icon} {deg_class}</h4></div>",
                    unsafe_allow_html=True)
            else:
                st.info("No courses saved yet. Add a course above to start tracking your CGPA.")

    elif choice == "Scholarships & Alerts":
        st.title("💼 Scholarship & Internship Alerts")
        if username == ADMIN_USERNAME:
            with st.expander("🛠️ Admin: Post Opportunity"):
                o_title = st.text_input("Opportunity Title")
                o_cat = st.selectbox("Category", ["Scholarship", "Internship", "Hackathon", "Other"])
                o_desc = st.text_area("Brief Description")
                o_link = st.text_input("Application Link (URL)")
                if st.button("Post Opportunity"):
                    if o_title and o_link:
                        with st.spinner("Broadcasting opportunity..."):
                            conn = get_connection()
                            conn.cursor().execute(
                                'INSERT INTO opportunities (title, category, description, link) VALUES (%s,%s,%s,%s)',
                                (o_title, o_cat, o_desc, o_link))
                            conn.commit()
                            conn.close()
                            st.success("Posted!")
                            notify_mass_audience("General", None, f"New Opportunity Alert: {o_title}",
                                                 f"A new {o_cat} opportunity has just been posted!\n\nDescription: {o_desc}\nLink: {o_link}\n\nBest of luck with your application!")
                            st.rerun()

        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT title, category, description, link, timestamp FROM opportunities ORDER BY timestamp DESC')
        for o in c.fetchall():
            ts_formatted = o[4].strftime("%Y-%m-%d") if isinstance(o[4], datetime) else o[4]
            st.markdown(
                f"<div class='opp-box'><h4 style='color: #1ABC9C; margin-bottom: 5px;'>{o[0]} <span class='tag-badge'>{o[1]}</span></h4><p>{o[2]}</p><a href='{o[3]}' target='_blank' style='font-weight: bold; color: #3498db;'>🔗 Click here to Apply</a><br><br><span class='timestamp'>Posted: {ts_formatted}</span></div>",
                unsafe_allow_html=True)
        conn.close()

    elif choice == "Exam Countdown":
        st.title("⏳ Exam Countdown Timer")
        with st.form("add_exam"):
            e_course = st.text_input("Course Code")
            e_date = st.date_input("Exam Date")
            if st.form_submit_button("Add Exam", use_container_width=True) and e_course:
                with st.spinner("Adding exam to your calendar..."):
                    conn = get_connection()
                    conn.cursor().execute('INSERT INTO exams (username, course_code, exam_date) VALUES (%s,%s,%s)',
                                          (username, e_course, e_date))
                    conn.commit()
                    conn.close()
                    st.rerun()
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT course_code, exam_date FROM exams WHERE username = %s ORDER BY exam_date ASC', (username,))
        for ex in c.fetchall():
            exam_d = ex[1] if isinstance(ex[1], date) else datetime.strptime(ex[1], "%Y-%m-%d").date()
            days_left = (exam_d - date.today()).days

            if days_left > 0:
                st.info(f"📝 **{ex[0]}** is in **{days_left} days** ({ex[1]})")
            elif days_left == 0:
                st.error(f"🚨 **{ex[0]}** is **TODAY!** Good luck!")
            else:
                st.success(f"✅ **{ex[0]}** - Completed on {ex[1]}")
        conn.close()

    elif choice == "Study Groups":
        st.title("🤝 Department Study Groups")
        with st.expander("➕ Create a New Study Group"):
            with st.form("new_group"):
                g_name = st.text_input("Group Name")
                g_desc = st.text_area("Description")
                if st.form_submit_button("Create Group") and g_name:
                    with st.spinner("Creating study group..."):
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute(
                            'INSERT INTO study_groups (creator, department, group_name, description) VALUES (%s,%s,%s,%s) RETURNING id',
                            (username, user_dept, g_name, g_desc))
                        new_group_id = c.fetchone()[0]
                        c.execute('INSERT INTO group_members (group_id, username) VALUES (%s,%s)',
                                  (new_group_id, username))
                        conn.commit()
                        conn.close()
                        st.rerun()
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT id, creator, group_name, description FROM study_groups WHERE department = %s', (user_dept,))
        for g in c.fetchall():
            c.execute('SELECT COUNT(*) FROM group_members WHERE group_id = %s', (g[0],))
            st.markdown(
                f"<div class='post-box'><h4 style='color: #1ABC9C;'>{g[2]}</h4><p>{g[3]}</p><span class='tag-badge'>👥 Members: {c.fetchone()[0]}</span></div>",
                unsafe_allow_html=True)

            # UPGRADED STUDY GROUP LOGIC (Checks membership, shows Workspace)
            c.execute('SELECT 1 FROM group_members WHERE group_id = %s AND username = %s', (g[0], username))
            is_member = c.fetchone()

            if not is_member:
                if st.button("Join Group", key=f"join_{g[0]}"):
                    with st.spinner("Joining group..."):
                        c.execute('INSERT INTO group_members (group_id, username) VALUES (%s,%s)', (g[0], username))
                        conn.commit()
                        st.rerun()
            else:
                st.success("✅ You are a member of this group.")
                with st.expander("💬 Open Group Workspace"):
                    # Display past group messages
                    c.execute(
                        'SELECT author, content, file_url, timestamp FROM group_messages WHERE group_id = %s ORDER BY timestamp ASC',
                        (g[0],))
                    messages = c.fetchall()
                    if not messages:
                        st.info("No messages yet. Be the first to share an idea!")
                    else:
                        for m in messages:
                            m_ts = m[3].strftime("%Y-%m-%d %H:%M") if isinstance(m[3], datetime) else m[3]
                            st.markdown(
                                f"<div style='background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; margin-bottom: 5px; border: 1px solid rgba(255,255,255,0.05);'><small><b>{m[0]}</b> <span style='color:#94a3b8;'>{m_ts}</span></small><br>{m[1]}</div>",
                                unsafe_allow_html=True)
                            if m[2]:
                                st.link_button("📎 View/Download Attached File", m[2])

                    st.write("---")
                    # Send a new message or file
                    with st.form(f"msg_form_{g[0]}", clear_on_submit=True):
                        msg_text = st.text_area("Share an idea or message with the group...")
                        msg_file = st.file_uploader("Attach a file or image (Optional)", key=f"file_{g[0]}")
                        if st.form_submit_button("Send to Group"):
                            if msg_text or msg_file:
                                with st.spinner("Sending..."):
                                    file_url = None
                                    if msg_file:
                                        try:
                                            res = cloudinary.uploader.upload(msg_file.read(), resource_type="auto",
                                                                             folder="uniuyo_hub/group_files")
                                            file_url = res['secure_url']
                                        except Exception:
                                            st.warning("File upload failed, sending text only.")
                                    c.execute(
                                        'INSERT INTO group_messages (group_id, author, content, file_url) VALUES (%s,%s,%s,%s)',
                                        (g[0], username, msg_text, file_url))
                                    conn.commit()
                                    st.rerun()
                            else:
                                st.error("Please enter a message or attach a file.")
        conn.close()

    elif choice == "Task Manager":
        st.title("📅 Academic Task Reminders")
        with st.form("task_form", clear_on_submit=True):
            desc = st.text_input("Task Description")
            c1, c2 = st.columns(2)
            date_val = c1.date_input("Deadline Date")
            time_val = c2.time_input("Deadline Time")
            if st.form_submit_button("Set Automated Reminder", use_container_width=True):
                deadline_dt = datetime.combine(date_val, time_val)
                if deadline_dt <= datetime.now():
                    st.error("Deadline must be in the future!")
                else:
                    with st.spinner("Scheduling secure email alerts..."):
                        conn = get_connection()
                        conn.cursor().execute(
                            'INSERT INTO tasks (username, email, description, deadline) VALUES (%s,%s,%s,%s)',
                            (username, user_email, desc, deadline_dt))
                        conn.commit()
                        conn.close()
                        st.success("Task saved! You will be emailed reminders at the 2-day, 1-day, and 0-day marks.")
                        st.rerun()
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            'SELECT description, deadline FROM tasks WHERE username = %s AND reminded_0d = 0 ORDER BY deadline ASC',
            (username,))
        for t in c.fetchall():
            ts_formatted = t[1].strftime("%Y-%m-%d %H:%M") if isinstance(t[1], datetime) else t[1]
            st.info(f"📌 **{t[0]}** - Due: {ts_formatted}")
        conn.close()

    elif choice == "About Me":
        st.title("👨‍💻 About the Developer")
        st.markdown(f"""
        <div class="post-box" style="text-align: center;">
            <h2 style="color: #1ABC9C;">Welcome to the UniUyo Academic Support System!</h2>
            <p style="font-size: 1.1em; color: #94a3b8;">This entire platform was engineered by a passionate <b>100 Level Computer Engineering Student</b> at the University of Uyo.</p>
            <p style="color: #f1f5f9;">The vision behind this hub is to digitally transform the student experience—combining result tracking, vital announcements, study collaborations, and task management into one professional ecosystem.</p>
            <hr style="border-color: rgba(255,255,255,0.05);">
            <h4 style="color: #f1f5f9;">📬 Contact & Collaboration</h4>
            <p style="color: #94a3b8;">Have a feature request? Found a bug? Want to collaborate on growing this platform?</p>
            <p style="color: #f1f5f9;">Reach out directly via email at: <a href="mailto:{SENDER_EMAIL}" style="color: #1ABC9C; text-decoration: none;"><b>{SENDER_EMAIL}</b></a></p>
        </div>
        """, unsafe_allow_html=True)
        st.image("uniuyo.jpg", width=200)
        st.write("For the greatest Nigerian students💪🏿💪🏿")
        st.write("ACES 025 GINGER✌🏿✌🏿")
        st.write("ACES 025 SWAGGER")
        st.write("This app was created for the students of the department of computer engineering 025 students. This app can be used by any student in any department.")
        st.write("Developed by: Caleb Offiong James")
        st.write("I am a 100level student")
        st.write("Department of Computer Engineering")
        st.write("whatsapp📞📞: 08075495390")
        st.write("I will really appreciate your feedbacks, recommendations and contributions🙌🏿🙌🏿🙌🏿.")
        st.caption("BUILT BY CALEB")
        st.success("Stay consistent, track your GPA, and wishing you massive success at UNIUYO! 💙💛")
