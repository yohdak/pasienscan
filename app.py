import streamlit as st
import google.generativeai as genai
from PIL import Image
import json
from pathlib import Path
import pandas as pd 
import io            

# --- KONFIGURASI API KEY ---
# Ambil API Key dari file .streamlit/secrets.toml
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except Exception as e:
    st.error(f"Error Konfigurasi API Key: Pastikan Anda sudah membuat file .streamlit/secrets.toml. Error: {e}")
    st.stop() # Hentikan aplikasi jika key tidak ada

# --- DEFINISI PROMPT (Kita taruh di sini) ---
# (Kita asumsikan 'prompt', 'prompt2', 'prompt3' tetap sama)

# region --- SEMUA PROMPT ---
prompt = """
gunakan json alamat.json sebagai referensi alamat.
Tanggal menggunakan format DD-MM-YYYY.
biarkan kosong jika tidak ada datanya.
hilangkan panggilan Tn, Ny, Nn, dr, An dsb.
Tolong ekstrak informasi berikut dari gambar catatan pasien ini:
- No
- Nama Pasien
- Alamat
- Nomor Induk Kependudukan (NIK)
- Suhu Badan (dalam Celsius)
- Tekanan Darah (dalam mmHg)
- Berat Badan (dalam kg)
- Tanggal Kunjungan
- Tanggal Lahir
- Jenis Kelamin
- Usia
- Diagnosa
- Obat/Tindakan

Sajikan hasilnya dalam format JSON.
"""

prompt1 = """
RT adalah singkatan dari Rukun Tetangga, sedangkan RW adalah singkatan dari Rukun Warga.
RT biasa diikuti oleh nomor atau kode yang menunjukkan unit terkecil dalam sistem administrasi wilayah di Indonesia, begitu juga dengan RW.
contoh: RT 01 RW 02, RT 03 RW 01, RT 05 RW 04, RT 4A, RT 17, dsb.

berikut adalah contoh format alamat yang benar:

["SIDOMULYO RT 16 RW 1, SIDOHARJO, SRAGEN"
"TARAMAN RT 12, TARAMAN, SIDOHARJO SRAGEN"
"PIJILAN RT 4A, JAMBANAN, SIDOHARJO, SRAGEN"
"SINGOPADU RT 6, SINGOPADU, SIDOHARJO, SRAGEN"
"GROMPOLAN, JAMBANAN, SIDOHARJO, SRAGEN"]

format alamat adalah: Dukuh RT RW, Desa/Kelurahan, Kecamatan, Kabupaten.
Data JSON alamat.json yang saya berikan adalah daftar resmi alamat (kecamatan, desa, dukuh) di Kabupaten Sragen yang bisa anda gunakan sebagai referensi.

Fokus anda adalah memperbaiki typo alamat, mentranslate singkatan alamat (Contoh: GSA ->Perum Griya Sidoharjo Asri) dan melengkapi alamat sesuai format.

Untuk memaksimalkan hasilnya,cukup berikan data terkoreksinya saja dengan format No dan koreksinya.
contoh:
{"No": "5", "Alamat": "SIDOMULYO RT 16 RW 1, SIDOHARJO, SRAGEN"}
dan seterusnya

Sajikan hasilnya dalam format JSON.
jika tidak ada yang perlu dikoreksi, cukup balas dengan format JSON kosong: []
"""

prompt2 = """
bantu saya mengkoreksi ulang data json ini.
Saya ingin anda mengecek ulang file json dengan pdf/gambar yang terlampir.

Fokus anda ada pada Nama dan Tanggal kunjungan.
Anda sedang memproses data pasien dari Indonesia, sehingga Anda mengenali struktur nama yang umum.

Dibagian tanggal kunjungan tahunnya 2025 bukan null.
Tanggal kunjungan sebenernya kalo dari foto, modelnya itu menjelaskan tanggal kunjungan untuk data dibawahnya, bukan data diatasnya

untuk memaksimalkan hasilnya,cukup berikan data terkoreksinya saja dengan format No dan koreksinya.
contoh:
{"No": "5", "Nama Pasien": "SUGIYANTO", "Tanggal Kunjungan": "05-08-2025"}
{"No": "8", "Tanggal Kunjungan": "05-08-2025"}
{"No": "10", "Nama Pasien": "SRI WAHYUNI"}

Sajikan hasilnya dalam format JSON.
jika tidak ada yang perlu dikoreksi, cukup balas dengan format JSON kosong: []
 """

