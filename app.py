from flask import Flask, render_template, request, send_file, jsonify
import subprocess
import os
import re
import shutil
from pathlib import Path
import time
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB limit

# Buat folder jika belum ada
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)

# ===== FUNGSI SPLITTER (dari script sebelumnya) =====
def cek_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except:
        return False

def get_durasi_video(file_video):
    cmd = ["ffmpeg", "-i", file_video]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pattern = r"Duration: (\d+):(\d+):(\d+\.\d+)"
    match = re.search(pattern, result.stderr)
    if match:
        jam = int(match.group(1))
        menit = int(match.group(2))
        detik = float(match.group(3))
        return jam * 3600 + menit * 60 + detik
    return None

def format_waktu(detik):
    jam = int(detik // 3600)
    menit = int((detik % 3600) // 60)
    detik_sisa = int(detik % 60)
    return f"{jam:02d}:{menit:02d}:{detik_sisa:02d}"

def potong_video(input_file, output_dir, durasi_menit, nama_dasar, task_id):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    total_durasi = get_durasi_video(input_file)
    
    if total_durasi is None:
        return {"error": "Gagal membaca durasi video"}
    
    durasi_per_episode = durasi_menit * 60
    jumlah_episode = int((total_durasi + durasi_per_episode - 1) // durasi_per_episode)
    
    hasil = []
    for i in range(jumlah_episode):
        start_time = i * durasi_per_episode
        sisa_waktu = total_durasi - start_time
        durasi_episode = min(durasi_per_episode, sisa_waktu)
        nomor_str = f"{i+1:02d}"
        output_file = os.path.join(output_dir, f"{nama_dasar}_{nomor_str}.mp4")
        
        cmd = [
            "ffmpeg", "-i", input_file,
            "-ss", str(start_time),
            "-t", str(durasi_episode),
            "-c", "copy", "-y",
            output_file
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            ukuran = os.path.getsize(output_file) / (1024 * 1024)
            hasil.append({
                "episode": nomor_str,
                "file": output_file,
                "size": f"{ukuran:.1f} MB",
                "start": format_waktu(start_time),
                "duration": format_waktu(durasi_episode)
            })
        except:
            return {"error": f"Gagal memotong episode {nomor_str}"}
    
    return {"episodes": hasil, "total": jumlah_episode}

# ===== ROUTES =====
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'video' not in request.files:
        return jsonify({"error": "Tidak ada file yang diupload"})
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "Nama file kosong"})
    
    # Simpan file
    task_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_{file.filename}")
    file.save(input_path)
    
    # Ambil durasi
    durasi = request.form.get('durasi', 5)
    try:
        durasi_menit = float(durasi)
    except:
        durasi_menit = 5
    
    # Proses potong
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], task_id)
    hasil = potong_video(input_path, output_dir, durasi_menit, "episode", task_id)
    
    if "error" in hasil:
        return jsonify(hasil)
    
    # Buat ZIP file
    import zipfile
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{task_id}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for ep in hasil["episodes"]:
            zipf.write(ep["file"], os.path.basename(ep["file"]))
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "total_episodes": hasil["total"],
        "episodes": hasil["episodes"],
        "download_url": f"/download/{task_id}"
    })

@app.route('/download/<task_id>')
def download_file(task_id):
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{task_id}.zip")
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True)
    return jsonify({"error": "File tidak ditemukan"}), 404

if __name__ == '__main__':
    if not cek_ffmpeg():
        print("❌ FFmpeg tidak ditemukan! Install: sudo apt install ffmpeg")
    else:
        app.run(debug=True, host='0.0.0.0', port=5000)
