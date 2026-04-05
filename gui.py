import ctypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Tema Ayarları
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class OMRDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OMRChecker - Akıllı Optik Okuma Sistemi")
        self.geometry("750x650")

        # Klasör Yapılandırması
        self.paths = {
            "students": "sinif_listesi/",
            "answers": "cevap_anahtari/"
        }
        for path in self.paths.values():
            os.makedirs(path, exist_ok=True)

        # Server state
        self.server_process = None
        self.server_thread = None

        self.setup_ui()
        self.update_ip_display()

    def setup_ui(self):
        # Başlık ve IP
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(20, 10), fill="x")
        
        self.label = ctk.CTkLabel(self.header_frame, text="OMR Kontrol Paneli", font=ctk.CTkFont(size=24, weight="bold"))
        self.label.pack()
        
        self.ip_label = ctk.CTkLabel(self.header_frame, text="IP Tespit Ediliyor...", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db")
        self.ip_label.pack()

        # --- Sunucu Kontrol Bölümü ---
        self.server_frame = ctk.CTkFrame(self)
        self.server_frame.pack(pady=10, padx=20, fill="x")

        self.btn_server = ctk.CTkButton(self.server_frame, text="SUNUCUYU BAŞLAT", fg_color="green", hover_color="#228B22", command=self.toggle_server)
        self.btn_server.pack(side="left", padx=10, pady=15, expand=True)

        self.btn_manual_test = ctk.CTkButton(self.server_frame, text="MANUEL TEST", fg_color="#3498db", hover_color="#2980b9", command=self.run_manual_test)
        self.btn_manual_test.pack(side="left", padx=10, pady=15, expand=True)

        self.btn_firewall = ctk.CTkButton(self.server_frame, text="FIREWALL İZNİ VER", command=self.setup_firewall)
        self.btn_firewall.pack(side="left", padx=10, pady=15, expand=True)

        # --- Dosya Yükleme Bölümü ---
        self.upload_frame = ctk.CTkFrame(self)
        self.upload_frame.pack(pady=10, padx=20, fill="x")

        # Öğrenci Listesi
        self.btn_student = ctk.CTkButton(self.upload_frame, text="Öğrenci Listesini Yükle (.xlsx)", command=self.upload_students)
        self.btn_student.pack(pady=10, padx=20, fill="x")
        self.lbl_student_status = ctk.CTkLabel(self.upload_frame, text="Durum: Liste bekleniyor...", font=ctk.CTkFont(size=12))
        self.lbl_student_status.pack()

        # Cevap Anahtarı
        self.btn_answer = ctk.CTkButton(self.upload_frame, text="Cevap Anahtarını Yükle (.txt)", command=self.upload_answers)
        self.btn_answer.pack(pady=10, padx=20, fill="x")
        self.lbl_answer_status = ctk.CTkLabel(self.upload_frame, text="Durum: Anahtar bekleniyor...", font=ctk.CTkFont(size=12))
        self.lbl_answer_status.pack()

        # --- Log Console ---
        self.console_label = ctk.CTkLabel(self, text="Sistem Kayıtları", font=ctk.CTkFont(size=14, weight="bold"))
        self.console_label.pack(anchor="w", padx=20)

        self.console = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=12))
        self.console.pack(padx=20, pady=(5, 10), fill="both", expand=True)

        self.log_message("Sistem Hazır.")

    def log_message(self, message):
        """Mesajı konsola yazar."""
        self.console.configure(state="normal")
        self.console.insert("end", f">  {message}\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def update_ip_display(self):
        """Yerel IP tespit edip ekrana yazdırır."""
        local_ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            pass
        self.ip_label.configure(text=f"Mobil Uygulama Bağlantı IP: {local_ip}:8000")

    def upload_students(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx")])
        if file_path:
            target = os.path.join(self.paths["students"], "ogrenciler.xlsx")
            shutil.copy(file_path, target)
            self.lbl_student_status.configure(text=f"✅ Başarıyla Yüklendi: {os.path.basename(file_path)}", text_color="green")
            self.log_message(f"Öğrenci listesi güncellendi: {os.path.basename(file_path)}")

    def upload_answers(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if file_path:
            target = os.path.join(self.paths["answers"], "cevaplar.txt")
            shutil.copy(file_path, target)
            self.lbl_answer_status.configure(text=f"✅ Başarıyla Yüklendi: {os.path.basename(file_path)}", text_color="green")
            self.log_message(f"Cevap anahtarı güncellendi: {os.path.basename(file_path)}")

    def toggle_server(self):
        if self.server_process is None:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        self.log_message("FastAPI sunucusu başlatılıyor (Port: 8000)...")
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.server_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"],
                cwd=base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            self.btn_server.configure(text="SUNUCUYU DURDUR", fg_color="#e74c3c", hover_color="#c0392b")
            self.server_thread = threading.Thread(target=self.capture_server_logs, daemon=True)
            self.server_thread.start()
            self.log_message("✅ Sunucu başarıyla başlatıldı.")
        except Exception as e:
            self.log_message(f"❌ Sunucu başlatılamadı: {e}")

    def stop_server(self):
        if self.server_process:
            self.log_message("Sunucu durduruluyor...")
            self.server_process.terminate()
            self.server_process.wait()
            self.server_process = None
            
            self.btn_server.configure(text="SUNUCUYU BAŞLAT", fg_color="green", hover_color="#228B22")
            self.log_message("🛑 Sunucu durduruldu.")

    def capture_server_logs(self):
        if not self.server_process: return
        for line in iter(self.server_process.stdout.readline, ""):
            if line:
                self.after(0, self.log_message, line.strip())
            else:
                break

    def run_manual_test(self):
        """inputs klasöründeki dosyaları kullanarak manuel OMR testini tetikler."""
        inputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inputs")
        files = [f for f in os.listdir(inputs_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('omr_marker')]
        if not files:
            self.log_message("⚠️ 'inputs/' klasöründe test edilecek görüntü bulunamadı.")
            return

        self.log_message("🔄 Manuel test başlatılıyor... ('inputs/' içindeki dosyalar OMR motoruna gönderildi)")
        
        def process_test():
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                proc = subprocess.Popen(
                    [sys.executable, "main.py"],
                    cwd=base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        self.after(0, self.log_message, line.strip())
                    else:
                        break
                proc.wait()
                if proc.returncode == 0:
                    self.log_message("✅ OMR Motoru tamamlandı. Notlandırma ve Excel işlemleri uygulanıyor...")
                    self.after(0, self.apply_grading_logic)
                else:
                    self.log_message(f"❌ Test başarısız oldu (Hata Kodu: {proc.returncode}).")
            except Exception as e:
                self.after(0, self.log_message, f"❌ Test çalıştırılamadı: {e}")

        threading.Thread(target=process_test, daemon=True).start()

    def apply_grading_logic(self):
        """Son üretilen CSV'yi okuyarak cevap anahtarı eşleşmesini yapar ve Excel'i günceller."""
        try:
            import pandas as pd
            import glob, re
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            outputs_dir = os.path.join(base_dir, "outputs")
            
            # 1. En son CSV'yi bul
            matches = glob.glob(os.path.join(outputs_dir, "**", "Results_*.csv"), recursive=True)
            if not matches:
                self.log_message("❌ outputs/ altında Results_ CSV dosyası bulunamadı.")
                return
                
            csv_path = max(matches, key=os.path.getmtime)
            df_res = pd.read_csv(csv_path, dtype=str).fillna("")
            if df_res.empty: return
            
            records = df_res.to_dict(orient="records")
            last_row = records[-1]
            
            # --- Öğrenci No Çıkarımı ---
            roll = str(last_row.get("Roll", last_row.get("roll", ""))).strip()
            if not roll or roll.lower() == "nan":
                roll_chars = []
                for i in range(1, 10):
                    val = str(last_row.get(f"H{i}", "")).strip()
                    if val and val.lower() != "nan":
                        roll_chars.append(val)
                roll = "".join(roll_chars)
                
            if not roll:
                self.log_message("❌ Uyarı: Öğrenci Numarası optik okuyucuda algılanamadı.")
                return

            # --- Excel Eşleşmesi ---
            ogrenciler_path = os.path.join(base_dir, "sinif_listesi", "ogrenciler.xlsx")
            if not os.path.exists(ogrenciler_path):
                self.log_message("❌ sinif_listesi/ogrenciler.xlsx bulunamadı.")
                return
                
            df = pd.read_excel(ogrenciler_path, dtype=str)
            df.columns = df.columns.str.strip()
            if "Ogrenci_No" not in df.columns or "Ad_Soyad" not in df.columns:
                self.log_message("❌ Excel'de 'Ogrenci_No' veya 'Ad_Soyad' sütunu eksik.")
                return

            df["Ogrenci_No"] = df["Ogrenci_No"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            match_idx = df.index[df["Ogrenci_No"] == str(roll).strip()].tolist()
            
            if not match_idx:
                self.log_message(f"❌ {roll} numaralı öğrenci listesinde bulunamadı!")
                return
                
            idx = match_idx[0]
            ad_soyad = df.at[idx, "Ad_Soyad"]
            
            # --- Cevap Anahtarı Okuma ---
            ans_file = os.path.join(base_dir, "cevap_anahtari", "cevaplar.txt")
            if not os.path.exists(ans_file):
                self.log_message("❌ cevap_anahtari/cevaplar.txt bulunamadı.")
                return
                
            with open(ans_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                
            if ":" in content or "-" in content:
                parts = re.split(r'[,\n\r]+', content)
                ans_dict = {}
                for part in parts:
                    part = part.strip()
                    if not part: continue
                    kv = re.split(r'[:\-]', part)
                    if len(kv) >= 2:
                        q_num = re.sub(r'\D', '', kv[0])
                        if q_num:
                            ans_dict[int(q_num)] = kv[1].strip().upper()
                answer_key = "".join(ans_dict.get(i, "X") for i in range(1, 21))
            else:
                answer_key = re.sub(r'\s+', '', content).upper()
                
            # --- Puan Hesaplama ---
            correct_answers_count = 0
            total_q = min(len(answer_key), 20)
            
            for i in range(total_q):
                val = str(last_row.get(f"S{i+1}", last_row.get(f"q{i+1}", ""))).strip().upper()
                if val and val.lower() != "nan" and val == answer_key[i]:
                    correct_answers_count += 1
                    
            score = correct_answers_count * 5
            
            # --- Excel Güncelleme ---
            if "Not" not in df.columns:
                df["Not"] = ""
            df.at[idx, "Not"] = str(score)
            df.to_excel(ogrenciler_path, index=False)
            
            self.log_message(f"📝 BAŞARILI: {roll} numaralı {ad_soyad} işlendi. Notu: {score}")

        except Exception as e:
            self.log_message(f"❌ Değerlendirme sırasında bir hata oluştu: {e}")

    def setup_firewall(self):
        self.log_message("Güvenlik duvarı kuralı eklenmeye çalışılıyor...")
        rule_name = "OMR Checker API Port 8000"
        
        if self.is_admin():
            self._run_firewall_cmd(rule_name)
        else:
            self.log_message("Yönetici izni gerekiyor. Lütfen gelen uyarıyı onaylayın.")
            cmd = "netsh"
            args = f'advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=TCP localport=8000'
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", cmd, args, None, 1)
                if int(ret) > 32:
                    self.log_message("✅ Yönetici onayı alındı. İzin verildi ise kural eklendi.")
                else:
                    self.log_message(f"❌ Yönetici izni alınamadı (Hata: {ret})")
            except Exception as e:
                self.log_message(f"❌ İstisna oluştu: {e}")

    def _run_firewall_cmd(self, rule_name):
        try:
            cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=TCP localport=8000'
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, shell=True)
            self.log_message("✅ Güvenlik duvarı kuralı başarıyla eklendi!")
            messagebox.showinfo("Firewall", "Güvenlik duvarı izni başarıyla verildi.")
        except subprocess.CalledProcessError as e:
            self.log_message(f"❌ Güvenlik duvarı kuralı eklenemedi: {e.stderr}")
            messagebox.showerror("Hata", "Güvenlik duvarı izni verilemedi.")

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

if __name__ == "__main__":
    app = OMRDashboard()
    def on_closing():
        app.stop_server()
        app.destroy()
        sys.exit(0)
    
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
