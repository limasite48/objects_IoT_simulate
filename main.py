import sys
import os

# Cấu hình encoding UTF-8 cho dòng lệnh để chạy tốt trên Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')

# Thêm thư mục hiện tại và thư mục gốc của project vào sys.path để chạy tốt ở mọi ngữ cảnh
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

import time
import threading
from datetime import datetime
import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER, MQTT_PORT, TOPIC_TELEMETRY, TOPIC_COMMAND,
    ZONES, ZONE_CODES, TYPE_CODES, CODE_TO_ZONE, CODE_TO_TYPE
)
from protocol import parse_downlink_frame, decode_command_payload
from simulation import OfficeSimulation

# Khởi tạo đối tượng mô phỏng toàn bộ văn phòng
sim = OfficeSimulation()

# Flag log để bật/tắt hiển thị gói tin Hex thô trên màn hình
log_hex = False

# Event đồng bộ hóa kết nối mạng trước khi chạy mô phỏng
connected_event = threading.Event()

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback khi kết nối thành công tới broker"""
    print(f"\n[MQTT] Đã kết nối thành công tới Broker: {MQTT_BROKER}", flush=True)
    client.subscribe(TOPIC_COMMAND)
    print(f"[MQTT] Đã subscribe kênh lệnh: {TOPIC_COMMAND}\n", flush=True)
    connected_event.set()

def on_message(client, userdata, msg):
    """Callback khi nhận được tin nhắn trên kênh command"""
    global log_hex
    payload_str = msg.payload.decode("utf-8", errors="ignore").strip()
    
    # Thử giải mã gói tin Hex nhận được từ gateway
    parsed = parse_downlink_frame(payload_str)
    if not parsed:
        return # Gói tin không hợp lệ hoặc sai checksum, bỏ qua
        
    zone_code = parsed["zone_id"]
    type_code = parsed["type_code"]
    payload_bytes = parsed["payload"]
    
    zone_name = CODE_TO_ZONE.get(zone_code)
    type_name = CODE_TO_TYPE.get(type_code)
    
    if not zone_name or not type_name:
        return # Không xác định được thiết bị/phân vùng
        
    # Giải mã chi tiết lệnh điều khiển
    cmd_data = decode_command_payload(type_code, payload_bytes)
    if not cmd_data:
        return
        
    if log_hex:
        print(f"\n[ZIGBEE RX] Nhận lệnh Hex: {payload_str}")
        print(f"            Thiết bị: {zone_name} / {type_name} | Lệnh: {cmd_data}")
        
    # Áp dụng lệnh vào hệ thống giả lập
    if type_name == "light":
        sim.set_light_state(zone_name, cmd_data["active"])
    elif type_name == "ahu":
        sim.set_ahu_state(zone_name, cmd_data["active"], cmd_data.get("fan_speed"), cmd_data.get("temp_set"))
    elif type_name == "curtain":
        sim.set_curtain_state(zone_name, cmd_data["percentage_cover"])

# Khởi tạo MQTT Client sử dụng callback API version 2
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def simulation_loop():
    """Luồng chạy ngầm cập nhật trạng thái vật lý và đẩy dữ liệu lên gateway"""
    global log_hex
    while True:
        sim.update()
        
        # Đẩy tất cả các gói tin trong hàng đợi gửi (Zigbee uplink) lên Broker với độ trễ ngắn tránh rớt gói
        while sim.publish_queue:
            code, type_code, hex_msg = sim.publish_queue.pop(0)
            res = mqtt_client.publish(TOPIC_TELEMETRY, hex_msg)
            
            if log_hex:
                zone_name = CODE_TO_ZONE.get(code, f"0x{code:02X}")
                type_name = CODE_TO_TYPE.get(type_code, f"0x{type_code:02X}")
                print(f"[ZIGBEE TX] {zone_name:<15} | Cảm biến: {type_name:<8} | Hex: {hex_msg} | RC: {res.rc}", flush=True)
            
            # Trễ ngắn 100ms ngăn chặn nén/rớt gói tin do quá tải hàng đợi Broker
            time.sleep(0.1)
                
        # Nghỉ ngắn để giảm tải CPU (0.1 giây thực tế)
        time.sleep(0.1)

def print_help():
    print("\n================ CÁC LỆNH ĐIỀU KHIỂN GIẢ LẬP ================")
    print("1. Trạng thái: `status` hoặc `st` (Xem chi tiết môi trường các zone)")
    print("2. Đèn: `light <zone> <on/off>` (VD: `light pantry on`)")
    print("3. Điều hòa: `ahu <zone> <on/off> [tốc độ 1-3] [nhiệt độ]` (VD: `ahu pantry on 2 24.5`)")
    print("4. Cửa sổ: `window <1-6> <open/close>` (VD: `window 1 open`)")
    print("5. Rèm cửa: `curtain <1-6> <che_phủ 0-100>` (VD: `curtain 1 80`)")
    print("6. Cửa đi: `door <1-5> <open/close>` (VD: `door 2 open`)")
    print("7. Báo khói: `smoke <zone> <on/off>` (VD: `smoke storage on`)")
    print("8. Tốc độ thời gian: `time speed <hệ_số>` (VD: `time speed 60` - 1 giây thực = 1 phút giả lập)")
    print("9. Nhảy thời gian: `time set <năm-tháng-ngày> <giờ:phút:giây>` (VD: `time set 2026-07-01 12:00:00`)")
    print("10. Bật/Tắt Log Hex: `log <on/off>` (Bật/tắt in log gói tin Zigbee thô)")
    print("11. Thoát: `exit` hoặc `quit` (Thoát chương trình)")
    print("=============================================================")

def display_status():
    """Hiển thị bảng trạng thái hiện tại một cách rõ ràng"""
    print(f"\n--- THỜI GIAN GIẢ LẬP: {sim.sim_time.strftime('%Y-%m-%d %H:%M:%S')} (Tốc độ: {sim.time_speed}x) ---")
    print(f"Thời tiết Hà Nội ngoài trời: {sim.outdoor_temp:.1f}°C | Độ ẩm: {sim.outdoor_humid:.1f}% | Cường độ sáng: {sim.outdoor_light:.0f} lux\n")
    
    # Header bảng Zone
    print(f"+-----------------+----------+--------+-------------+-------+-------+-------------------------+")
    print(f"|       Phân vùng | Nhiệt độ |  Độ ẩm |    Ánh sáng |  Khói |   Đèn |            Điều hòa AHU |")
    print(f"+-----------------+----------+--------+-------------+-------+-------+-------------------------+")
    for zone in ZONES:
        state = sim.zone_states[zone]
        smoke_str = "CÓ KHÓI" if state["smoke"] else "Không"
        light_str = "BẬT" if state["light_active"] else "TẮT"
        
        if state["ahu_active"]:
            ahu_str = f"BẬT (TĐ:{state['ahu_fan_speed']}, Đặt:{state['ahu_temp_set']:.1f}°C)"
        else:
            ahu_str = f"TẮT (Đặt:{state['ahu_temp_set']:.1f}°C)"
            
        print(f"| {zone:<15} |  {state['temp']:>5.1f}°C | {state['humid']:>5.1f}% | {state['light_intensity']:>7} lux | {smoke_str:<5} |  {light_str:<5}| {ahu_str:<23} |")
    print(f"+-----------------+----------+--------+-------------+-------+-------+-------------------------+")
    
    # Bảng Cửa đi
    print("\n--- TRẠNG THÁI CỬA ĐI ---")
    door_line = " | ".join([f"{d}: {'MỞ' if info['is_open'] else 'ĐÓNG'}" for d, info in sim.doors.items()])
    print(door_line)
    
    # Bảng Cửa sổ & Rèm
    print("\n--- TRẠNG THÁI CỬA SỔ & RÈM ---")
    for wd, info in sim.windows.items():
        print(f"- {wd}: {'MỞ' if info['is_open'] else 'ĐÓNG'} | Rèm che phủ: {info['curtain_pct']}%")
    print("")

def console_loop():
    """Vòng lặp chính xử lý các lệnh nhập từ màn hình"""
    global log_hex
    print_help()
    while True:
        try:
            cmd_line = input("\nNhập lệnh giả lập: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nĐang tắt chương trình giả lập...")
            break
            
        if not cmd_line:
            continue
            
        parts = cmd_line.split()
        cmd = parts[0].lower()
        
        if cmd in ["exit", "quit"]:
            print("Đang dừng bộ giả lập...")
            break
            
        elif cmd in ["h", "help"]:
            print_help()
            
        elif cmd in ["status", "st"]:
            display_status()
            
        elif cmd == "log":
            if len(parts) > 1 and parts[1].lower() in ["on", "off"]:
                log_hex = (parts[1].lower() == "on")
                print(f"Đã {'BẬT' if log_hex else 'TẮT'} nhật ký Hex.")
            else:
                print("Sai cú pháp. Dùng: `log <on/off>`")
                
        elif cmd == "light":
            if len(parts) >= 3:
                zone = parts[1].lower()
                state_str = parts[2].lower()
                if zone in ZONES and state_str in ["on", "off"]:
                    active = (state_str == "on")
                    sim.set_light_state(zone, active)
                    print(f"Đã điều khiển thủ công: Đèn {zone} -> {'BẬT' if active else 'TẮT'}")
                else:
                    print("Tên zone hoặc trạng thái không hợp lệ.")
            else:
                print("Sai cú pháp. Dùng: `light <zone> <on/off>`")
                
        elif cmd == "ahu":
            if len(parts) >= 3:
                zone = parts[1].lower()
                state_str = parts[2].lower()
                if zone in ZONES and state_str in ["on", "off"]:
                    active = (state_str == "on")
                    fan_speed = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
                    temp_set = float(parts[4]) if len(parts) > 4 else None
                    sim.set_ahu_state(zone, active, fan_speed, temp_set)
                    print(f"Đã điều khiển thủ công: AHU {zone} -> {'BẬT' if active else 'TẮT'} (Tốc độ: {fan_speed}, Đặt: {temp_set})")
                else:
                    print("Tên zone hoặc trạng thái không hợp lệ.")
            else:
                print("Sai cú pháp. Dùng: `ahu <zone> <on/off> [tốc độ 1-3] [nhiệt độ]`")
                
        elif cmd == "door":
            if len(parts) >= 3:
                door_num = parts[1]
                state_str = parts[2].lower()
                door_id = f"door_0{door_num}"
                if door_id in sim.doors and state_str in ["open", "close", "closed"]:
                    is_open = (state_str == "open")
                    sim.set_door_state(door_id, is_open)
                    print(f"Đã điều khiển: {door_id} -> {'MỞ' if is_open else 'ĐÓNG'}")
                else:
                    print("Số cửa (1-5) hoặc trạng thái không hợp lệ.")
            else:
                print("Sai cú pháp. Dùng: `door <1-5> <open/close>`")
                
        elif cmd == "window":
            if len(parts) >= 3:
                wd_num = parts[1]
                state_str = parts[2].lower()
                wd_id = f"wd_0{wd_num}"
                if wd_id in sim.windows and state_str in ["open", "close", "closed"]:
                    is_open = (state_str == "open")
                    sim.set_window_state(wd_id, is_open)
                    print(f"Đã điều khiển: {wd_id} -> {'MỞ' if is_open else 'ĐÓNG'}")
                else:
                    print("Số cửa sổ (1-6) hoặc trạng thái không hợp lệ.")
            else:
                print("Sai cú pháp. Dùng: `window <1-6> <open/close>`")
                
        elif cmd == "curtain":
            if len(parts) >= 3:
                wd_num = parts[1]
                pct_str = parts[2]
                wd_id = f"wd_0{wd_num}"
                if wd_id in sim.windows and pct_str.isdigit():
                    pct = int(pct_str)
                    if 0 <= pct <= 100:
                        sim.set_curtain_state(wd_id, pct)
                        print(f"Đã điều khiển: Rèm {wd_id} -> che phủ {pct}%")
                    else:
                        print("Phần trăm che phủ phải từ 0 đến 100.")
                else:
                    print("Số cửa sổ (1-6) hoặc giá trị phần trăm không hợp lệ.")
            else:
                print("Sai cú pháp. Dùng: `curtain <1-6> <0-100>`")
                
        elif cmd == "smoke":
            if len(parts) >= 3:
                zone = parts[1].lower()
                state_str = parts[2].lower()
                if zone in ZONES and state_str in ["on", "off"]:
                    has_smoke = (state_str == "on")
                    sim.set_smoke_alarm(zone, has_smoke)
                    print(f"Đã đặt cảm biến báo khói {zone} -> {'CÓ KHÓI' if has_smoke else 'BÌNH THƯỜNG'}")
                else:
                    print("Tên zone hoặc trạng thái không hợp lệ.")
            else:
                print("Sai cú pháp. Dùng: `smoke <zone> <on/off>`")
                
        elif cmd == "time":
            if len(parts) >= 3:
                sub_cmd = parts[1].lower()
                if sub_cmd == "speed":
                    try:
                        speed = float(parts[2])
                        sim.time_speed = speed
                        print(f"Đã đổi tốc độ giả lập: {speed}x")
                    except ValueError:
                        print("Tốc độ thời gian phải là một số.")
                elif sub_cmd == "set":
                    # Cú pháp: `time set 2026-07-01 12:00:00`
                    try:
                        time_str = " ".join(parts[2:])
                        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        sim.sim_time = dt
                        print(f"Đã chỉnh thời gian giả lập thành: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    except ValueError:
                        print("Sai định dạng ngày giờ. Dùng: `time set YYYY-MM-DD HH:MM:SS`")
                else:
                    print("Lệnh time phụ không hợp lệ. Dùng: `time speed <hệ_số>` hoặc `time set <ngày giờ>`")
            else:
                print("Sai cú pháp lệnh time.")
        else:
            print("Lệnh không hợp lệ. Gõ `help` để xem danh sách lệnh.")
def main():
    print("-------------------------------------------------------------")
    print("Bộ Giả Lập Thiết Bị & Cảm Biến IoT (Zigbee Simulation over MQTT)")
    print("Địa điểm giả lập: Hà Nội, Việt Nam")
    print("-------------------------------------------------------------")
    
    # Kết nối MQTT Broker
    print(f"Đang kết nối tới MQTT Broker: {MQTT_BROKER}...", flush=True)
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        # Bắt đầu vòng lặp xử lý sự kiện MQTT chạy ngầm
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[ERROR] Không thể kết nối tới MQTT Broker: {e}", flush=True)
        sys.exit(1)
        
    # Chờ kết nối Broker thành công (tối đa 10s) trước khi chạy vòng lặp mô phỏng
    print("Đang chờ thiết lập phiên kết nối MQTT...", flush=True)
    if not connected_event.wait(timeout=10.0):
        print("[WARNING] Phiên kết nối MQTT chưa sẵn sàng, mô phỏng sẽ bắt đầu ở chế độ offline.")
    else:
        print("[MQTT] Phiên kết nối MQTT đã sẵn sàng.", flush=True)
        
    # Khởi chạy luồng chạy ngầm cập nhật trạng thái vật lý và đẩy telemetry định kỳ
    t = threading.Thread(target=simulation_loop, daemon=True)
    t.start()
    
    # Khởi chạy giao diện console dòng lệnh chính.
    # Nếu chạy nền (không có console tương tác), bỏ qua console và giữ tiến trình sống
    # để mô phỏng + MQTT vẫn chạy liên tục.
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            console_loop()
        else:
            print("[HEADLESS] Không có console tương tác — chạy nền, mô phỏng vẫn tiếp tục.", flush=True)
            while True:
                time.sleep(1)
    except Exception as e:
        print(f"Lỗi vòng lặp console: {e}")
    finally:
        print("Đang ngắt kết nối MQTT...")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("Đã tắt bộ giả lập thành công.")

if __name__ == "__main__":
    main()
