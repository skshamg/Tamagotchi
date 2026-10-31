import os
import sys
import time
from PyQt6.QtCore import QObject, QPoint, QRect, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QGuiApplication, QPainter
from PyQt6.QtWidgets import QApplication, QWidget
import psutil

# =====================================================================
# 1. TELEMETRY & SYSTEM SAFETY FIREWALL (Background QThread)
# =====================================================================

# Strict Protection: Core OS + Developer Tools + Essential Apps
SYSTEM_PROCESS_WHITELIST = {
    # Windows Core OS
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
    "winlogon.exe", "dwm.exe", "explorer.exe", "sihost.exe", "taskhostw.exe",
    "ctfmon.exe", "shellexperiencehost.exe", "searchindexer.exe",
    "startmenuexperiencehost.exe", "securityhealthservice.exe",
    "antimalware service executable", "msmpeng.exe", "spoolsv.exe", "conhost.exe",
    
    # Dev Tools & Terminals (Do NOT kill your IDE)
    "code.exe",              # VS Code main process
    "code - oss.exe",        # VSCodium / Open-source Code
    "python.exe",            # Python runtimes
    "pythonw.exe",
    "powershell.exe",        # Terminals
    "cmd.exe",
    "windowsterminal.exe",
    "git.exe",
    "bash.exe",
    
    # System Audio / GPU Hardware Daemons
    "audiodg.exe",
    "radeonsoftware.exe",    # AMD software
    "amdfdr.exe"
}

class TelemetryWorker(QObject):
    telemetry_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        while self._is_running:
            try:
                mem = psutil.virtual_memory()
                cpu_pct = psutil.cpu_percent(interval=None)
                ram_pct = mem.percent

                bloat_candidates = []
                current_pid = os.getpid()

                for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                    try:
                        pinfo = proc.info
                        p_name = (pinfo['name'] or '').lower()
                        p_pid = pinfo['pid']

                        if p_pid == current_pid or p_pid <= 4:
                            continue
                        if p_name in SYSTEM_PROCESS_WHITELIST:
                            continue

                        mem_bytes = pinfo['memory_info'].rss if pinfo['memory_info'] else 0
                        mem_mb = mem_bytes / (1024 * 1024)

                        if mem_mb >= 650.0:
                            bloat_candidates.append({
                                'pid': p_pid,
                                'name': pinfo['name'],
                                'mem_mb': round(mem_mb, 1),
                                'cpu': pinfo.get('cpu_percent', 0.0)
                            })
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                bloat_candidates.sort(key=lambda x: x['mem_mb'], reverse=True)
                primary_target = bloat_candidates[0] if bloat_candidates else None

                payload = {
                    "ram_pct": ram_pct,
                    "cpu_pct": cpu_pct,
                    "target": primary_target,
                    "total_targets_count": len(bloat_candidates)
                }
                self.telemetry_updated.emit(payload)

            except Exception as e:
                print(f"[Telemetry Error]: {e}")

            time.sleep(2.5)

# =====================================================================
# 2. NEURAL TAMAGOTCHI GUI WITH CHOMP & FEEDING INTERACTION
# =====================================================================

