import streamlit as st
import google.generativeai as genai
from PIL import Image
import json
from pathlib import Path
import pandas as pd
import io
import fitz  # PyMuPDF

# --- KONFIGURASI API KEY ---
# Ambil API Key dari file .streamlit/secrets.toml
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except Exception as e:
    st.error(f"Error Konfigurasi API Key: Pastikan Anda sudah membuat file .streamlit/secrets.toml. Error: {e}")
    st.stop()

# region --- SEMUA PROMPT (Tidak ada perubahan) ---
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
contoh: RT 1 RW 2, RT 3, RT 4A, RT 17,RT 5, RW 1, RW 4,RW 14 dsb.

format alamat adalah: Dukuh RT RW, Desa/Kelurahan, Kecamatan, Kabupaten.
Data JSON alamat.json yang saya berikan adalah daftar resmi alamat (kecamatan, desa, dukuh) di Kabupaten Sragen yang bisa anda gunakan sebagai referensi.

koreksi bagian Alamat saja.
kalo emang ga ada alamat, biarin kosong aja.
Untuk memaksimalkan hasilnya,cukup berikan data terkoreksinya saja dengan format No dan koreksinya.
contoh:
{"No": "5", "Alamat": "PIJILAN RT 16 RW 1,JAMBANAN, SIDOHARJO, SRAGEN"}

Sajikan hasilnya dalam format JSON.
jika tidak ada yang perlu dikoreksi, cukup balas dengan format JSON kosong: []

berikut adalah contoh format alamat yang benar:
["PIJILAN RT 16 RW 1,JAMBANAN, SIDOHARJO, SRAGEN"
"TARAMAN RT 12, TARAMAN, SIDOHARJO SRAGEN"
"PIJILAN RT 4A, JAMBANAN, SIDOHARJO, SRAGEN"
"SINGOPADU RT 6, SINGOPADU, SIDOHARJO, SRAGEN"
"GROMPOLAN, JAMBANAN, SIDOHARJO, SRAGEN"]
"""

prompt2 = """
bantu saya mengkoreksi ulang data json ini.
Saya ingin anda mengecek ulang file json dengan pdf/gambar yang terlampir.

Fokus anda ada pada Nama dan Tanggal kunjungan.
Anda sedang memproses data pasien dari Indonesia, sehingga Anda mengenali struktur nama yang umum.

Dibagian tanggal kunjungan kalo misal tahunnya gak diketahui, isi 2025.
Tanggal kunjungan kalo dari foto, yang biasa tulisannya paling gedhe atau kadang pake spidol, menjelaskan tanggal kunjungan untuk data dibawah bawahnya.

konsekuensinya brarti bagian atasnya gak diketahui kan, nah kalo ketemu kayak gitu, isi aja tanggal kunjungannya dikurang 1 hari dari tanggal dibawahnya.

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

# region --- SEMUA FUNGSI ---

def bersihkan_json(teks_kotor):
    """
    Mencari dan mengekstrak string JSON (list) dari balasan AI.
    """
    if not teks_kotor:
        return "[]"
    try:
        awal = teks_kotor.find('[')
        akhir = teks_kotor.rfind(']')
        if awal != -1 and akhir != -1 and akhir > awal:
            teks_bersih = teks_kotor[awal : akhir + 1]
            json.loads(teks_bersih)
            return teks_bersih
        else:
            return "[]"
    except Exception as e:
        st.warning(f"Gagal membersihkan JSON dari AI. Error: {e}. Mengembalikan list kosong.")
        return "[]"

def gabungkan_hasil_koreksi(data_awal_str, *list_patch_str):
    """
    Menggabungkan data awal dengan BANYAK patch koreksi.
    """
    try:
        data_awal = json.loads(data_awal_str)
        if not isinstance(data_awal, list):
            st.error("Error: Data awal bukan list. Penggabungan dibatalkan.")
            return None

        list_semua_patch_map = []
        for i, patch_str in enumerate(list_patch_str):
            try:
                patch_list = json.loads(patch_str)
                if not isinstance(patch_list, list): patch_list = []
            except (json.JSONDecodeError, TypeError):
                st.warning(f"Patch ke-{i+1} tidak valid JSON atau kosong. Dilewati.")
                patch_list = []
            patch_map = {item['No']: item for item in patch_list if 'No' in item}
            list_semua_patch_map.append(patch_map)

        data_terkoreksi = []
        for pasien in data_awal:
            if 'No' not in pasien:
                data_terkoreksi.append(pasien)
                continue
            no_pasien = pasien['No']
            for patch_map in list_semua_patch_map:
                if no_pasien in patch_map:
                    pasien.update(patch_map[no_pasien])
            data_terkoreksi.append(pasien)

        hasil_final_json = json.dumps(data_terkoreksi, indent=4, ensure_ascii=False)
        return hasil_final_json

    except json.JSONDecodeError:
        st.error(f"Error: 'hasil_ekstraksi' awal bukan JSON valid. Penggabungan gagal.")
        st.code(data_awal_str)
        return None
    except Exception as e:
        st.error(f"Error tidak terduga saat menggabungkan data: {e}")
        return None

