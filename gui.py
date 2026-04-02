import ctypes
import os
import socket
import subprocess
import threading
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

class OMRDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OMRChecker Control Panel")
        self.geometry("750x650")
        self.resizable(False, False)

        # Server state
        self.server_process = None
        self.server_thread = None

        # --- Grid Layout Setup ---
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- HEADER: IP Display ---
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="ew")

        self.ip_label = ctk.CTkLabel(
            self.header_frame, 
            text="Detecting IP...", 
            font=ctk.CTkFont(family="Inter", size=24, weight="bold"),
            text_color="#9D8FFF"
        )
        self.ip_label.pack(pady=5)
        
        self.sub_label = ctk.CTkLabel(
            self.header_frame,
            text="Enter this IP in the Mobile App to connect securely",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.sub_label.pack()

        # Update IP immediately
        self.update_ip_display()

        # --- MIDDLE: Action Buttons ---
        self.actions_frame = ctk.CTkFrame(self)
        self.actions_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.actions_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # 1. Server Start/Stop Button
        self.btn_server = ctk.CTkButton(
            self.actions_frame, 
            text="START SERVER",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=60,
            corner_radius=15,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=self.toggle_server
        )
        self.btn_server.grid(row=0, column=0, padx=10, pady=20, sticky="ew")

        # 2. Firewall Setup Button
        self.btn_firewall = ctk.CTkButton(
            self.actions_frame, 
            text="Setup Firewall Rule",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=60,
            corner_radius=15,
            fg_color="#e67e22",
            hover_color="#d35400",
            command=self.setup_firewall
        )
        self.btn_firewall.grid(row=0, column=1, padx=10, pady=20, sticky="ew")

        # 3. Student List Loader Button
        self.btn_upload = ctk.CTkButton(
            self.actions_frame, 
            text="Select Student List",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=60,
            corner_radius=15,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.load_student_file
        )
        self.btn_upload.grid(row=0, column=2, padx=10, pady=20, sticky="ew")

        # --- BOTTOM: Log Console ---
        self.console_label = ctk.CTkLabel(self, text="Live System Logs", font=ctk.CTkFont(size=16, weight="bold"))
        self.console_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(10, 0), sticky="w")

        self.console = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=13))
        self.console.grid(row=3, column=0, columnspan=2, padx=20, pady=(5, 20), sticky="nsew")
        self.grid_rowconfigure(3, weight=1)

        self.log_message("System Ready.")

    def log_message(self, message):
        """Append message to console safely from any thread."""
        self.console.configure(state="normal")
        self.console.insert("end", f">  {message}\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def update_ip_display(self):
        """Detect local active IPv4 and update the user interface."""
        local_ip = "127.0.0.1"
        try:
            # Use UDP to connect to an external IP to cleanly detect the active outgoing interface IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            pass
        self.ip_label.configure(text=f"Server IP: {local_ip}:8000")

    def toggle_server(self):
        if self.server_process is None:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        self.log_message("Starting FastAPI server on Port 8000...")
        try:
            # Run the server silently connecting stdout so we can pipe it
            # sys.executable ensures the same correct virtual environment/python is used
            self.server_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            self.btn_server.configure(text="STOP SERVER", fg_color="#e74c3c", hover_color="#c0392b")
            
            # Start background thread to capture logs
            self.server_thread = threading.Thread(target=self.capture_server_logs, daemon=True)
            self.server_thread.start()

            self.log_message("✅ Server successfully started.")

        except Exception as e:
            self.log_message(f"❌ Failed to start server: {e}")

    def stop_server(self):
        if self.server_process:
            self.log_message("Stopping server...")
            self.server_process.terminate()
            self.server_process.wait()
            self.server_process = None
            
            self.btn_server.configure(text="START SERVER", fg_color="#2ecc71", hover_color="#27ae60")
            self.log_message("🛑 Server stopped.")

    def capture_server_logs(self):
        """Read standard output from the Uvicorn terminal and post it to our UI log box."""
        if not self.server_process: return
        for line in iter(self.server_process.stdout.readline, ""):
            if line:
                # Strip newlines at the end
                self.after(0, self.log_message, line.strip())
            else:
                break

    def load_student_file(self):
        """Show file dialog and parse the selected Excel/CSV, save as ogrenciler.csv."""
        filepath = filedialog.askopenfilename(
            title="Sınıf Listesini Seç",
            filetypes=[("Excel ve CSV dosyaları", "*.xlsx *.csv")]
        )
        
        if not filepath:
            return

        self.log_message(f"Loading student list from: {os.path.basename(filepath)}...")

        try:
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            
            # Simple check if required columns exist (to help the user)
            if "Ogrenci_No" not in df.columns or "Isim" not in df.columns:
                self.log_message("⚠️ Warning: Your file might not have 'Ogrenci_No' or 'Isim' columns. Make sure the headers match exactly!")

            df.to_csv("ogrenciler.csv", index=False)
            self.log_message("✅ Student list successfully saved as 'ogrenciler.csv' in the project directory.")
            
        except Exception as e:
            self.log_message(f"❌ Failed to read or save file: {e}")

    def setup_firewall(self):
        """Try running the netsh firewall rule. If this isn't elevated, ask for elevation."""
        self.log_message("Attempting to add Firewall Rule...")
        
        rule_name = "OMR Hackathon Port 8000"
        
        if self.is_admin():
            self._run_firewall_cmd(rule_name)
        else:
            self.log_message("Admin privileges required. Please accept the popup prompt.")
            # Elevate our request directly for netsh 
            cmd = "netsh"
            args = f'advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=TCP localport=8000'
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", cmd, args, None, 1) # 1 = SW_SHOWNORMAL
                if int(ret) > 32:
                    self.log_message("✅ Administrator prompt opened. If approved, the rule was added successfully.")
                else:
                    self.log_message(f"❌ Failed to request elevation. Error code: {ret}")
            except Exception as e:
                self.log_message(f"❌ Elevated execution failed: {e}")

    def _run_firewall_cmd(self, rule_name):
        try:
            cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=TCP localport=8000'
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, shell=True)
            self.log_message("✅ Firewall rule successfully added!")
        except subprocess.CalledProcessError as e:
            self.log_message(f"❌ Could not add firewall rule: {e.stderr}")

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

if __name__ == "__main__":
    import sys
    app = OMRDashboard()
    # Clean shutdown on closing window
    def on_closing():
        app.stop_server()
        app.destroy()
        sys.exit(0)
    
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