class NeuralTamagotchi(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Extended canvas to accommodate speech bubble and floating combat text
        self.canvas_width = 160
        self.canvas_height = 130
        self.sprite_width = 80
        self.sprite_height = 80
        self.resize(self.canvas_width, self.canvas_height)

        self.pos_x = 120.0
        self.pos_y = 0.0

        self.velocity_x = 2.2
        self.stalk_speed = 1.2
        self.velocity_y = 0.0
        self.gravity = 0.8
        self.bounce_damping = 0.35
        self.is_falling = False
        self.is_dragging = False
        self.facing_right = True

        # State Engine: WALK, ALERT_SNIFFING, CHOMPING, SATIATED, FALLING
        self.current_state = "WALK"
        self.frame_index = 0
        self.tick_count = 0
        self.satiated_timer = 0
        self.chomp_frame = 0

        # UI Bubble & Floating Text
        self.show_feed_bubble = False
        self.floating_text = ""
        self.floating_text_y = 0.0
        self.floating_text_alpha = 0.0

        self.system_ram = 0.0
        self.system_cpu = 0.0
        self.active_target = None

        self.drag_offset = QPoint()
        self.snap_to_taskbar_floor()

        # 60 FPS Engine Timer
        self.engine_timer = QTimer(self)
        self.engine_timer.timeout.connect(self.update_physics_and_animation)
        self.engine_timer.start(16)

        self.init_telemetry_thread()

    def init_telemetry_thread(self):
        self.telemetry_thread = QThread()
        self.worker = TelemetryWorker()
        self.worker.moveToThread(self.telemetry_thread)

        self.telemetry_thread.started.connect(self.worker.run)
        self.worker.telemetry_updated.connect(self.on_telemetry_received)
        self.telemetry_thread.start()

    def on_telemetry_received(self, data: dict):
        self.system_ram = data["ram_pct"]
        self.system_cpu = data["cpu_pct"]
        self.active_target = data["target"]

        # Only transition to hunting if not currently eating, satiated, or falling
        if self.current_state not in ["CHOMPING", "SATIATED", "FALLING"] and not self.is_dragging:
            if (self.system_ram >= 82.0 or self.active_target) and self.satiated_timer <= 0:
                self.current_state = "ALERT_SNIFFING"
            elif self.satiated_timer <= 0:
                self.current_state = "WALK"

    def get_screen_bounds(self) -> QRect:
        screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080 - 48)

    def snap_to_taskbar_floor(self):
        bounds = self.get_screen_bounds()
        self.pos_x = float(bounds.left() + 120)
        self.pos_y = float(bounds.bottom() - self.canvas_height)
        self.move(int(self.pos_x), int(self.pos_y))

    # --- Mouse & Feeding Button Triggers ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.position().toPoint()
            
            # Check if user clicked the "DEVOUR" button in the bubble
            devour_btn_rect = QRect(20, 5, 120, 36)
            if self.show_feed_bubble and self.active_target and devour_btn_rect.contains(click_pos):
                self.execute_devour()
                event.accept()
                return

            # Otherwise, clicking the pet toggles the feeding bubble if a target exists
            pet_rect = QRect(40, 50, self.sprite_width, self.sprite_height)
            if pet_rect.contains(click_pos):
                if self.active_target:
                    self.show_feed_bubble = not self.show_feed_bubble
                self.drag_offset = event.globalPosition().toPoint() - self.pos()
                self.is_dragging = True
                self.is_falling = False
                self.velocity_y = 0.0
                event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            new_p = event.globalPosition().toPoint() - self.drag_offset
            self.pos_x = float(new_p.x())
            self.pos_y = float(new_p.y())
            self.move(new_p)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.is_falling = True
            event.accept()

    def execute_devour(self):
        """Kills the target process, plays chomp animation, and triggers reward text."""
        if not self.active_target:
            return

        target_pid = self.active_target["pid"]
        target_name = self.active_target["name"]
        freed_mb = self.active_target["mem_mb"]

        try:
            p = psutil.Process(target_pid)
            p.kill()
            print(f"[HARVEST SUCCESS] Devoured {target_name} (PID: {target_pid}) - Freed {freed_mb} MB")

            # Setup floating combat text reward
            self.floating_text = f"+{freed_mb} MB Reclaimed!"
            self.floating_text_y = 45.0
            self.floating_text_alpha = 1.0

            # State transition to Chomp
            self.current_state = "CHOMPING"
            self.chomp_frame = 0
            self.show_feed_bubble = False
            self.active_target = None
            self.satiated_timer = 300  # ~5 seconds of satisfied calm
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"[HARVEST ERROR]: Could not terminate PID {target_pid}: {e}")
            self.show_feed_bubble = False

    # --- Physics & Behavior Engine ---

    def update_physics_and_animation(self):
        self.tick_count += 1
        bounds = self.get_screen_bounds()
        floor_y = float(bounds.bottom() - self.canvas_height)

        # Decay Satiated Timer
        if self.satiated_timer > 0:
            self.satiated_timer -= 1
            if self.satiated_timer == 0 and not self.is_falling:
                self.current_state = "WALK"

        # Floating Combat Text Animation
        if self.floating_text_alpha > 0.0:
            self.floating_text_y -= 0.6
            self.floating_text_alpha -= 0.015

        if self.is_dragging:
            self.update()
            return

        # 1. Vertical Gravity
        if self.pos_y < floor_y or abs(self.velocity_y) > 0.1:
            self.current_state = "FALLING"
            self.velocity_y += self.gravity
            self.pos_y += self.velocity_y

            if self.pos_y >= floor_y:
                self.pos_y = floor_y
                if abs(self.velocity_y) > 2.0:
                    self.velocity_y = -self.velocity_y * self.bounce_damping
                else:
                    self.velocity_y = 0.0
                    self.is_falling = False
                    self.current_state = "ALERT_SNIFFING" if self.active_target and self.satiated_timer <= 0 else "WALK"
        else:
            self.pos_y = floor_y
            self.velocity_y = 0.0

        # 2. Horizontal Locomotion
        if not self.is_falling and self.current_state != "CHOMPING":
            if self.current_state == "WALK" or self.current_state == "SATIATED":
                current_speed = self.velocity_x if self.facing_right else -self.velocity_x
                self.pos_x += current_speed
            elif self.current_state == "ALERT_SNIFFING":
                creep = self.stalk_speed if self.facing_right else -self.stalk_speed
                self.pos_x += creep

            # Boundary Collision
            if self.pos_x + self.canvas_width >= bounds.right():
                self.pos_x = float(bounds.right() - self.canvas_width)
                self.facing_right = False
            elif self.pos_x <= bounds.left():
                self.pos_x = float(bounds.left())
                self.facing_right = True

        self.move(int(self.pos_x), int(self.pos_y))

        # 3. Animation Tick Loop
        if self.tick_count % 6 == 0:
            self.frame_index = (self.frame_index + 1) % 4
            
            # Progress Chomp Animation Sequence
            if self.current_state == "CHOMPING":
                self.chomp_frame += 1
                if self.chomp_frame > 5:
                    self.current_state = "SATIATED"

            self.update()

    # --- Render Pipeline ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        pet_x = 40  # Centered in the 160px canvas
        pet_y = 50

        bounce_offset = 2 if (self.frame_index % 2 == 0 and not self.is_falling) else 0
        if self.is_falling:
            bounce_offset = -3
        elif self.current_state == "ALERT_SNIFFING":
            bounce_offset = 4 if self.frame_index in [1, 3] else 1
        elif self.current_state == "CHOMPING":
            bounce_offset = -2 if (self.chomp_frame % 2 == 0) else 3

        # Body Color by State
        if self.is_falling:
            body_color = QColor(245, 158, 11)
            edge_color = QColor(180, 83, 9)
        elif self.current_state == "ALERT_SNIFFING":
            body_color = QColor(239, 68, 68)   # Crimson (Hunting)
            edge_color = QColor(185, 28, 28)
        elif self.current_state == "CHOMPING":
            body_color = QColor(217, 70, 239)  # Cyber-Violet (Chomping power)
            edge_color = QColor(162, 28, 175)
        elif self.current_state == "SATIATED":
            body_color = QColor(16, 185, 129)  # Emerald (Satisfied)
            edge_color = QColor(4, 120, 87)
        else:
            body_color = QColor(16, 185, 129)
            edge_color = QColor(4, 120, 87)

        # 1. Floating Reclaimed RAM Text
        if self.floating_text_alpha > 0.0:
            font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(font)
            text_color = QColor(16, 185, 129)
            text_color.setAlphaF(max(0.0, self.floating_text_alpha))
            painter.setPen(text_color)
            painter.drawText(QRect(0, int(self.floating_text_y), self.canvas_width, 20), Qt.AlignmentFlag.AlignCenter, self.floating_text)

        # 2. Interactive Devour Bubble
        if self.show_feed_bubble and self.active_target:
            painter.setBrush(QBrush(QColor(15, 23, 42, 240)))
            painter.setPen(QColor(239, 68, 68))
            bubble_rect = QRect(15, 5, 130, 38)
            painter.drawRoundedRect(bubble_rect, 6, 6)

            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.setPen(QColor(254, 202, 202))
            target_label = f"EAT {self.active_target['name'][:10]}?"
            painter.drawText(QRect(15, 8, 130, 14), Qt.AlignmentFlag.AlignCenter, target_label)

            # Devour Action Pill
            painter.setBrush(QBrush(QColor(239, 68, 68)))
            painter.drawRoundedRect(QRect(35, 23, 90, 15), 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRect(35, 24, 90, 14), Qt.AlignmentFlag.AlignCenter, f"CHOMP -{self.active_target['mem_mb']}MB")

        # 3. Sprite Body
        painter.setBrush(QBrush(body_color))
        painter.setPen(edge_color)
        painter.drawRoundedRect(QRect(pet_x + 12, pet_y + 16 + bounce_offset, 56, 44), 14, 14)

        # 4. Face Visor & Chomping Jaws
        painter.setBrush(QBrush(QColor(15, 23, 42)))
        painter.setPen(Qt.PenStyle.NoPen)
        if self.current_state == "CHOMPING":
            # Multi-frame expanding bite mouth
            mouth_open = 18 if (self.chomp_frame % 2 == 1) else 6
            painter.drawRoundedRect(QRect(pet_x + 18, pet_y + 20 + bounce_offset, 44, mouth_open), 4, 4)
            # Sharp 8-bit teeth
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawRect(pet_x + 22, pet_y + 20 + bounce_offset, 6, 4)
            painter.drawRect(pet_x + 36, pet_y + 20 + bounce_offset, 6, 4)
            painter.drawRect(pet_x + 50, pet_y + 20 + bounce_offset, 6, 4)
        else:
            painter.drawRoundedRect(QRect(pet_x + 20, pet_y + 24 + bounce_offset, 40, 20), 6, 6)

        # 5. Scanner Eyes
        eye_offset = 4 if self.facing_right else -4
        if self.current_state == "ALERT_SNIFFING":
            painter.setBrush(QBrush(QColor(254, 202, 202)))
            painter.drawRect(pet_x + 26 + eye_offset, pet_y + 31 + bounce_offset, 8, 4)
            painter.drawRect(pet_x + 42 + eye_offset, pet_y + 31 + bounce_offset, 8, 4)
        elif self.current_state == "SATIATED":
            # Happy closed crescent/line eyes
            painter.setPen(QColor(6, 182, 212))
            painter.drawLine(pet_x + 26 + eye_offset, pet_y + 34 + bounce_offset, pet_x + 34 + eye_offset, pet_y + 34 + bounce_offset)
            painter.drawLine(pet_x + 42 + eye_offset, pet_y + 34 + bounce_offset, pet_x + 50 + eye_offset, pet_y + 34 + bounce_offset)
        elif self.current_state != "CHOMPING":
            painter.setBrush(QBrush(QColor(6, 182, 212)))
            painter.setPen(Qt.PenStyle.NoPen)
            if self.frame_index == 3 and not self.is_falling:
                painter.drawRect(pet_x + 26 + eye_offset, pet_y + 34 + bounce_offset, 8, 2)
                painter.drawRect(pet_x + 42 + eye_offset, pet_y + 34 + bounce_offset, 8, 2)
            else:
                painter.drawRect(pet_x + 26 + eye_offset, pet_y + 30 + bounce_offset, 8, 8)
                painter.drawRect(pet_x + 42 + eye_offset, pet_y + 30 + bounce_offset, 8, 8)

        # 6. Feet
        painter.setBrush(QBrush(edge_color))
        painter.setPen(Qt.PenStyle.NoPen)
        foot_wobble = 3 if self.frame_index % 2 == 0 else -3
        painter.drawRect(pet_x + 18, pet_y + 60 + (foot_wobble if self.facing_right else -foot_wobble), 14, 6)
        painter.drawRect(pet_x + 48, pet_y + 60 + (-foot_wobble if self.facing_right else foot_wobble), 14, 6)

    def closeEvent(self, event):
        self.worker.stop()
        self.telemetry_thread.quit()
        self.telemetry_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = NeuralTamagotchi()
    pet.show()
    sys.exit(app.exec())