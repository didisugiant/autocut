from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import os
import re
import uuid
import zipfile
from pathlib import Path
import shutil

app = Flask(__name__)
CORS(app)  # Izinkan akses dari GitHub Pages

# Konfigurasi
UPLOAD_FOLDER = '/tmp/uploads'
OUTPUT_FOLDER = '/tmp/downloads'
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB

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

@app.route('/health')
def health():
    return jsonify({"status": "ok", "ffmpeg": cek_ffmpeg()})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'video' not in request.files:
        return jsonify({"error": "Tidak ada file"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "Nama file kosong"}), 400
    
    # Generate task ID
    task_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(UPLOAD_FOLDER, f"{task_id}_{file.filename}")
    file.save(input_path)
    
    # Ambil durasi
    durasi = request.form.get('durasi', 5)
    try:
        durasi_menit = float(durasi)
    except:
        durasi_menit = 5
    
    # Proses potong
    output_dir = os.path.join(OUTPUT_FOLDER, task_id)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    total_durasi = get_durasi_video(input_path)
    if total_durasi is None:
        return jsonify({"error": "Gagal membaca durasi video"}), 400
    
    durasi_per_episode = durasi_menit * 60
    jumlah_episode = int((total_durasi + durasi_per_episode - 1) // durasi_per_episode)
    
    hasil = []
    for i in range(jumlah_episode):
        start_time = i * durasi_per_episode
        sisa_waktu = total_durasi - start_time
        durasi_episode = min(durasi_per_episode, sisa_waktu)
        nomor_str = f"{i+1:02d}"
        output_file = os.path.join(output_dir, f"episode_{nomor_str}.mp4")
        
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-ss", str(start_time),
            "-t", str(durasi_episode),
            "-c", "copy",
            "-y",
            output_file
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            ukuran = os.path.getsize(output_file) / (1024 * 1024)
            hasil.append({
                "episode": nomor_str,
                "file": output_file,
                "size": f"{ukuran:.1f} MB",
                "duration": format_waktu(durasi_episode)
            })
        except Exception as e:
            return jsonify({"error": f"Gagal potong episode {nomor_str}: {str(e)}"}), 500
    
    # Buat ZIP
    zip_path = os.path.join(OUTPUT_FOLDER, f"{task_id}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for ep in hasil:
            zipf.write(ep["file"], os.path.basename(ep["file"]))
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "total_episodes": jumlah_episode,
        "episodes": hasil,
        "download_url": f"/download/{task_id}"
    })

@app.route('/download/<task_id>')
def download_file(task_id):
    zip_path = os.path.join(OUTPUT_FOLDER, f"{task_id}.zip")
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True)
    return jsonify({"error": "File tidak ditemukan"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