prompt3 = """
koreksi ulang data json ini.
Saya ingin anda mengecek ulang file json dengan pdf/gambar yang terlampir.
Fokus anda ada pada Tanggal Lahir dan Usia.

Kalo adanya cuma tahun di tanggal lahir, misal 1975, maka ubah menjadi 31-12-1975.
Kalo tanggal lahir kosong tapi ada usia, Isi dengan : Tahun lahir = 2025 - Usia, bulan = 12, tanggal = 31 
kalo di bagian tanggal lahir didapati tahunnya cuma 2 digit, misal 75, maka anggap itu 1975.
tolong isi juga usia berdasarkan tanggal lahir dikurang tanggal kunjungan dengan format contoh: 30 tahun 2 bulan 3 hari

untuk memaksimalkan hasilnya, cukup berikan data terkoreksinya saja dengan format No dan Tanggal Lahir.
contoh:
{"No": "5", "Tanggal Lahir": "31-12-1975"}
{"No": "8", "Tanggal Lahir": "31-12-1980"}

Sajikan hasilnya dalam format JSON.
jika tidak ada yang perlu dikoreksi, cukup balas dengan format JSON kosong: []
"""

prompt4 = """
anggap diri anda sebagai ahli medis.
saya ingin anda mengecek ulang file json dengan pdf/gambar yang terlampir.
fokus pada Diagnosa.

sebagai informasi beberapa Diagnosa menggunakan bahasa campuran indonesia dan jawa.
jadi saya ingin anda memperbaiki Diagnosa agar tidak typo (contoh: ademponan -> adem panas) tanpa mengubah bahasa jawa atau indonesianya.

untuk memaksimalkan hasilnya, cukup berikan data terkoreksinya saja dengan format No dan koreksinya.
Jika tidak ada yang perlu dikoreksi, balas dengan JSON kosong: []
"""
# endregion

# region --- SEMUA FUNGSI (Disalin dari skrip lama) ---

def bersihkan_json(teks_kotor):
    """
    Mencari dan mengekstrak string JSON (list) dari balasan AI.
    """
    if not teks_kotor:
        return "[]" # Kembalikan list kosong jika tidak ada balasan

    try:
        # Cari kurung siku pembuka pertama
        awal = teks_kotor.find('[')
        # Cari kurung siku penutup terakhir
        akhir = teks_kotor.rfind(']')
        
        if awal != -1 and akhir != -1 and akhir > awal:
            teks_bersih = teks_kotor[awal : akhir + 1]
            
            # Coba validasi sekali lagi
            json.loads(teks_bersih) 
            
            return teks_bersih
        else:
            # Jika tidak ditemukan [ atau ], kembalikan list kosong
            return "[]"
    except Exception as e:
        st.warning(f"Gagal membersihkan JSON dari AI. Error: {e}. Mengembalikan list kosong.")
        return "[]" # Gagal parse, kembalikan list kosong

