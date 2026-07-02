import time
import math
import random
from datetime import datetime, timedelta
from config import (
    ZONES, ZONE_CODES, TYPE_CODES, DOOR_ADJACENT, WINDOW_ADJACENT,
    HANOI_MONTHLY_WEATHER
)
from protocol import (
    encode_dht22, encode_mq2, encode_lm393, encode_mc38,
    encode_light, encode_ahu, encode_curtain
)

class OfficeSimulation:
    def __init__(self):
        # Trạng thái giả lập thời gian
        self.sim_time = datetime(2026, 7, 1, 8, 0, 0) # Bắt đầu từ 8:00 sáng ngày 1/7/2026
        self.time_speed = 1.0 # Tốc độ thời gian (1.0 = thời gian thực, 60.0 = 1s thực là 1 phút giả lập)
        self.last_update_real_time = time.time()
        
        # Trạng thái ngoài trời
        self.outdoor_temp = 30.0
        self.outdoor_humid = 80.0
        self.outdoor_light = 0.0 # lux
        
        # Trạng thái môi trường trong các Zone
        self.zone_states = {}
        for zone in ZONES:
            self.zone_states[zone] = {
                "temp": round(random.uniform(24.0, 26.0), 1),
                "humid": round(random.uniform(55.0, 65.0), 1),
                "smoke": False,
                "light_intensity": 150,
                
                # Trạng thái các thiết bị chấp hành
                "light_active": False,
                "ahu_active": False,
                "ahu_fan_speed": 1, # 1: Yếu, 2: Trung bình, 3: Mạnh
                "ahu_temp_set": 25.0
            }
            
        # Trạng thái các cửa đi
        self.doors = {f"door_0{i}": {"is_open": False, "auto_close_time": None} for i in range(1, 6)}
        
        # Trạng thái các cửa sổ
        self.windows = {f"wd_0{i}": {"is_open": False, "curtain_pct": 100} for i in range(1, 7)}
        
        # Hộp thư gửi tin nhắn Hex (chứa hàng đợi các gói tin hex sẵn sàng gửi lên)
        self.publish_queue = []
        
        # Theo dõi lần gửi telemetry gần nhất (thực tế mỗi 10s)
        self.last_telemetry_real_time = 0.0
        
        # Tạo trạng thái ban đầu của toàn bộ thiết bị để đồng bộ Gateway ngay khi kết nối
        self.generate_initial_state()

    def get_outdoor_weather(self):
        """Tính toán thời tiết ngoài trời tại Hà Nội dựa trên thời gian giả lập"""
        month = self.sim_time.month
        hour = self.sim_time.hour + self.sim_time.minute / 60.0 + self.sim_time.second / 3600.0
        
        weather_config = HANOI_MONTHLY_WEATHER.get(month, {"temp": 25.0, "temp_range": 6.0, "humid": 80.0})
        avg_temp = weather_config["temp"]
        temp_range = weather_config["temp_range"]
        avg_humid = weather_config["humid"]
        
        # Nhiệt độ hình sin đạt đỉnh lúc 14:00 (chiều) và thấp nhất lúc 02:00 (sáng)
        # 14.0 giờ ứng với cos(0) = 1.0. 02.0 giờ ứng với cos(pi) = -1.0
        hour_rad = (hour - 14.0) * (2 * math.pi / 24.0)
        self.outdoor_temp = avg_temp + (temp_range / 2.0) * math.cos(hour_rad)
        
        # Độ ẩm ngược pha với nhiệt độ (độ ẩm thấp nhất lúc nóng nhất)
        self.outdoor_humid = max(30.0, min(99.0, avg_humid - 12.0 * math.cos(hour_rad)))
        
        # Ánh sáng mặt trời (Bình minh 5:30 -> Hoàng hôn 18:30)
        if 5.5 <= hour <= 18.5:
            # Mô phỏng hình sin đỉnh điểm lúc 12:00 trưa
            solar_factor = math.sin(math.pi * (hour - 5.5) / 13.0)
            # Độ sáng cực đại có thể lên tới 40,000 lux vào buổi trưa
            self.outdoor_light = 40000.0 * solar_factor
        else:
            self.outdoor_light = 0.0
            
    def update(self):
        """Vòng lặp cập nhật vật lý và logic môi trường"""
        now_real = time.time()
        dt_real = now_real - self.last_update_real_time
        self.last_update_real_time = now_real
        
        # Cập nhật thời gian giả lập
        dt_sim = dt_real * self.time_speed
        self.sim_time += timedelta(seconds=dt_sim)
        
        # Cập nhật thời tiết ngoài trời
        self.get_outdoor_weather()
        
        # 1. Xử lý mở cửa tự động đóng (auto-close doors sau một khoảng thời gian)
        for door_id, door_info in self.doors.items():
            if door_info["is_open"] and door_info["auto_close_time"] is not None:
                if self.sim_time >= door_info["auto_close_time"]:
                    self.set_door_state(door_id, False) # Đóng cửa
                    door_info["auto_close_time"] = None
                    
        # Mô phỏng người đi lại trong giờ làm việc (Thứ 2 - Thứ 6, từ 8:00 đến 18:00)
        is_working_day = self.sim_time.weekday() < 5
        is_working_hour = 8 <= self.sim_time.hour < 18
        in_office_hours = is_working_day and is_working_hour
        
        if in_office_hours:
            # Ngẫu nhiên mở cửa đi (1% cơ hội mỗi giây thực)
            if random.random() < 0.01 * dt_real:
                random_door = f"door_0{random.randint(1, 5)}"
                if not self.doors[random_door]["is_open"]:
                    # Mở cửa và hẹn giờ đóng sau 5 - 15 giây giả lập
                    self.set_door_state(random_door, True)
                    self.doors[random_door]["auto_close_time"] = self.sim_time + timedelta(seconds=random.randint(5, 15))
        
        # 2. Cập nhật trạng thái từng Zone
        for zone in ZONES:
            state = self.zone_states[zone]
            
            # --- Cập nhật Nhiệt độ ---
            # Hệ số trao đổi nhiệt cơ bản qua tường/trần
            k_conduction = 0.00005 
            
            # Kiểm tra xem có cửa chính hoặc cửa sổ nào mở nối từ zone ra ngoài không
            k_ventilation = 0.0
            
            # Duyệt các cửa sổ thuộc Zone này
            for wd_id, adj in WINDOW_ADJACENT.items():
                if zone in adj:
                    if self.windows[wd_id]["is_open"]:
                        k_ventilation += 0.002 # Mở cửa sổ thông gió rất mạnh
                        
            # Duyệt các cửa đi thuộc Zone này
            for door_id, adj in DOOR_ADJACENT.items():
                if zone in adj:
                    if self.doors[door_id]["is_open"]:
                        k_ventilation += 0.001 # Mở cửa đi thông gió trung bình
                        
            # Sự thay đổi nhiệt độ do trao đổi khí với bên ngoài
            temp_diff_outdoor = self.outdoor_temp - state["temp"]
            state["temp"] += (k_conduction + k_ventilation) * temp_diff_outdoor * dt_sim
            
            # Tỏa nhiệt từ con người và thiết bị văn phòng (chỉ khi có người làm việc)
            if in_office_hours:
                state["temp"] += 0.00002 * dt_sim # Tăng nhiệt tự nhiên
                
            # Tác động của điều hòa AHU
            if state["ahu_active"]:
                # Tốc độ làm mát/sưởi ấm phụ thuộc vào fan_speed (1, 2, 3)
                fan_mult = state["ahu_fan_speed"]
                # Khả năng thay đổi nhiệt độ của AHU
                k_ahu = 0.0005 * fan_mult
                state["temp"] += k_ahu * (state["ahu_temp_set"] - state["temp"]) * dt_sim
                
            state["temp"] = round(state["temp"], 2)
            
            # --- Cập nhật Độ ẩm ---
            # Độ ẩm đổi hướng theo độ ẩm ngoài trời
            humid_diff_outdoor = self.outdoor_humid - state["humid"]
            state["humid"] += (0.0001 + k_ventilation) * humid_diff_outdoor * dt_sim
            
            # AHU làm giảm độ ẩm khi làm lạnh (khi nhiệt độ đặt thấp hơn nhiệt độ phòng)
            if state["ahu_active"] and state["ahu_temp_set"] < state["temp"]:
                # Rút ẩm về mức dễ chịu khoảng 50%
                state["humid"] += 0.0003 * (50.0 - state["humid"]) * dt_sim
                
            state["humid"] = round(max(10.0, min(100.0, state["humid"])), 2)
            
            # --- Cập nhật Ánh sáng ---
            # Ánh sáng ngoài trời lọt qua cửa sổ của zone
            window_light_sum = 0.0
            window_count = 0
            for wd_id, adj in WINDOW_ADJACENT.items():
                if zone in adj:
                    window_count += 1
                    # Rèm che phủ làm cản bớt ánh sáng (0% cover = mở hoàn toàn, 100% cover = rèm dày cản 98%)
                    curtain_pct = self.windows[wd_id]["curtain_pct"]
                    transmissivity = 1.0 - (curtain_pct / 100.0) * 0.98
                    # Tác động của mái che ngoài ban công (eave factor = 0.15) cản bớt 85% ánh nắng trực tiếp
                    eave_factor = 0.15
                    window_light_sum += self.outdoor_light * transmissivity * eave_factor
            
            outdoor_contribution = (window_light_sum / window_count) if window_count > 0 else 0.0
            
            # Ánh sáng từ đèn trong phòng (bật đèn tăng thêm ~ 350 lux)
            lamp_contribution = 350.0 if state["light_active"] else 0.0
            
            # Ánh sáng nền tối thiểu
            base_light = 5.0
            
            # Cập nhật giá trị ánh sáng thực tế kèm nhiễu nhẹ
            target_light = base_light + outdoor_contribution + lamp_contribution
            state["light_intensity"] = max(0, int(target_light + random.randint(-2, 2)))
            
        # 3. Gửi Telemetry định kỳ mỗi 10 giây (Thời gian thực)
        if now_real - self.last_telemetry_real_time >= 10.0:
            self.last_telemetry_real_time = now_real
            self.generate_periodic_telemetry()
            
    def generate_periodic_telemetry(self):
        """Tạo các gói tin telemetry định kỳ của cảm biến và đưa vào hàng đợi gửi"""
        for zone in ZONES:
            state = self.zone_states[zone]
            zone_code = ZONE_CODES[zone]
            
            # 1. DHT22
            self.publish_queue.append((
                ZONE_CODES[zone], 
                TYPE_CODES["dht22"], 
                encode_dht22(zone_code, state["temp"], state["humid"])
            ))
            
            # 2. MQ2 (chỉ gửi khi có sự thay đổi hoặc ngẫu nhiên cập nhật, ở đây gửi định kỳ luôn để khớp v1)
            self.publish_queue.append((
                ZONE_CODES[zone], 
                TYPE_CODES["mq2"], 
                encode_mq2(zone_code, state["smoke"])
            ))
            
            # 3. LM393
            self.publish_queue.append((
                ZONE_CODES[zone], 
                TYPE_CODES["lm393"], 
                encode_lm393(zone_code, state["light_intensity"])
            ))

    def generate_initial_state(self):
        """Tạo dữ liệu trạng thái ban đầu của toàn bộ cảm biến, thiết bị, cửa để đồng bộ Gateway"""
        # 1. Toàn bộ cảm biến DHT22, MQ2, LM393 của 12 Zones
        self.generate_periodic_telemetry()
        
        # 2. Toàn bộ Đèn và AHU của 12 Zones
        for zone in ZONES:
            state = self.zone_states[zone]
            zone_code = ZONE_CODES[zone]
            
            # Đèn
            self.publish_queue.append((
                zone_code,
                TYPE_CODES["light"],
                encode_light(zone_code, state["light_active"])
            ))
            
            # AHU
            self.publish_queue.append((
                zone_code,
                TYPE_CODES["ahu"],
                encode_ahu(zone_code, state["ahu_active"], state["ahu_fan_speed"], state["ahu_temp_set"])
            ))
            
        # 3. Toàn bộ Cửa đi (MC38)
        for door_id in self.doors:
            door_code = ZONE_CODES[door_id]
            is_open = self.doors[door_id]["is_open"]
            self.publish_queue.append((
                door_code,
                TYPE_CODES["mc38"],
                encode_mc38(door_code, is_open)
            ))
            
        # 4. Toàn bộ Cửa sổ & Rèm (MC38, Curtain)
        for wd_id in self.windows:
            wd_code = ZONE_CODES[wd_id]
            is_open = self.windows[wd_id]["is_open"]
            curtain_pct = self.windows[wd_id]["curtain_pct"]
            
            # Cửa sổ MC38
            self.publish_queue.append((
                wd_code,
                TYPE_CODES["mc38"],
                encode_mc38(wd_code, is_open)
            ))
            
            # Rèm Curtain
            self.publish_queue.append((
                wd_code,
                TYPE_CODES["curtain"],
                encode_curtain(wd_code, curtain_pct)
            ))

    # --- CÁC HÀM THAY ĐỔI TRẠNG THÁI (console hoặc MQTT ghi đè) ---

    def set_door_state(self, door_id: str, is_open: bool):
        """Thay đổi trạng thái cửa đi và gửi ngay mã MC38 Hex tương ứng"""
        if door_id in self.doors:
            old_state = self.doors[door_id]["is_open"]
            self.doors[door_id]["is_open"] = is_open
            
            if old_state != is_open:
                # Gửi gói tin MC38 ngay lập tức
                code = ZONE_CODES[door_id]
                hex_msg = encode_mc38(code, is_open)
                self.publish_queue.append((code, TYPE_CODES["mc38"], hex_msg))
                return True
        return False

    def set_window_state(self, wd_id: str, is_open: bool):
        """Thay đổi trạng thái cửa sổ và gửi ngay mã MC38 Hex tương ứng"""
        if wd_id in self.windows:
            old_state = self.windows[wd_id]["is_open"]
            self.windows[wd_id]["is_open"] = is_open
            
            if old_state != is_open:
                # Gửi gói tin MC38 ngay lập tức
                code = ZONE_CODES[wd_id]
                hex_msg = encode_mc38(code, is_open)
                self.publish_queue.append((code, TYPE_CODES["mc38"], hex_msg))
                return True
        return False

    def set_light_state(self, zone: str, active: bool):
        """Thay đổi trạng thái Đèn và gửi phản hồi Hex ngay lập tức"""
        if zone in self.zone_states:
            self.zone_states[zone]["light_active"] = active
            code = ZONE_CODES[zone]
            hex_msg = encode_light(code, active)
            self.publish_queue.append((code, TYPE_CODES["light"], hex_msg))
            
            # Thay đổi ánh sáng ngay lập tức trong mô phỏng
            lamp_contrib = 350.0 if active else 0.0
            # Cập nhật nháp để người dùng thấy thay đổi ngay trong console
            self.zone_states[zone]["light_intensity"] = max(0, int(5.0 + lamp_contrib))
            return True
        return False

    def set_ahu_state(self, zone: str, active: bool, fan_speed: int = None, temp_set: float = None):
        """Thay đổi cấu hình AHU và gửi phản hồi Hex ngay lập tức"""
        if zone in self.zone_states:
            state = self.zone_states[zone]
            state["ahu_active"] = active
            if fan_speed is not None:
                state["ahu_fan_speed"] = int(fan_speed)
            if temp_set is not None:
                state["ahu_temp_set"] = float(temp_set)
                
            code = ZONE_CODES[zone]
            hex_msg = encode_ahu(code, state["ahu_active"], state["ahu_fan_speed"], state["ahu_temp_set"])
            self.publish_queue.append((code, TYPE_CODES["ahu"], hex_msg))
            return True
        return False

    def set_curtain_state(self, wd_id: str, percentage_cover: int):
        """Thay đổi trạng thái rèm cửa sổ và gửi phản hồi Hex ngay lập tức"""
        if wd_id in self.windows:
            percentage_cover = max(0, min(100, int(percentage_cover)))
            self.windows[wd_id]["curtain_pct"] = percentage_cover
            
            code = ZONE_CODES[wd_id]
            hex_msg = encode_curtain(code, percentage_cover)
            self.publish_queue.append((code, TYPE_CODES["curtain"], hex_msg))
            return True
        return False

    def set_smoke_alarm(self, zone: str, has_smoke: bool):
        """Kích hoạt/tắt cảnh báo khói MQ2 trong Zone và gửi gói tin Hex ngay lập tức"""
        if zone in self.zone_states:
            self.zone_states[zone]["smoke"] = has_smoke
            code = ZONE_CODES[zone]
            hex_msg = encode_mq2(code, has_smoke)
            self.publish_queue.append((code, TYPE_CODES["mq2"], hex_msg))
            return True
        return False