# endregion
# --- INTERFACE (GUI) STREAMLIT ---

st.set_page_config(page_title="Admin Klinik", layout="wide")
st.title("🤖 Admin Klinik: Ekstraktor Data Pasien (V2 - Per Halaman)")
st.markdown("Upload file PDF atau Gambar (JPG, PNG). PDF akan diproses halaman per halaman untuk akurasi maksimal.")

path_json_alamat = "alamat.json"
if not Path(path_json_alamat).exists():
    st.error(f"File '{path_json_alamat}' tidak ditemukan. Harap letakkan file di folder yang sama dengan app.py")
    st.stop()

uploaded_files = st.file_uploader(
    "Pilih file PDF atau Gambar:",
    type=['pdf', 'jpg', 'jpeg', 'png'],
    accept_multiple_files=True
)

if 'data_hasil_ai' not in st.session_state:
    st.session_state['data_hasil_ai'] = None

if st.button("Mulai Proses Ekstraksi AI"):
    st.session_state['data_hasil_ai'] = None

    if uploaded_files:
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        list_path_file_untuk_diproses = []
        semua_hasil_per_halaman = []

        with st.spinner("Mempersiapkan file..."):
            # --- PERSIAPAN FILE: SPLIT PDF ATAU SALIN GAMBAR ---
            for f in uploaded_files:
                temp_file_path = temp_dir / f.name
                with open(temp_file_path, "wb") as file_buffer:
                    file_buffer.write(f.getbuffer())

                if temp_file_path.suffix.lower() == ".pdf":
                    st.info(f"Memecah file PDF: {f.name}...")
                    doc = fitz.open(temp_file_path)
                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)
                        pix = page.get_pixmap(dpi=200) # Tingkatkan DPI untuk kualitas lebih baik
                        page_path = temp_dir / f"{temp_file_path.stem}_page_{page_num + 1}.png"
                        pix.save(page_path)
                        list_path_file_untuk_diproses.append(str(page_path))
                    doc.close()
                else:
                    list_path_file_untuk_diproses.append(str(temp_file_path))

        # --- MULAI PROSES UTAMA PER FILE/HALAMAN ---
        total_files = len(list_path_file_untuk_diproses)
        if total_files > 0:
            st.info(f"Total {total_files} halaman akan diproses.")
            progress_bar_total = st.progress(0)

            for idx, file_path in enumerate(list_path_file_untuk_diproses):
                nama_file_display = Path(file_path).name
                st.markdown(f"---")
                st.subheader(f"⚙️ Memproses Halaman {idx + 1}/{total_files}: `{nama_file_display}`")

                list_referensi_file_uploaded = []
                try:
                    with st.spinner(f"[{idx+1}/{total_files}] Mengirim file ke AI dan menjalankan alur..."):
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        chat = model.start_chat()

                        # 1. UPLOAD FILE TUNGGAL
                        file_upload = genai.upload_file(path=file_path)
                        list_referensi_file_uploaded.append(file_upload)

                        # 2. SIAPKAN JSON ALAMAT
                        with open(path_json_alamat, 'r') as f:
                            data_json_string = json.dumps(json.load(f))

                        # --- ALUR CHAT UNTUK SATU HALAMAN ---
                        # ALUR 1: Ekstraksi Awal
                        st.write(f"[{idx+1}] Alur 1: Menjalankan Ekstraksi Awal...")
                        payload_alur_1 = [prompt, data_json_string, file_upload]
                        response1 = chat.send_message(payload_alur_1)
                        hasil_ekstraksi = bersihkan_json(response1.text)

                        if hasil_ekstraksi == "[]" and response1.text:
                            st.error(f"[{idx+1}] Alur 1 Gagal: AI tidak mengembalikan JSON valid untuk {nama_file_display}.")
                            st.code(response1.text)
                            continue # Lanjut ke file berikutnya

                        # ALUR Koreksi berantai...
                        st.write(f"[{idx+1}] Alur 1.1: Koreksi Alamat...")
                        prompt_call_1 = f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt1}"
                        response1_1 = chat.send_message([prompt_call_1, data_json_string])
                        patch_koreksi_1_1 = bersihkan_json(response1_1.text)

                        st.write(f"[{idx+1}] Alur 2: Koreksi Nama & Tgl Kunjungan...")
                        prompt_call_2 = f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt2}"
                        response2 = chat.send_message(prompt_call_2)
                        patch_koreksi_1 = bersihkan_json(response2.text)

                        st.write(f"[{idx+1}] Alur 3: Koreksi Tgl Lahir & Usia...")
                        prompt_call_3 = f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt3}"
                        response3 = chat.send_message(prompt_call_3)
                        patch_koreksi_2 = bersihkan_json(response3.text)

                        st.write(f"[{idx+1}] Alur 4: Koreksi Diagnosa...")
                        payload_alur_4 = [f"Data JSON yang perlu dikoreksi:\n{hasil_ekstraksi}\n\n{prompt4}"]
                        response4 = chat.send_message(payload_alur_4)
                        patch_koreksi_alamat = bersihkan_json(response4.text)

                        # GABUNGKAN HASIL UNTUK HALAMAN INI
                        hasil_final_halaman_ini = gabungkan_hasil_koreksi(
                            hasil_ekstraksi,
                            patch_koreksi_1_1,
                            patch_koreksi_1,
                            patch_koreksi_2,
                            patch_koreksi_alamat
                        )

                        if hasil_final_halaman_ini:
                            data_list = json.loads(hasil_final_halaman_ini)
                            semua_hasil_per_halaman.extend(data_list)
                            st.write(f"✅ Halaman `{nama_file_display}` selesai diproses.")
                        else:
                            st.warning(f"Gagal menggabungkan data untuk halaman `{nama_file_display}`.")

                except Exception as e:
                    st.error(f"Terjadi error saat memproses `{nama_file_display}`: {e}")
                finally:
                    # BERSIHKAN FILE API GOOGLE
                    for file_ref in list_referensi_file_uploaded:
                        try:
                            genai.delete_file(file_ref.name)
                        except Exception as e_del_api:
                            st.warning(f"Gagal hapus file API Google: {e_del_api}")
                
                progress_bar_total.progress((idx + 1) / total_files)

            # --- PEMBERSIHAN FILE LOKAL SETELAH SEMUA SELESAI ---
            st.info("Membersihkan file sementara...")
            for p_str in list_path_file_untuk_diproses:
                try:
                    Path(p_str).unlink()
                except Exception as e_del:
                    st.warning(f"Gagal hapus file temp: {p_str}. Error: {e_del}")
            # Hapus juga file PDF asli yang di-upload
            for f in uploaded_files:
                 if (temp_dir / f.name).exists():
                     (temp_dir / f.name).unlink(missing_ok=True)


            # --- FINALISASI: BUAT DATAFRAME DARI SEMUA HASIL ---
            if semua_hasil_per_halaman:
                df_final = pd.DataFrame(semua_hasil_per_halaman)
                # Re-index kolom 'No' agar berurutan
                df_final['No'] = range(1, len(df_final) + 1)
                st.session_state['data_hasil_ai'] = df_final
                st.success("🎉 Semua halaman selesai diproses! Silakan review tabel di bawah.")
            else:
                st.error("Tidak ada data yang berhasil diekstrak dari semua file.")

    else:
        st.warning("Harap upload file terlebih dahulu sebelum memproses.")


# --- TAMPILKAN EDITOR TABEL & TOMBOL DOWNLOAD ---
if st.session_state['data_hasil_ai'] is not None and not st.session_state['data_hasil_ai'].empty:
    st.markdown("---")
    st.subheader("Data Hasil AI (Silakan Edit Langsung di Tabel Ini)")
    st.markdown("Klik di dalam sel untuk mengedit. Perubahan Anda disimpan otomatis.")

    edited_df = st.data_editor(
        st.session_state['data_hasil_ai'],
        num_rows="dynamic",
        key="editor_pasien",
        use_container_width=True
    )

    st.subheader("Download Hasil Final")
    try:
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
