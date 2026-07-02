import struct
from config import TYPE_CODES, CODE_TO_TYPE, ZONE_CODES, CODE_TO_ZONE

def calculate_checksum(zone_id: int, type_code: int, length: int, payload: bytes) -> int:
    """Tính toán XOR Checksum cho khung truyền tin"""
    chk = zone_id ^ type_code ^ length
    for b in payload:
        chk ^= b
    return chk

def wrap_uplink_frame(zone_id: int, type_code: int, payload: bytes) -> str:
    """Đóng gói dữ liệu uplink (Device -> Gateway) thành chuỗi Hex"""
    length = len(payload)
    checksum = calculate_checksum(zone_id, type_code, length, payload)
    frame = bytearray([0xA5, zone_id, type_code, length]) + payload + bytearray([checksum, 0x5A])
    return frame.hex().upper()

def wrap_downlink_frame(zone_id: int, type_code: int, payload: bytes) -> str:
    """Đóng gói dữ liệu downlink (Gateway -> Device) thành chuỗi Hex (tiện dùng kiểm thử)"""
    length = len(payload)
    checksum = calculate_checksum(zone_id, type_code, length, payload)
    frame = bytearray([0x5A, zone_id, type_code, length]) + payload + bytearray([checksum, 0xA5])
    return frame.hex().upper()

def parse_downlink_frame(hex_str: str):
    """Giải mã khung truyền tin downlink (Gateway -> Device)"""
    try:
        hex_clean = hex_str.strip().replace(" ", "")
        data = bytes.fromhex(hex_clean)
        if len(data) < 7:
            return None # Khung quá ngắn
        if data[0] != 0x5A or data[-1] != 0xA5:
            return None # Sai Start/End byte
            
        zone_id = data[1]
        type_code = data[2]
        length = data[3]
        
        if len(data) != 6 + length:
            return None # Độ dài không khớp thực tế
            
        payload = data[4:4+length]
        checksum = data[4+length]
        
        if checksum != calculate_checksum(zone_id, type_code, length, payload):
            return None # Sai Checksum
            
        return {
            "zone_id": zone_id,
            "type_code": type_code,
            "payload": payload
        }
    except Exception:
        return None

# --- BỘ ENCODE TELEMETRY (UPLINK) ---

def encode_dht22(zone_code: int, temp: float, humid: float) -> str:
    """Mã hóa cảm biến nhiệt ẩm DHT22 (4 Bytes)"""
    payload = struct.pack(">hH", int(temp * 10), int(humid * 10))
    return wrap_uplink_frame(zone_code, TYPE_CODES["dht22"], payload)

def encode_mq2(zone_code: int, smoke: bool) -> str:
    """Mã hóa cảm biến báo khói MQ2 (1 Byte)"""
    payload = struct.pack(">B", 1 if smoke else 0)
    return wrap_uplink_frame(zone_code, TYPE_CODES["mq2"], payload)

def encode_lm393(zone_code: int, light_intensity: int) -> str:
    """Mã hóa cảm biến cường độ ánh sáng LM393 (2 Bytes)"""
    payload = struct.pack(">H", int(light_intensity))
    return wrap_uplink_frame(zone_code, TYPE_CODES["lm393"], payload)

def encode_mc38(zone_or_device_code: int, is_open: bool) -> str:
    """Mã hóa cảm biến cửa đóng/mở MC38 (1 Byte)"""
    payload = struct.pack(">B", 1 if is_open else 0)
    return wrap_uplink_frame(zone_or_device_code, TYPE_CODES["mc38"], payload)

def encode_light(zone_code: int, active: bool) -> str:
    """Mã hóa phản hồi trạng thái đèn (1 Byte)"""
    payload = struct.pack(">B", 1 if active else 0)
    return wrap_uplink_frame(zone_code, TYPE_CODES["light"], payload)

def encode_ahu(zone_code: int, active: bool, fan_speed: int, temp_set: float) -> str:
    """Mã hóa phản hồi trạng thái điều hòa AHU (4 Bytes)"""
    payload = struct.pack(">BBh", 1 if active else 0, int(fan_speed), int(temp_set * 10))
    return wrap_uplink_frame(zone_code, TYPE_CODES["ahu"], payload)

def encode_curtain(window_code: int, percentage_cover: int) -> str:
    """Mã hóa phản hồi trạng thái rèm cửa (1 Byte)"""
    payload = struct.pack(">B", int(percentage_cover))
    return wrap_uplink_frame(window_code, TYPE_CODES["curtain"], payload)

# --- BỘ DECODE COMMANDS (DOWNLINK) ---

def decode_command_payload(type_code: int, payload: bytes):
    """Giải mã dữ liệu điều khiển của từng loại thiết bị"""
    try:
        if type_code == TYPE_CODES["light"]:
            # Light payload: 1 Byte (0x00/0x01)
            active = struct.unpack(">B", payload)[0] == 1
            return {"active": active}
            
        elif type_code == TYPE_CODES["ahu"]:
            # AHU payload: 4 Bytes (Active(1B), FanSpeed(1B), TempSet(2B))
            active_val, fan_speed, temp_set_val = struct.unpack(">BBh", payload)
            return {
                "active": active_val == 1,
                "fan_speed": fan_speed,
                "temp_set": temp_set_val / 10.0
            }
            
        elif type_code == TYPE_CODES["curtain"]:
            # Curtain payload: 1 Byte (Percentage 0-100)
            percentage_cover = struct.unpack(">B", payload)[0]
            return {"percentage_cover": percentage_cover}
            
    except Exception:
        pass
    return None
