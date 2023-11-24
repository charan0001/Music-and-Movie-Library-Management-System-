from flask import Flask, render_template, request, redirect, url_for, session,send_file,Response,current_app
from flask_bcrypt import Bcrypt
import mysql.connector
import io
from io import BytesIO

app = Flask(__name__)
bcrypt = Bcrypt(app)

# Replace 'your_secret_key' with a secure key for sessions
app.config['SECRET_KEY'] = 'your_secret_key'

# Replace these with your MySQL database credentials
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'charanc9',
    'database': 'music_movie',
}

def create_tables():
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL,
            is_admin INT DEFAULT 0
        )
    ''')

    # Check if the admin user already exists
    cur.execute('SELECT * FROM users WHERE username = %s', ('admin',))
    admin_user = cur.fetchone()

    if not admin_user:
        admin_username = 'admin'
        admin_password = bcrypt.generate_password_hash('adminpassword').decode('utf-8')
        cur.execute('INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)',
                    (admin_username, admin_password, 1))

    cur.execute('''
        CREATE TABLE IF NOT EXISTS music (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            artist VARCHAR(255) NOT NULL,
            data LONGBLOB NOT NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            genre VARCHAR(255) NOT NULL,
            data LONGBLOB NOT NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS playlists (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            music_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (music_id) REFERENCES music(id) ON DELETE CASCADE
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS collections (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            movie_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS username_change_audit (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            old_username VARCHAR(255) NOT NULL,
            new_username VARCHAR(255) NOT NULL,
            change_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

create_tables()


def is_admin(user_id):
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()
    cur.execute('SELECT is_admin FROM users WHERE id = %s', (user_id,))
    result = cur.fetchone()
    conn.close()
    return result and result[0] == 1

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s AND is_admin = 1', (username,))
        admin_user = cur.fetchone()
        conn.close()

        if admin_user and bcrypt.check_password_hash(admin_user[2], password):
            session['user_id'] = admin_user[0]
            return redirect(url_for('admin'))
        else:
            return 'Admin login failed. Please check your username and password.'

    return render_template('admin_login.html') 

@app.route('/login', methods=['GET', 'POST'])
def login():
    alert_message = None  

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        conn.close()

        if user:
            if bcrypt.check_password_hash(user[2], password):
                session['user_id'] = user[0]
                if is_admin(session['user_id']):
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('selection'))
            else:
                alert_message = 'Incorrect password. Please try again.'
        else:
            alert_message = 'Username does not exist. Please check your username.'

    return render_template('login.html', alert_message=alert_message)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        existing_user = cur.fetchone()

        if existing_user:
            return render_template('register.html', alert_message='Username already taken. Please choose another.')

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed_password))
        conn.commit()
        conn.close()

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/selection')
def selection():
    return render_template('selection.html')

@app.route('/music')
def music():
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT * FROM music')
    songs = cur.fetchall()

    conn.close()

    return render_template('music.html', songs=songs)

@app.route('/audio/<int:music_id>')
def audio(music_id):
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT data FROM music WHERE id = %s', (music_id,))
    audio_data = cur.fetchone()['data']

    conn.close()

    return Response(audio_data, mimetype='audio/mpeg')

@app.route('/add_to_playlist/<int:music_id>', methods=['POST'])
def add_to_playlist(music_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    # Check if the record already exists in the playlist
    cur.execute('SELECT * FROM playlists WHERE user_id = %s AND music_id = %s', (user_id, music_id))
    existing_record = cur.fetchone()

    if not existing_record:
        # Insert the record if it doesn't exist
        cur.execute('INSERT INTO playlists (user_id, music_id) VALUES (%s, %s)', (user_id, music_id))

        conn.commit()

    conn.close()

    return redirect(url_for('music'))

@app.route('/remove_from_playlist/<int:music_id>', methods=['POST'])
def remove_from_playlist(music_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    cur.execute('DELETE FROM playlists WHERE user_id = %s AND music_id = %s', (user_id, music_id))

    conn.commit()
    conn.close()

    return redirect(url_for('music'))

@app.route('/playlist')
def playlist():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    # Fetch playlist songs
    cur.execute('''
        SELECT music.id, music.title, music.artist
        FROM music
        JOIN playlists ON music.id = playlists.music_id
        WHERE playlists.user_id = %s
    ''', (user_id,))
    playlist_songs = cur.fetchall()

    # Fetch song count in the playlist
    cur.execute('SELECT COUNT(music_id) FROM playlists WHERE user_id = %s', (user_id,))
    song_count_query = cur.statement
    song_count_result = cur.fetchone()

    # Debugging statements
    print(f"song_count_query: {song_count_query}")
    print(f"song_count_result: {song_count_result}")

    song_count = song_count_result['COUNT(music_id)'] if song_count_result and 'COUNT(music_id)' in song_count_result else 0

    conn.close()

    return render_template('playlist.html', playlist_songs=playlist_songs, song_count=song_count)




@app.route('/video/<int:movie_id>')
def video(movie_id):
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT data FROM movies WHERE id = %s', (movie_id,))
    video_data = cur.fetchone()['data']

    conn.close()

    current_app.logger.info(f"Video data size: {len(video_data)} bytes")

    return send_file(io.BytesIO(video_data), mimetype='video/mp4')

@app.route('/movies')
def movies():
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT * FROM movies')
    movies = cur.fetchall()

    conn.close()

    return render_template('movies.html', movies=movies)

@app.route('/add_to_collection/<int:movie_id>', methods=['POST'])
def add_to_collection(movie_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    # Check if the record already exists in the collection
    cur.execute('SELECT * FROM collections WHERE user_id = %s AND movie_id = %s', (user_id, movie_id))
    existing_record = cur.fetchone()

    if not existing_record:
        # Insert the record if it doesn't exist
        cur.execute('INSERT INTO collections (user_id, movie_id) VALUES (%s, %s)', (user_id, movie_id))

        conn.commit()

    conn.close()

    return redirect(url_for('movies'))

@app.route('/remove_from_collection/<int:movie_id>', methods=['POST'])
def remove_from_collection(movie_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    cur.execute('DELETE FROM collections WHERE user_id = %s AND movie_id = %s', (user_id, movie_id))

    conn.commit()
    conn.close()

    return redirect(url_for('movies'))

@app.route('/collection')
def collection():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    # Fetch collection movies
    cur.execute('''
        SELECT movies.id, movies.title, movies.genre
        FROM movies
        JOIN collections ON movies.id = collections.movie_id
        WHERE collections.user_id = %s
    ''', (user_id,))
    collection_movies = cur.fetchall()

    # Fetch movie count in the collection
    cur.execute('SELECT COUNT(movie_id) FROM collections WHERE user_id = %s', (user_id,))
    movie_count_result = cur.fetchone()

    # Debugging statements
    print(f"movie_count_result: {movie_count_result}")

    movie_count = movie_count_result['COUNT(movie_id)'] if movie_count_result and 'COUNT(movie_id)' in movie_count_result else 0

    conn.close()

    return render_template('collection.html', collection_movies=collection_movies, movie_count=movie_count)



@app.route('/view_users')
def view_users():
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT id,username FROM users')
    users = cur.fetchall()

    conn.close()

    return render_template('admin.html', users=users)


@app.route('/view_music')
def view_music():
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT * FROM music')
    music = cur.fetchall()

    conn.close()

    return render_template('admin.html', music=music)


@app.route('/view_movies')
def view_movies():
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT * FROM movies')
    movies = cur.fetchall()

    conn.close()

    return render_template('admin.html', movies=movies)


@app.route('/delete_user', methods=['POST'])
def delete_user():
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    user_id_to_delete = request.form['user_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    cur.execute('DELETE FROM users WHERE id = %s', (user_id_to_delete,))

    conn.commit()
    conn.close()

    return redirect(url_for('admin'))


@app.route('/delete_music', methods=['POST'])
def delete_music():
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    music_id_to_delete = request.form['music_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    cur.execute('DELETE FROM music WHERE id = %s', (music_id_to_delete,))

    conn.commit()
    conn.close()

    return redirect(url_for('admin'))


@app.route('/delete_movie', methods=['POST'])
def delete_movie():
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    movie_id_to_delete = request.form['movie_id']

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    cur.execute('DELETE FROM movies WHERE id = %s', (movie_id_to_delete,))

    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # Check if the user is an admin
    if 'user_id' not in session or not is_admin(session['user_id']):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        artist = request.form['artist']
        genre = request.form['genre']
        file_data = request.files['file'].read()
        data_type = request.form.get('type')  # Get the selected type (music or movie)

        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()

        if data_type == 'music':
            cur.execute('INSERT INTO music (title, artist, data) VALUES (%s, %s, %s)', (title, artist, file_data))
        elif data_type == 'movie':
            cur.execute('INSERT INTO movies (title, genre, data) VALUES (%s, %s, %s)', (title, genre, file_data))

        conn.commit()
        conn.close()

    return render_template('admin.html')

@app.route('/change_username', methods=['GET', 'POST'])
def change_username():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_username = request.form['new_username']
        user_id = session['user_id']

        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()

        cur.callproc('ChangeUsername', (user_id, new_username))

        conn.commit()
        conn.close()

        return redirect(url_for('selection'))

    return render_template('change_username.html')

if __name__ == '__main__':
    app.run(debug=True)