def ekstrak_data_via_file_api(prompt_text, path_json, list_path_file):
    """
    Fungsi ini meng-upload SEMUA file (JPG, PNG, PDF) terlebih dahulu,
    lalu mengirim referensinya ke Gemini.
    """
    model = genai.GenerativeModel('gemini-1.5-flash') 
    
    try:
        # 1. Siapkan JSON String (path_json sekarang lokal)
        with open(path_json, 'r') as f:
            data_json_object = json.load(f)
        data_json_string = json.dumps(data_json_object)

        st.info(f"Meng-upload {len(list_path_file)} file ke File API...")
        
        # 2. Upload SEMUA file dan kumpulkan referensinya
        list_referensi_file_uploaded = []
        progress_bar = st.progress(0)
        
        for i, path_file in enumerate(list_path_file):
            try:
                file_upload = genai.upload_file(path=path_file)
                list_referensi_file_uploaded.append(file_upload)
                st.write(f"Berhasil upload: {Path(path_file).name}")
            except Exception as e_upload:
                st.warning(f"Gagal upload {Path(path_file).name}. Error: {e_upload}. File dilewati.")
            progress_bar.progress((i + 1) / len(list_path_file))

        # 3. Siapkan payload akhir
        payload_lengkap = [prompt_text, data_json_string]
        payload_lengkap.extend(list_referensi_file_uploaded)

        # 4. Kirim request
        st.info("Mengirim data ke Gemini... (Ini bisa lama)")
        response = model.generate_content(payload_lengkap)
        
        # 5. Hapus file
        for file_ref in list_referensi_file_uploaded:
            genai.delete_file(file_ref.name)
            
        return response.text

    except Exception as e:
        st.error(f"Terjadi error saat menghubungi Gemini: {e}")
        return None


def gabungkan_hasil_koreksi(data_awal_str, *list_patch_str): # <--- Fungsi baru dengan *args
    """
    Menggabungkan data awal dengan BANYAK patch koreksi (bisa 1, 2, 3, dst).
    """
    try:
        # 1. Parse data awal
        data_awal = json.loads(data_awal_str)
        if not isinstance(data_awal, list):
             st.error("Error: Data awal bukan list. Penggabungan dibatalkan.")
             return None

        # 2. Buat daftar SEMUA 'peta patch'
        list_semua_patch_map = []
        for i, patch_str in enumerate(list_patch_str):
            try:
                patch_list = json.loads(patch_str)
                if not isinstance(patch_list, list): patch_list = []
            except (json.JSONDecodeError, TypeError):
                st.warning(f"Patch ke-{i+1} tidak valid JSON atau kosong. Dilewati.")
                patch_list = []

            # Buat map dari patch dan tambahkan ke daftar
            patch_map = {item['No']: item for item in patch_list if 'No' in item}
            list_semua_patch_map.append(patch_map)

        # 3. Iterasi data awal dan terapkan SEMUA patch secara berurutan
        data_terkoreksi = []
        for pasien in data_awal:
            if 'No' not in pasien:
                data_terkoreksi.append(pasien) 
                continue 
            no_pasien = pasien['No']

            # Terapkan SEMUA patch (1, 2, 3, dst) ke 'pasien' ini
            for patch_map in list_semua_patch_map:
                if no_pasien in patch_map:
                    pasien.update(patch_map[no_pasien]) # Timpa data pasien

            data_terkoreksi.append(pasien)

        # 4. Konversi hasil akhir
        hasil_final_json = json.dumps(data_terkoreksi, indent=4, ensure_ascii=False)
        return hasil_final_json

    except json.JSONDecodeError:
        st.error(f"Error: 'hasil_ekstraksi' awal bukan JSON valid. Penggabungan gagal.")
        st.code(data_awal_str) # Tampilkan data mentah yang gagal
        return None
    except Exception as e:
        st.error(f"Error tidak terduga saat menggabungkan data: {e}")
        return None

# endregion
# --- INTERFACE (GUI) STREAMLIT ---

st.set_page_config(page_title="Admin Klinik", layout="wide")
st.title("🤖 Admin Klinik: Ekstraktor Data Pasien")
st.markdown("Upload file PDF atau Gambar (JPG, PNG) untuk diekstrak datanya.")

# Tentukan path file json alamat (HARUS ADA DI FOLDER YANG SAMA)
path_json_alamat = "alamat.json"

if not Path(path_json_alamat).exists():
    st.error(f"File '{path_json_alamat}' tidak ditemukan. Harap letakkan file di folder yang sama dengan app.py")
    st.stop() # Hentikan aplikasi jika file alamat tidak ada

