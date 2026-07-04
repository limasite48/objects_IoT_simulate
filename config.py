# Cấu hình cho hệ thống giả lập thiết bị & cảm biến IoT

# Broker cục bộ dùng chung với gateway & backend (đổi từ broker.emqx.io sang localhost
# để chạy pipeline thật: sensor -> gateway -> server qua một Mosquitto ở localhost:1883)
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_TELEMETRY = "duk1chvietcong/hcmc_office/telemetry"
TOPIC_COMMAND = "duk1chvietcong/hcmc_office/command"

# Cấu hình bảo mật AES-CCM (Giả lập Link Key từ Zigbee 3.0 Install Code)
AES_KEY = b"IoT_prj_gr21"

# Mã hex định danh cho các phân vùng (Zone ID)
ZONE_CODES = {
    "pantry": 0x01,
    "storage": 0x02,
    "prvt_meeting": 0x03,
    "office_1": 0x04,
    "office_2": 0x05,
    "lobby": 0x06,
    "connect": 0x07,
    "director": 0x08,
    "finance_mng": 0x09,
    "finace_mng": 0x09,  # Hỗ trợ lỗi chính tả từ file đặc tả
    "meeting": 0x0A,
    "technical_mng": 0x0B,
    "vice_director": 0x0C,
    
    # Cửa đi (Doors)
    "door_01": 0xD1,
    "door_02": 0xD2,
    "door_03": 0xD3,
    "door_04": 0xD4,
    "door_05": 0xD5,
    
    # Cửa sổ (Windows)
    "wd_01": 0xE1,
    "wd_02": 0xE2,
    "wd_03": 0xE3,
    "wd_04": 0xE4,
    "wd_05": 0xE5,
    "wd_06": 0xE6
}

# Ánh xạ ngược từ Code sang Tên đối tượng (dùng tên chuẩn hóa chính)
CODE_TO_ZONE = {
    0x01: "pantry",
    0x02: "storage",
    0x03: "prvt_meeting",
    0x04: "office_1",
    0x05: "office_2",
    0x06: "lobby",
    0x07: "connect",
    0x08: "director",
    0x09: "finance_mng",
    0x0A: "meeting",
    0x0B: "technical_mng",
    0x0C: "vice_director",
    0xD1: "door_01",
    0xD2: "door_02",
    0xD3: "door_03",
    0xD4: "door_04",
    0xD5: "door_05",
    0xE1: "wd_01",
    0xE2: "wd_02",
    0xE3: "wd_03",
    0xE4: "wd_04",
    0xE5: "wd_05",
    0xE6: "wd_06"
}

# Mã hex cho các loại thiết bị & cảm biến (Device/Sensor Type)
TYPE_CODES = {
    # Cảm biến (Sensors)
    "dht22": 0x11,
    "mq2": 0x12,
    "lm393": 0x13,
    "mc38": 0x14,
    
    # Thiết bị chấp hành (Devices)
    "light": 0x21,
    "ahu": 0x22,
    "curtain": 0x23
}

CODE_TO_TYPE = {code: name for name, code in TYPE_CODES.items()}

# Danh sách các Zones chuẩn
ZONES = ["pantry", "storage", "prvt_meeting", "office_1", "office_2", "lobby", 
         "connect", "director", "finance_mng", "meeting", "technical_mng", "vice_director"]

# Định nghĩa các mối liên kết liền kề (Adjacent relationships) để mô phỏng sự lan truyền nhiệt/gió
DOOR_ADJACENT = {
    "door_01": ("outside", "lobby"),
    "door_02": ("outside", "lobby"),
    "door_03": ("balcony", "director"),
    "door_04": ("balcony", "meeting"),
    "door_05": ("balcony", "vice_director")
}

WINDOW_ADJACENT = {
    "wd_01": ("outside", "lobby"),
    "wd_02": ("outside", "office_1"),  # Mặc định kết nối với office_1
    "wd_03": ("outside", "office_2"),
    "wd_04": ("balcony", "director", "finance_mng"),
    "wd_05": ("balcony", "meeting"),
    "wd_06": ("balcony", "vice_director", "technical_mng")
}

# Cấu hình thời tiết trung bình tháng tại Hà Nội (Nhiệt độ trung bình, dải độ ẩm)
HANOI_MONTHLY_WEATHER = {
    1:  {"temp": 16.5, "temp_range": 5.0, "humid": 70.0},
    2:  {"temp": 17.5, "temp_range": 5.0, "humid": 75.0},
    3:  {"temp": 20.5, "temp_range": 6.0, "humid": 90.0}, # Nồm ẩm
    4:  {"temp": 24.5, "temp_range": 6.0, "humid": 85.0},
    5:  {"temp": 28.5, "temp_range": 7.0, "humid": 80.0},
    6:  {"temp": 30.5, "temp_range": 8.0, "humid": 78.0},
    7:  {"temp": 30.0, "temp_range": 8.0, "humid": 80.0},
    8:  {"temp": 29.5, "temp_range": 7.0, "humid": 82.0},
    9:  {"temp": 28.0, "temp_range": 6.0, "humid": 80.0},
    10: {"temp": 25.5, "temp_range": 6.0, "humid": 75.0},
    11: {"temp": 22.0, "temp_range": 5.0, "humid": 72.0},
    12: {"temp": 18.5, "temp_range": 5.0, "humid": 68.0}
}