# 1. Buat "File Uploader"
uploaded_files = st.file_uploader(
    "Pilih file PDF atau Gambar:",
    type=['pdf', 'jpg', 'jpeg', 'png'],
    accept_multiple_files=True
)

# Inisialisasi 'memori' (session state) untuk menyimpan data
if 'data_hasil_ai' not in st.session_state:
    st.session_state['data_hasil_ai'] = None

# 2. Buat Tombol "Proses"
# GANTI SEMUA BLOK if st.button(...) ANDA DENGAN INI:

if st.button("Mulai Proses Ekstraksi AI"):
    # 1. Hapus data lama dari 'memori'
    st.session_state['data_hasil_ai'] = None 
    
    if uploaded_files:
        with st.spinner("Mohon tunggu, AI sedang bekerja (Alur 1-4)..."):
            
            # --- Definisikan Variabel Hasil (penting untuk 'finally') ---
            list_path_file_temp = []
            list_referensi_file_uploaded = [] # Simpan referensi file Google
            
            try:
                # --- SIMPAN FILE LOKAL SEMENTARA ---
                temp_dir = Path("temp_uploads")
                temp_dir.mkdir(exist_ok=True)
                
                for f in uploaded_files:
                    temp_file_path = temp_dir / f.name
                    with open(temp_file_path, "wb") as file_buffer:
                        file_buffer.write(f.getbuffer())
                    list_path_file_temp.append(str(temp_file_path))

                # --- ALUR CHAT BARU (ADA DI DALAM 'TRY') ---
                
                model = genai.GenerativeModel('gemini-2.5-flash')
                
                # 1. UPLOAD KE GOOGLE API (HANYA SEKALI)
                st.info(f"Meng-upload {len(list_path_file_temp)} file ke File API...")
                for path_file in list_path_file_temp:
                    try:
                        file_upload = genai.upload_file(path=path_file)
                        list_referensi_file_uploaded.append(file_upload)
                        st.write(f"Berhasil upload: {Path(path_file).name}")
                    except Exception as e_upload:
                        st.warning(f"Gagal upload {Path(path_file).name}: {e_upload}")
                
                if not list_referensi_file_uploaded:
                    st.error("Tidak ada file yang berhasil di-upload ke Google. Proses berhenti.")
                    st.stop()
                
                # 2. SIAPKAN JSON ALAMAT
                with open(path_json_alamat, 'r') as f:
                    data_json_string = json.dumps(json.load(f))

                # 3. MULAI SESI CHAT
                st.info("AI sedang bekerja...")
                chat = model.start_chat()

                # ALUR 1: Kirim file + prompt1
                st.write("Alur 1: Menjalankan Ekstraksi Awal...")
                payload_alur_1 = [prompt, data_json_string]
                payload_alur_1.extend(list_referensi_file_uploaded)
                response1 = chat.send_message(payload_alur_1)
                hasil_ekstraksi = bersihkan_json(response1.text)
                
                if hasil_ekstraksi == "[]" and response1.text:
                    st.error("Alur 1 Gagal: AI tidak mengembalikan JSON yang valid.")
                    st.code(response1.text)
                    st.stop()
                
                st.write("Alur 1.1: Menjalankan Koreksi Alamat Sesuai Format ...")
                prompt_call_1 = f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt1}"
                payload_alur_1_1= [prompt_call_1, data_json_string]
                response1_1 = chat.send_message(payload_alur_1_1)
                patch_koreksi_1_1 = bersihkan_json(response1_1.text)
                st.write("Koreksi 1.1 selesai.")

                # ALUR 2: Kirim prompt2 + HASIL EKSTRAKSI (Ini perbaikannya)
                st.write("Alur 2: Menjalankan Koreksi Nama & Tgl Kunjungan...")
                prompt_call_2 = f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt2}"
                response2 = chat.send_message(prompt_call_2)
                patch_koreksi_1 = bersihkan_json(response2.text)
                st.write("Koreksi 1 selesai.")

                # ALUR 3: Kirim prompt3 + HASIL EKSTRAKSI (Ini perbaikannya)
                st.write("Alur 3: Menjalankan Koreksi Tgl Lahir & Usia...")
                prompt_call_3 = f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt3}"
                response3 = chat.send_message(prompt_call_3)
                patch_koreksi_2 = bersihkan_json(response3.text)
                st.write("Koreksi 2 selesai.")
                
                # ALUR 4 (BARU): Koreksi Alamat
                st.write("Alur 4: Menjalankan Koreksi Diagnosa...")
                # Kita kirim prompt4 DAN referensi alamat.json LAGI agar fokus
                payload_alur_4 = [f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt4}"]
                
                response4 = chat.send_message(payload_alur_4)
                patch_koreksi_alamat = bersihkan_json(response4.text)
                st.write("Crosscheck ulang Diagnosa.")
                
                # ALUR 5 (GABUNG): Sekarang kita gabung SEMUA patch
                st.write("Alur 5: Menggabungkan Hasil Final...")
                hasil_final_ai = gabungkan_hasil_koreksi(
                    hasil_ekstraksi, 
                    patch_koreksi_1,
                    patch_koreksi_1_1, 
                    patch_koreksi_2,
                    patch_koreksi_alamat  # <--- Patch baru ditambahkan
                )

                if hasil_final_ai:
                    data_dict = json.loads(hasil_final_ai)
                    df_hasil_ai = pd.DataFrame(data_dict)
                    st.session_state['data_hasil_ai'] = df_hasil_ai
                    st.success("🎉 Proses AI Selesai! Silakan review tabel di bawah.")
                else:
                    st.error("Gagal menggabungkan data AI.")
            
            except Exception as e:
                st.error(f"Terjadi error tak terduga: {e}")
            
            finally:
                # Blok 'finally' akan SELALU jalan, baik sukses atau error
                
                # BERSIHKAN FILE API GOOGLE
                if list_referensi_file_uploaded:
                    st.info("Menghapus file di File API...")
                    for file_ref in list_referensi_file_uploaded:
                        try:
                            genai.delete_file(file_ref.name)
                        except Exception as e_del_api:
                            st.warning(f"Gagal hapus file API Google: {e_del_api}")

                # BERSIHKAN FILE TEMP LOKAL
                st.write("Membersihkan file sementara...")
                for p in list_path_file_temp:
                    try:
                        Path(p).unlink()
                    except Exception as e_del:
                        st.warning(f"Gagal hapus file temp: {p}. Error: {e_del}")
    else:
        st.warning("Harap upload file terlebih dahulu sebelum memproses.")


# --- TAMPILKAN EDITOR TABEL & TOMBOL DOWNLOAD ---
# Bagian ini ada di luar tombol 'if st.button(...)', 
# jadi akan tampil otomatis jika 'memori' (session state) sudah terisi

if st.session_state['data_hasil_ai'] is not None:
    
    st.subheader("Data Hasil AI (Silakan Edit Langsung di Tabel Ini)")
    st.markdown("Klik di dalam sel untuk mengedit. Perubahan Anda disimpan otomatis.")
    
    # 3. Tampilkan data editor
    # 'edited_df' akan berisi data terbaru SETELAH dikoreksi paman Anda
    edited_df = st.data_editor(
        st.session_state['data_hasil_ai'],
        num_rows="dynamic", # Memperbolehkan paman Anda menambah/menghapus baris
        key="editor_pasien", # Kunci untuk menyimpan state editan
        width="stretch" # Gunakan lebar penuh
    )
    
    # 4. Tombol Download sekarang mengambil data dari 'edited_df'
    st.subheader("Download Hasil Final")
    try:
        # Siapkan file Excel dari 'edited_df' (data terbaru)
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='DataPasien')
        
        st.download_button(
            label="📥 Download Data Final (Excel)",
            data=output_excel.getvalue(),
            file_name="hasil_final_pasien.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Gagal membuat file Excel: {e}")